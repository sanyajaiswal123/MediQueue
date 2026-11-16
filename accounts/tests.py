from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from hospitals.models import Hospital

from .forms import PatientRegistrationForm
from .models import Profile
from .permissions import role_required

R = Profile.Role


class ProfileTests(TestCase):
    def test_profile_auto_created_as_patient(self):
        u = User.objects.create_user('p1', password='x')
        self.assertEqual(u.profile.role, R.PATIENT)

    def test_superuser_is_admin(self):
        u = User.objects.create_superuser('boss', password='x')
        self.assertEqual(u.profile.role, R.ADMIN)

    def test_role_groups_exist_and_user_in_one_group(self):
        self.assertEqual(Group.objects.filter(name__in=[l for _, l in R.choices]).count(), 5)
        u = User.objects.create_user('d1', password='x')
        u.profile.role = R.DOCTOR
        u.profile.hospital = Hospital.objects.create(name='H', area='A')
        u.profile.save()
        self.assertEqual(list(u.groups.values_list('name', flat=True)), ['Doctor'])

    def test_staff_role_requires_hospital(self):
        u = User.objects.create_user('r1', password='x')
        u.profile.role = R.RECEPTIONIST
        with self.assertRaises(ValidationError):
            u.profile.full_clean()


class RegistrationTests(TestCase):
    data = {'username': 'sam', 'first_name': 'Sam', 'email': '', 'phone': '9876543210',
            'password1': 'Str0ng!pass42', 'password2': 'Str0ng!pass42'}

    def test_form_valid_creates_patient_with_phone(self):
        form = PatientRegistrationForm(self.data)
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.profile.role, R.PATIENT)
        self.assertEqual(user.profile.phone, '9876543210')

    def test_bad_phone_rejected(self):
        self.assertFalse(PatientRegistrationForm({**self.data, 'phone': '12345'}).is_valid())

    def test_password_mismatch_rejected(self):
        self.assertFalse(PatientRegistrationForm({**self.data, 'password2': 'nope'}).is_valid())

    def test_register_view_logs_in_and_redirects(self):
        resp = self.client.post(reverse('accounts:register'), self.data)
        self.assertRedirects(resp, reverse('home'))
        self.assertEqual(int(self.client.session['_auth_user_id']), User.objects.get(username='sam').pk)

    def test_csrf_enforced(self):
        from django.test import Client
        resp = Client(enforce_csrf_checks=True).post(reverse('accounts:register'), self.data)
        self.assertEqual(resp.status_code, 403)


class RoleRequiredTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.view = role_required(R.DOCTOR)(lambda request: HttpResponse('ok'))

    def _req(self, user):
        req = self.rf.get('/x/')
        req.user = user
        return req

    def test_anonymous_redirected_to_login(self):
        resp = self.view(self._req(AnonymousUser()))
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp.url)

    def test_wrong_role_forbidden(self):
        patient = User.objects.create_user('p', password='x')
        with self.assertRaises(PermissionDenied):
            self.view(self._req(patient))

    def test_right_role_allowed(self):
        doc = User.objects.create_user('d', password='x')
        doc.profile.role = R.DOCTOR
        doc.profile.save()
        self.assertEqual(self.view(self._req(doc)).status_code, 200)

    def test_superuser_allowed(self):
        su = User.objects.create_superuser('su', password='x')
        self.assertEqual(self.view(self._req(su)).status_code, 200)


class StaffHomeTests(TestCase):
    """The staff shell page is role-gated and renders the sidebar."""

    def setUp(self):
        self.hospital = Hospital.objects.create(name='Test Hospital', area='Jalandhar')

    def _login(self, username, role):
        user = User.objects.create_user(username, password='pw12345')
        profile = user.profile
        profile.role = role
        if role != Profile.Role.PATIENT:
            profile.hospital = self.hospital
        profile.save()
        self.client.login(username=username, password='pw12345')

    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse('staff_home'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response['Location'])

    def test_patient_forbidden(self):
        self._login('pat', Profile.Role.PATIENT)
        self.assertEqual(self.client.get(reverse('staff_home')).status_code, 403)

    def test_staff_sees_sidebar(self):
        self._login('rec', Profile.Role.RECEPTIONIST)
        response = self.client.get(reverse('staff_home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-sidebar')


class AuthPagesTests(TestCase):
    """Login and register pages render; login routes by role."""

    def test_pages_render(self):
        for name in ('accounts:login', 'accounts:register'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_staff_login_goes_to_staff_portal(self):
        hospital = Hospital.objects.create(name='H', area='A')
        user = User.objects.create_user('doc', password='pw12345')
        user.profile.role = Profile.Role.DOCTOR
        user.profile.hospital = hospital
        user.profile.save()
        resp = self.client.post(reverse('accounts:login'), {'username': 'doc', 'password': 'pw12345'})
        self.assertRedirects(resp, reverse('staff_home'))

    def test_patient_login_goes_home(self):
        User.objects.create_user('pat2', password='pw12345')
        resp = self.client.post(reverse('accounts:login'), {'username': 'pat2', 'password': 'pw12345'})
        self.assertRedirects(resp, reverse('home'), fetch_redirect_response=False)


class DemoLockTests(TestCase):
    def test_locked_demo_user_cannot_change_password(self):
        from django.contrib.auth.models import User
        from django.test import override_settings
        User.objects.create_user('patient', password='demo')
        self.client.login(username='patient', password='demo')
        with override_settings(DEMO_LOCKED_USERS=['patient']):
            self.assertEqual(self.client.get('/accounts/password/').status_code, 403)
        self.assertEqual(self.client.get('/accounts/password/').status_code, 200)
