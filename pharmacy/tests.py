from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from hospitals.models import Department, Hospital
from opd import services as opd_services
from opd.models import Patient
from pharmacy import services
from pharmacy.models import Medicine, Prescription, PrescriptionItem, StockMovement

TODAY = timezone.localdate()


class PharmacyBase(TestCase):
    def setUp(self):
        self.h = Hospital.objects.create(name='H', area='A')
        dept = Department.objects.create(hospital=self.h, name='Gen', code='GEN')
        patient = Patient.objects.create(name='P', phone='9000000001', age=30, gender='M')
        self.token = opd_services.book_token(patient, dept)
        self.user = get_user_model().objects.create_user('pharma', password='x')
        self.para = self.med('Paracetamol', 100, reorder=20)
        self.amox = self.med('Amoxicillin', 10, reorder=5)

    def med(self, name, qty, reorder=10, days=365, hospital=None):
        return Medicine.objects.create(hospital=hospital or self.h, name=name, quantity=qty, reorder_level=reorder,
                                       expiry_date=TODAY + timedelta(days=days), unit_price=2)

    def rx(self, *pairs):
        rx = Prescription.objects.create(token=self.token)
        for med, qty in pairs:
            PrescriptionItem.objects.create(prescription=rx, medicine=med, quantity=qty)
        return rx


class DispenseTests(PharmacyBase):
    def test_dispense_deducts_stock_and_logs_movements(self):
        rx = services.dispense(self.rx((self.para, 30), (self.amox, 4)), user=self.user)
        self.para.refresh_from_db()
        self.amox.refresh_from_db()
        self.assertEqual((rx.status, self.para.quantity, self.amox.quantity), ('DISPENSED', 70, 6))
        mv = StockMovement.objects.get(medicine=self.para)
        self.assertEqual((mv.change, mv.reason, mv.performed_by), (-30, 'DISPENSED', self.user))

    def test_insufficient_stock_rolls_back_everything(self):
        rx = self.rx((self.para, 30), (self.amox, 11))  # amoxicillin only has 10
        with self.assertRaises(services.InsufficientStock):
            services.dispense(rx)
        self.para.refresh_from_db()
        rx.refresh_from_db()
        self.assertEqual((self.para.quantity, rx.status), (100, 'PENDING'))  # first item not deducted
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_exact_stock_can_be_dispensed_to_zero(self):
        services.dispense(self.rx((self.amox, 10)))
        self.amox.refresh_from_db()
        self.assertEqual(self.amox.quantity, 0)

    def test_expired_medicine_blocked(self):
        old = self.med('Old syrup', 50, days=-1)
        with self.assertRaises(services.ExpiredMedicine):
            services.dispense(self.rx((old, 1)))
        old.refresh_from_db()
        self.assertEqual(old.quantity, 50)

    def test_cannot_dispense_twice(self):
        rx = self.rx((self.para, 1))
        services.dispense(rx)
        with self.assertRaises(services.InvalidPrescription):
            services.dispense(rx)  # stale object, DB state decides
        self.para.refresh_from_db()
        self.assertEqual(self.para.quantity, 99)

    def test_medicine_from_other_hospital_rejected(self):
        other = Hospital.objects.create(name='Other', area='B')
        foreign = self.med('Foreign', 10, hospital=other)
        with self.assertRaises(services.InvalidPrescription):
            services.dispense(self.rx((foreign, 1)))

    def test_empty_prescription_rejected(self):
        with self.assertRaises(services.InvalidPrescription):
            services.dispense(self.rx())


class StockAlertTests(PharmacyBase):
    def test_low_stock_alert_at_or_below_reorder_level(self):
        low = self.med('Low', 5, reorder=5)       # equal to level -> alert
        self.med('Fine', 6, reorder=5)
        names = [m.name for m in services.low_stock(self.h)]
        self.assertEqual(names, ['Low'])
        self.assertNotIn(self.para.name, names)
        services.dispense(self.rx((self.para, 85)))  # 100 -> 15, below reorder 20
        self.assertIn('Paracetamol', [m.name for m in services.low_stock(self.h)])
        self.assertEqual(low.is_low, True)

    def test_expired_and_expiring_lists(self):
        self.med('Gone', 5, days=-3)
        self.med('Soon', 5, days=10)
        self.assertEqual([m.name for m in services.expired(self.h)], ['Gone'])
        self.assertEqual([m.name for m in services.expiring_soon(self.h)], ['Soon'])

    def test_receive_stock_and_write_off(self):
        services.receive_stock(self.amox, 15, user=self.user)
        self.amox.refresh_from_db()
        self.assertEqual(self.amox.quantity, 25)
        with self.assertRaises(services.PharmacyError):
            services.receive_stock(self.amox, 0)
        self.med('Gone', 7, days=-1)
        self.assertEqual(services.write_off_expired(self.h, user=self.user), 1)
        self.assertEqual(Medicine.objects.get(name='Gone').quantity, 0)
        self.assertTrue(StockMovement.objects.filter(reason='EXPIRED', change=-7).exists())
