from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

from hospitals.models import Department, Hospital
from opd import services as opd_services
from opd.models import Patient, Token

User = get_user_model()
PRIVATE_WORDS = ('phone', 'patient', 'age', 'gender', 'username')


class ApiBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', verbosity=0)
        cls.hospital = Hospital.objects.get(name='City Care Hospital')
        cls.dept = Department.objects.get(hospital=cls.hospital, code='CAR')
        cls.alice = User.objects.create_user('alice', password='pw12345!x', first_name='Alice')
        cls.alice.profile.phone = '9111111111'
        cls.alice.profile.save()
        cls.bob = User.objects.create_user('bob', password='pw12345!x', first_name='Bob')
        cls.bob.profile.phone = '9222222222'
        cls.bob.profile.save()

    def book(self, user, **extra):
        c = Client()
        c.force_login(user)
        return c, c.post(reverse('api:token-create'), {'department': self.dept.id, 'age': 30, 'gender': 'F', **extra})


class CityApiTests(ApiBase):
    def test_public_no_login_and_aggregate_only(self):
        self.book(self.alice)
        res = self.client.get(reverse('api:city-hospitals'))
        self.assertEqual(res.status_code, 200)
        row = next(h for h in res.json() if h['name'] == 'City Care Hospital')
        self.assertEqual(row['beds']['total'], 17)
        self.assertEqual(row['opd']['waiting_tokens'], 1)
        self.assertIn('low_stock_items', row['pharmacy'])
        text = res.content.decode().lower()
        for word in PRIVATE_WORDS:
            self.assertNotIn(word, text, f'public API leaks "{word}"')
        self.assertNotIn('alice', text)

    def test_inactive_hospital_hidden(self):
        Hospital.objects.filter(pk=self.hospital.pk).update(is_active=False)
        names = [h['name'] for h in self.client.get(reverse('api:city-hospitals')).json()]
        self.assertNotIn('City Care Hospital', names)
        self.assertEqual(self.client.get(reverse('api:hospital-beds', args=[self.hospital.pk])).status_code, 404)

    def test_departments_and_beds_endpoints(self):
        self.book(self.alice)
        deps = self.client.get(reverse('api:hospital-departments', args=[self.hospital.pk])).json()
        car = next(d for d in deps if d['code'] == 'CAR')
        self.assertEqual((car['waiting'], car['tokens_left']), (1, 29))
        beds = self.client.get(reverse('api:hospital-beds', args=[self.hospital.pk])).json()
        self.assertEqual((beds['total'], beds['available']), (17, 17))
        self.assertEqual(len(beds['wards']), 3)
        self.assertEqual(self.client.get(reverse('api:hospital-beds', args=[99999])).status_code, 404)


class TokenApiTests(ApiBase):
    def test_book_token_creates_patient_and_returns_position(self):
        _, res = self.book(self.alice)
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertEqual((body['label'], body['status'], body['people_ahead']), ('CAR-001', 'WAITING', 0))
        self.assertEqual(Patient.objects.get(user=self.alice).phone, '9111111111')

    def test_second_patient_sees_wait_and_priority_is_not_self_assignable(self):
        self.book(self.alice)
        _, res = self.book(self.bob, is_priority=True)
        body = res.json()
        self.assertFalse(body['is_priority'])
        self.assertEqual((body['people_ahead'], body['estimated_wait_minutes']), (1, 15))

    def test_anonymous_cannot_book(self):
        res = self.client.post(reverse('api:token-create'), {'department': self.dept.id})
        self.assertIn(res.status_code, (401, 403))
        self.assertEqual(Token.objects.count(), 0)

    def test_staff_cannot_use_patient_endpoints(self):
        c = Client()
        c.login(username='reception', password='demo')
        res = c.post(reverse('api:token-create'), {'department': self.dept.id, 'age': 1, 'gender': 'M'})
        self.assertEqual(res.status_code, 403)

    def test_missing_profile_fields_and_duplicates(self):
        c = Client()
        c.force_login(self.alice)
        res = c.post(reverse('api:token-create'), {'department': self.dept.id})
        self.assertEqual(res.status_code, 400)
        self.book(self.alice)
        _, dup = self.book(self.alice)
        self.assertEqual(dup.status_code, 409)

    def test_closed_department_rejected(self):
        Department.objects.filter(pk=self.dept.pk).update(is_open=False)
        _, res = self.book(self.alice)
        self.assertEqual(res.status_code, 409)

    def test_csrf_enforced_for_session_auth(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.alice)
        res = c.post(reverse('api:token-create'), {'department': self.dept.id, 'age': 30, 'gender': 'F'})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(Token.objects.count(), 0)


class TokenPrivacyTests(ApiBase):
    def test_owner_reads_own_token_only(self):
        ca, res = self.book(self.alice)
        tid = res.json()['id']
        self.assertEqual(ca.get(reverse('api:token-detail', args=[tid])).status_code, 200)
        cb = Client()
        cb.force_login(self.bob)
        self.assertEqual(cb.get(reverse('api:token-detail', args=[tid])).status_code, 404)
        self.assertEqual(self.client.get(reverse('api:token-detail', args=[tid])).status_code in (401, 403), True)

    def test_token_carries_pass_fields_but_no_medicines(self):
        ca, res = self.book(self.alice)
        data = ca.get(reverse('api:token-detail', args=[res.json()['id']])).json()
        self.assertEqual(data['department_code'], 'CAR')
        self.assertTrue(data['hospital_area'])
        self.assertIsNone(data['prescription'])
        self.assertNotIn('items', data)

    def test_other_patient_cannot_cancel(self):
        _, res = self.book(self.alice)
        tid = res.json()['id']
        cb = Client()
        cb.force_login(self.bob)
        self.assertEqual(cb.post(reverse('api:token-cancel', args=[tid])).status_code, 404)
        self.assertEqual(Token.objects.get(pk=tid).status, 'WAITING')

    def test_owner_cancel_then_late_cancel_conflict(self):
        ca, res = self.book(self.alice)
        tid = res.json()['id']
        out = ca.post(reverse('api:token-cancel', args=[tid]))
        self.assertEqual((out.status_code, out.json()['status']), (200, 'CANCELLED'))
        # new token that gets called can no longer be cancelled
        _, res2 = self.book(self.alice)
        opd_services.call_next(self.dept)
        late = ca.post(reverse('api:token-cancel', args=[res2.json()['id']]))
        self.assertEqual(late.status_code, 409)

    def test_unknown_url_is_404(self):
        self.assertEqual(self.client.get('/api/nope/').status_code, 404)
