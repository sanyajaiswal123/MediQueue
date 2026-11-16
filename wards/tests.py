from django.test import TestCase

from hospitals.models import Hospital
from opd.models import Patient
from wards import services
from wards.models import Admission, Bed, Ward

A = Admission.Status
B = Bed.Status


def make_patient(n):
    return Patient.objects.create(name=f'P{n}', phone=f'80000000{n:02d}', age=40, gender='F')


class WardBase(TestCase):
    def setUp(self):
        self.h = Hospital.objects.create(name='H', area='A')
        self.ward = Ward.objects.create(hospital=self.h, name='General', ward_type='GENERAL')
        self.b1 = Bed.objects.create(ward=self.ward, number='1')
        self.b2 = Bed.objects.create(ward=self.ward, number='2')


class AdmitTests(WardBase):
    def test_admit_assigns_free_bed(self):
        adm = services.admit_patient(make_patient(1), self.ward)
        self.b1.refresh_from_db()
        self.assertEqual((adm.status, adm.bed, self.b1.status), (A.ADMITTED, self.b1, B.OCCUPIED))
        self.assertIsNotNone(adm.admitted_at)

    def test_no_bed_goes_to_waiting_list(self):
        services.admit_patient(make_patient(1), self.ward)
        services.admit_patient(make_patient(2), self.ward)
        adm = services.admit_patient(make_patient(3), self.ward)
        self.assertEqual((adm.status, adm.bed), (A.WAITING, None))
        self.assertEqual(list(services.waiting_list(self.ward)), [adm])

    def test_patient_cannot_hold_two_active_admissions(self):
        p = make_patient(1)
        services.admit_patient(p, self.ward)
        with self.assertRaises(services.AlreadyAdmitted):
            services.admit_patient(p, self.ward)

    def test_two_requests_never_share_a_bed(self):
        """Sequential stand-in for a race: with one free bed only one of two requests gets it."""
        self.b2.delete()
        a = services.admit_patient(make_patient(1), self.ward)
        b = services.admit_patient(make_patient(2), self.ward)
        self.assertEqual((a.status, b.status), (A.ADMITTED, A.WAITING))
        self.assertEqual(Bed.objects.filter(status=B.OCCUPIED).count(), 1)
        self.assertEqual(Admission.objects.filter(bed=self.b1).count(), 1)


class DischargeAndAllocationTests(WardBase):
    def test_discharge_puts_bed_in_cleaning_and_it_is_not_reassigned(self):
        a = services.admit_patient(make_patient(1), self.ward)
        services.admit_patient(make_patient(2), self.ward)
        waiting = services.admit_patient(make_patient(3), self.ward)
        services.discharge(a)
        self.b1.refresh_from_db()
        waiting.refresh_from_db()
        self.assertEqual(self.b1.status, B.CLEANING)
        self.assertEqual(waiting.status, A.WAITING)  # dirty bed must not be given out

    def test_mark_clean_auto_allocates_to_waiting_priority_first(self):
        a = services.admit_patient(make_patient(1), self.ward)
        services.admit_patient(make_patient(2), self.ward)
        normal = services.admit_patient(make_patient(3), self.ward)
        urgent = services.admit_patient(make_patient(4), self.ward, priority=True)
        services.discharge(a)
        got = services.mark_clean(self.b1)
        normal.refresh_from_db()
        urgent.refresh_from_db()
        self.assertEqual(got, urgent)
        self.assertEqual((urgent.status, urgent.bed), (A.ADMITTED, self.b1))
        self.assertEqual(normal.status, A.WAITING)

    def test_mark_clean_with_empty_waiting_list_frees_bed(self):
        a = services.admit_patient(make_patient(1), self.ward)
        services.discharge(a)
        self.assertIsNone(services.mark_clean(self.b1))
        self.b1.refresh_from_db()
        self.assertEqual(self.b1.status, B.AVAILABLE)

    def test_double_discharge_rejected(self):
        a = services.admit_patient(make_patient(1), self.ward)
        services.discharge(a)
        with self.assertRaises(services.InvalidAdmissionState):
            services.discharge(a)  # `a` is a stale object; the DB state is what counts

    def test_cannot_discharge_waiting_or_clean_a_free_bed(self):
        services.admit_patient(make_patient(1), self.ward)
        services.admit_patient(make_patient(2), self.ward)
        waiting = services.admit_patient(make_patient(3), self.ward)
        with self.assertRaises(services.InvalidAdmissionState):
            services.discharge(waiting)
        with self.assertRaises(services.InvalidBedState):
            services.mark_clean(Bed.objects.create(ward=self.ward, number='9'))

    def test_cancel_waiting_and_bed_counts(self):
        services.admit_patient(make_patient(1), self.ward)
        services.admit_patient(make_patient(2), self.ward)
        waiting = services.admit_patient(make_patient(3), self.ward)
        self.assertEqual(services.bed_counts(self.h),
                         {'total': 2, 'available': 0, 'occupied': 2, 'cleaning': 0, 'waiting': 1})
        services.cancel_waiting(waiting)
        self.assertEqual(services.bed_counts(self.h)['waiting'], 0)
        with self.assertRaises(services.InvalidAdmissionState):
            services.cancel_waiting(waiting)
