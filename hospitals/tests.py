from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase

from accounts.models import Profile
from hospitals.models import Department, Doctor, Hospital
from wards.models import Bed

User = get_user_model()


class HospitalModelTests(TestCase):
    def setUp(self):
        self.h = Hospital.objects.create(name='H1', area='A')

    def test_department_defaults_and_str(self):
        d = Department.objects.create(hospital=self.h, name='Cardiology', code='CAR')
        self.assertEqual((d.avg_minutes, d.daily_limit, d.is_open), (10, 50, True))
        self.assertEqual(str(d), 'Cardiology (H1)')

    def test_department_code_unique_per_hospital(self):
        Department.objects.create(hospital=self.h, name='A', code='X')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Department.objects.create(hospital=self.h, name='B', code='X')
        other = Hospital.objects.create(name='H2', area='B')
        Department.objects.create(hospital=other, name='A', code='X')  # allowed

    def test_doctor_requires_doctor_role(self):
        d = Department.objects.create(hospital=self.h, name='A', code='X')
        user = User.objects.create_user('pat', password='x')
        with self.assertRaises(ValidationError):
            Doctor(user=user, department=d).clean()
        user.profile.role, user.profile.hospital = Profile.Role.DOCTOR, self.h
        user.profile.save()
        Doctor(user=user, department=d).clean()


class SeedDemoTests(TestCase):
    def test_seed_creates_data_and_is_idempotent(self):
        call_command('seed_demo', verbosity=0)
        counts = (Hospital.objects.count(), Department.objects.count(), Doctor.objects.count(), User.objects.count())
        self.assertEqual(counts[:3], (3, 12, 12))
        self.assertEqual(Bed.objects.count(), 3 * 17)
        call_command('seed_demo', verbosity=0)
        self.assertEqual(counts, (Hospital.objects.count(), Department.objects.count(),
                                  Doctor.objects.count(), User.objects.count()))

    def test_seeded_doctor_can_log_in_with_role(self):
        call_command('seed_demo', verbosity=0)
        self.assertTrue(self.client.login(username='doctor', password='demo'))
        u = User.objects.get(username='doctor')
        self.assertEqual(u.profile.role, Profile.Role.DOCTOR)
        self.assertEqual(u.doctor.hospital.name, 'City Care Hospital')
