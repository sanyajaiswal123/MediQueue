"""End-to-end view tests for the P8/P9 screens (S1-S14), run against seed_demo data."""
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Profile
from hospitals.models import Department, Hospital
from opd import services as opd_services
from opd.models import Patient, Token
from opd.views import ACTIVE_TOKEN_SESSION_KEY, PREFERRED_HOSPITAL_COOKIE
from pharmacy.models import Medicine, Prescription
from wards.models import Admission, Bed, Ward

PW = 'demo'
S = Token.Status


class ScreenBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', stdout=StringIO())
        cls.hospital = Hospital.objects.get(name='City Care Hospital')
        cls.dept = Department.objects.get(hospital=cls.hospital, code='CAR')

    def login(self, username):
        self.assertTrue(self.client.login(username=username, password=PW))

    def make_patient_user(self, username='asha'):
        user = User.objects.create_user(username, password=PW, first_name='Asha')
        user.profile.phone = '9876543210'
        user.profile.save()
        return user


class PublicPagesTests(ScreenBase):
    def test_landing_shows_live_aggregates(self):
        res = self.client.get(reverse('home'))
        self.assertContains(res, 'Now serving')
        self.assertContains(res, 'beds free right now')

    def test_landing_names_every_pillar_and_the_problem(self):
        res = self.client.get(reverse('home'))
        for text in ('Three things hospitals still do blind', 'waiting for a bed', 'medicines in stock',
                     'Where do you start?'):
            self.assertContains(res, text)
        self.assertEqual(res.context['stats']['admissions_waiting'], 0)

    def test_landing_empty_queue_is_not_shown_as_zero_wait(self):
        res = self.client.get(reverse('home'))
        self.assertTrue(res.context['stats']['quiet'])
        self.assertContains(res, 'Tokens left today')
        self.assertNotContains(res, 'Shortest wait right now')

    def test_city_dashboard_page(self):
        self.assertContains(self.client.get(reverse('city')), 'id="city"')

    @override_settings(DEBUG=False)
    def test_custom_404(self):
        res = self.client.get('/no-such-page/')
        self.assertEqual(res.status_code, 404)
        self.assertContains(res, "isn't in any queue", status_code=404)


class PatientFlowTests(ScreenBase):
    def test_book_sets_session_cookie_and_redirects_to_tracker(self):
        self.make_patient_user()
        self.login('asha')
        url = reverse('opd:book') + f'?hospital={self.hospital.pk}'
        self.assertContains(self.client.get(url), 'Cardiology')
        res = self.client.post(url, {'department': self.dept.pk, 'age': 31, 'gender': 'F'})
        token = Token.objects.get(patient__user__username='asha')
        self.assertRedirects(res, reverse('opd:track', args=[token.pk]) + '?new=1')
        self.assertEqual(self.client.session[ACTIVE_TOKEN_SESSION_KEY], token.pk)
        self.assertEqual(res.cookies[PREFERRED_HOSPITAL_COOKIE].value, str(self.hospital.pk))
        self.assertContains(self.client.get(reverse('opd:track', args=[token.pk])), token.label)
        self.assertRedirects(self.client.get(reverse('opd:my_token')), reverse('opd:track', args=[token.pk]))

    def test_duplicate_booking_shows_error(self):
        self.make_patient_user()
        self.login('asha')
        url = reverse('opd:book') + f'?hospital={self.hospital.pk}'
        self.client.post(url, {'department': self.dept.pk, 'age': 31, 'gender': 'F'})
        res = self.client.post(url, {'department': self.dept.pk})
        self.assertContains(res, 'already have an active token')

    def test_cannot_track_someone_elses_token(self):
        other = Patient.objects.create(name='Other', phone='9000000000', age=40, gender='M')
        token = opd_services.book_token(other, self.dept)
        self.make_patient_user()
        self.login('asha')
        self.assertEqual(self.client.get(reverse('opd:track', args=[token.pk])).status_code, 404)

    def test_staff_cannot_book(self):
        self.login('reception')
        self.assertEqual(self.client.get(reverse('opd:book')).status_code, 403)


class ReceptionAndDoctorTests(ScreenBase):
    def test_walk_in_then_full_consultation_with_prescription(self):
        self.login('reception')
        res = self.client.post(reverse('opd:reception'), {
            'name': 'Ravi Kumar', 'phone': '9811111111', 'age': 60, 'gender': 'M',
            'department': self.dept.pk, 'is_priority': 'on'})
        token = Token.objects.get(patient__name='Ravi Kumar')
        self.assertTrue(token.is_priority)
        self.assertRedirects(res, reverse('opd:reception') + f'?dept={self.dept.pk}')
        self.assertContains(self.client.get(res.url), 'CAR-001')

        self.client.logout()
        self.login('doctor')
        self.client.post(reverse('opd:console'), {'action': 'call_next'})
        token.refresh_from_db()
        self.assertEqual(token.status, S.CALLED)
        self.client.post(reverse('opd:token_action', args=[token.pk, 'start']))
        token.refresh_from_db()
        self.assertEqual(token.status, S.IN_CONSULT)

        med = Medicine.objects.get(hospital=self.hospital, name='Paracetamol 500mg')
        self.client.post(reverse('opd:console'), {
            'action': 'complete', 'rx-TOTAL_FORMS': 3, 'rx-INITIAL_FORMS': 0, 'rx-MIN_NUM_FORMS': 0,
            'rx-MAX_NUM_FORMS': 6, 'rx-0-medicine': med.pk, 'rx-0-quantity': 10})
        token.refresh_from_db()
        self.assertEqual(token.status, S.COMPLETED)
        rx = Prescription.objects.get(token=token)
        self.assertEqual(rx.items.get().quantity, 10)

        self.client.logout()
        self.login('pharmacist')
        self.assertContains(self.client.get(reverse('pharmacy:dispense_list')), token.label)
        self.client.post(reverse('pharmacy:dispense', args=[rx.pk]))
        med.refresh_from_db()
        self.assertEqual(med.quantity, 490)

    def test_three_calls_then_no_show(self):
        token = opd_services.book_token(Patient.objects.create(name='X', phone='9000000001', age=20, gender='F'),
                                        self.dept)
        opd_services.call_next(self.dept)
        for _ in range(2):
            token = opd_services.recall(token)
        self.assertEqual((token.status, token.call_count), (S.CALLED, 3))
        self.assertEqual(opd_services.recall(token).status, S.NO_SHOW)

    def test_receptionist_cannot_recall_or_use_other_hospital_token(self):
        self.login('reception')
        self.assertEqual(self.client.get(reverse('opd:console')).status_code, 403)
        other = Department.objects.get(hospital__name='Lifeline Medical Centre', code='CAR')
        t = opd_services.book_token(Patient.objects.create(name='Y', phone='9000000002', age=20, gender='F'), other)
        res = self.client.post(reverse('opd:token_action', args=[t.pk, 'cancel']))
        self.assertEqual(res.status_code, 404)

    def test_pharmacist_cannot_open_reception(self):
        self.login('pharmacist')
        self.assertEqual(self.client.get(reverse('opd:reception')).status_code, 403)


class WardScreenTests(ScreenBase):
    def test_admit_discharge_clean_cycle(self):
        self.login('reception')
        icu = Ward.objects.get(hospital=self.hospital, name='ICU')
        for i in range(5):  # ICU has 4 beds: the 5th waits
            self.client.post(reverse('wards:admissions'), {
                'name': f'Pt {i}', 'phone': f'98000000{i:02d}', 'age': 50, 'gender': 'M', 'ward': icu.pk})
        waiting = Admission.objects.get(ward=icu, status=Admission.Status.WAITING)
        self.assertContains(self.client.get(reverse('wards:admissions')), waiting.patient.name)
        self.assertContains(self.client.get(reverse('wards:board')), 'Occupied')

        first = Admission.objects.filter(ward=icu, status=Admission.Status.ADMITTED).first()
        self.client.post(reverse('wards:discharge', args=[first.pk]))
        bed = Bed.objects.get(pk=first.bed_id)
        self.assertEqual(bed.status, Bed.Status.CLEANING)
        self.assertContains(self.client.get(reverse('wards:discharges')), 'Mark clean')
        self.client.post(reverse('wards:mark_clean', args=[bed.pk]))
        waiting.refresh_from_db()
        self.assertEqual((waiting.status, waiting.bed_id), (Admission.Status.ADMITTED, bed.pk))


class StaffOverviewTests(ScreenBase):
    def test_overview_and_role_nav(self):
        self.login('pharmacist')
        res = self.client.get(reverse('staff_home'))
        self.assertContains(res, 'Live queue')
        self.assertContains(res, 'Tokens, last 14 days')
        self.assertContains(res, reverse('pharmacy:stock'))
        self.assertNotContains(res, reverse('opd:reception'))

    def test_stock_page_and_receive(self):
        self.login('pharmacist')
        med = Medicine.objects.get(hospital=self.hospital, name='Metformin 500mg')
        self.assertContains(self.client.get(reverse('pharmacy:stock')), 'Low stock')
        self.client.post(reverse('pharmacy:stock'), {'medicine': med.pk, 'quantity': 100})
        med.refresh_from_db()
        self.assertEqual(med.quantity, 140)

    def test_every_staff_screen_renders_for_its_role(self):
        screens = {
            'reception': ['opd:reception', 'wards:board', 'wards:admissions', 'wards:discharges'],
            'doctor': ['opd:console', 'wards:board'],
            'pharmacist': ['pharmacy:dispense_list', 'pharmacy:stock'],
        }
        for user, names in screens.items():
            self.client.logout()
            self.login(user)
            for name in names:
                self.assertEqual(self.client.get(reverse(name)).status_code, 200, f'{user} {name}')
        self.assertEqual(Profile.objects.get(user__username='doctor').role, Profile.Role.DOCTOR)


class AuditFixTests(ScreenBase):
    """Regression tests for the final audit fixes and the late additions."""

    def other_dept(self, hospital_name='Lifeline Medical Centre', code='CAR'):
        return Department.objects.get(hospital__name=hospital_name, code=code)

    def test_admission_prefill_only_for_patients_of_this_hospital(self):
        stranger = opd_services.find_or_create_patient('Zed Stranger', '9000000001', 40, 'M')
        opd_services.book_token(stranger, self.other_dept())
        local = opd_services.find_or_create_patient('Mina Local', '9000000002', 30, 'F')
        opd_services.book_token(local, self.dept)
        self.login('reception')
        url = reverse('wards:admissions')
        self.assertNotContains(self.client.get(f'{url}?patient={stranger.pk}'), 'Zed Stranger')
        self.assertContains(self.client.get(f'{url}?patient={local.pk}'), 'Mina Local')

    def test_doctor_cannot_act_on_another_department(self):
        ort = Department.objects.get(hospital=self.hospital, code='ORT')
        token = opd_services.book_token(opd_services.find_or_create_patient('Raj Other', '9000000003', 50, 'M'), ort)
        self.login('doctor')
        res = self.client.post(reverse('opd:token_action', args=[token.pk, 'start']))
        self.assertEqual(res.status_code, 403)
        self.assertContains(res, 'This desk is for doctors', status_code=403)

    def test_stale_tokens_close_at_day_end(self):
        user = self.make_patient_user()
        token = opd_services.book_token(opd_services.patient_for_user(user, 30, 'F'), self.dept)
        Token.objects.filter(pk=token.pk).update(date=token.date.replace(year=token.date.year - 1))
        self.login('asha')
        self.assertRedirects(self.client.get(reverse('opd:my_token')), reverse('opd:book'))
        self.assertEqual(Token.objects.get(pk=token.pk).status, S.NO_SHOW)

    def test_registered_user_adopts_matching_walk_in_patient(self):
        walk_in = opd_services.find_or_create_patient('Asha', '9876543210', 30, 'F')
        user = self.make_patient_user()
        self.assertEqual(opd_services.patient_for_user(user).pk, walk_in.pk)
        self.assertEqual(Patient.objects.filter(phone='9876543210').count(), 1)

    def test_prescribe_merges_the_same_medicine_on_two_lines(self):
        from pharmacy import services as pharmacy_services
        token = opd_services.book_token(opd_services.find_or_create_patient('Pat Rx', '9000000004', 40, 'M'), self.dept)
        med = Medicine.objects.filter(hospital=self.hospital).first()
        rx = pharmacy_services.prescribe(token, None, [(med, 5), (med, 3)])
        self.assertEqual(rx.items.count(), 1)
        self.assertEqual(rx.items.first().quantity, 8)

    def test_pharmacist_can_reject_a_pending_prescription_once(self):
        from pharmacy import services as pharmacy_services
        token = opd_services.book_token(opd_services.find_or_create_patient('Pat Rj', '9000000005', 40, 'M'), self.dept)
        med = Medicine.objects.filter(hospital=self.hospital).first()
        before = med.quantity
        rx = pharmacy_services.prescribe(token, None, [(med, 2)])
        self.login('pharmacist')
        url = reverse('pharmacy:reject', args=[rx.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url)
        rx.refresh_from_db()
        med.refresh_from_db()
        self.assertEqual(rx.status, Prescription.Status.CANCELLED)
        self.assertEqual(med.quantity, before)
        self.assertContains(self.client.post(url, follow=True), 'already cancelled')

    def test_pharmacist_of_another_hospital_cannot_reject(self):
        from pharmacy import services as pharmacy_services
        token = opd_services.book_token(opd_services.find_or_create_patient('Pat Rk', '9000000006', 40, 'M'), self.dept)
        med = Medicine.objects.filter(hospital=self.hospital).first()
        rx = pharmacy_services.prescribe(token, None, [(med, 2)])
        self.login('pharmacist_lifeline')
        self.assertEqual(self.client.post(reverse('pharmacy:reject', args=[rx.pk])).status_code, 404)

    def test_withdrawn_admission_is_cancelled_not_discharged(self):
        from wards import services as ward_services
        ward = Ward.objects.filter(hospital=self.hospital).first()
        patient = opd_services.find_or_create_patient('Wil Draw', '9000000007', 40, 'M')
        adm = Admission.objects.create(patient=patient, ward=ward, status=Admission.Status.WAITING)
        ward_services.cancel_waiting(adm)
        adm.refresh_from_db()
        self.assertEqual(adm.status, Admission.Status.CANCELLED)
        self.assertIsNone(adm.discharged_at)

    def test_real_discharge_still_records_discharged_with_a_time(self):
        from wards import services as ward_services
        ward = Ward.objects.filter(hospital=self.hospital, ward_type='GENERAL').first()
        patient = opd_services.find_or_create_patient('Dee Charge', '9000000008', 40, 'M')
        adm = ward_services.admit_patient(patient, ward)
        self.assertEqual(adm.status, Admission.Status.ADMITTED)
        ward_services.discharge(adm)
        adm.refresh_from_db()
        self.assertEqual(adm.status, Admission.Status.DISCHARGED)
        self.assertIsNotNone(adm.discharged_at)

    def test_my_visits_lists_own_tokens_and_is_patient_only(self):
        user = self.make_patient_user()
        token = opd_services.book_token(opd_services.patient_for_user(user, 30, 'F'), self.dept)
        self.login('asha')
        self.assertContains(self.client.get(reverse('opd:history')), token.label)
        self.client.logout()
        self.login('reception')
        self.assertEqual(self.client.get(reverse('opd:history')).status_code, 403)

    def test_password_change_works_for_staff_and_patients(self):
        self.login('reception')
        res = self.client.post(reverse('accounts:password_change'), {
            'old_password': PW, 'new_password1': 'Sturdy-pass-2026!', 'new_password2': 'Sturdy-pass-2026!'})
        self.assertRedirects(res, reverse('accounts:password_done'))
        self.client.logout()
        self.assertTrue(self.client.login(username='reception', password='Sturdy-pass-2026!'))

    def test_admin_nav_has_no_doctor_only_links(self):
        self.login('admin')
        page = self.client.get(reverse('staff_home'))
        self.assertContains(page, 'Reception desk')
        self.assertNotContains(page, 'Consultations')
