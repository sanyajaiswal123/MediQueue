"""Seed demo data: hospitals, departments, doctors, receptionists, pharmacists. Idempotent."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile
from hospitals.models import Department, Doctor, Hospital
from pharmacy.models import Medicine
from wards.models import Bed, Ward

User = get_user_model()
DEMO_PASSWORD = 'demo'

# Short logins for the main demo hospital (City Care); the other hospitals keep long, unambiguous names.
SHORT_LOGINS = {'reception_citycare': 'reception', 'pharmacist_citycare': 'pharmacist',
                'dr_citycare_car': 'doctor', 'patient_demo': 'patient'}

HOSPITALS = [
    {'name': 'City Care Hospital', 'area': 'Model Town', 'phone': '1800000001', 'slug': 'citycare'},
    {'name': 'Lifeline Medical Centre', 'area': 'Civil Lines', 'phone': '1800000002', 'slug': 'lifeline'},
    {'name': 'Sunrise General Hospital', 'area': 'Rajpura Road', 'phone': '1800000003', 'slug': 'sunrise'},
]

# (name, code, avg_minutes, daily_limit, doctor first/last name)
DEPARTMENTS = [
    ('General Medicine', 'GEN', 8, 60, ('Anil', 'Verma')),
    ('Cardiology', 'CAR', 15, 30, ('Meera', 'Kapoor')),
    ('Orthopaedics', 'ORT', 12, 40, ('Rohit', 'Sethi')),
    ('Paediatrics', 'PED', 10, 40, ('Sana', 'Khan')),
]

# (ward name, type, bed count)
WARDS = [('General Ward', 'GENERAL', 8), ('ICU', 'ICU', 4), ('Maternity Ward', 'MATERNITY', 5)]

# (name, category, quantity, reorder_level, days_to_expiry, unit_price) - a few are deliberately low/expiring
MEDICINES = [
    ('Paracetamol 500mg', 'Analgesic', 500, 100, 400, '1.50'),
    ('Amoxicillin 250mg', 'Antibiotic', 120, 50, 300, '6.00'),
    ('Metformin 500mg', 'Antidiabetic', 40, 60, 200, '2.50'),
    ('Atorvastatin 10mg', 'Cardiac', 30, 40, 25, '4.00'),
    ('ORS Sachet', 'Rehydration', 200, 50, 500, '12.00'),
]


class Command(BaseCommand):
    help = 'Create demo hospitals, departments and staff users (password: demo).'

    def add_arguments(self, parser):
        parser.add_argument('--activity', action='store_true',
                            help="Also create today's demo activity (tokens, admissions, prescriptions).")

    @transaction.atomic
    def handle(self, *args, **options):
        self._rename_legacy_logins()
        for h in HOSPITALS:
            hospital, _ = Hospital.objects.get_or_create(
                name=h['name'], defaults={'area': h['area'], 'phone': h['phone']})
            for name, code, avg, limit, (first, last) in DEPARTMENTS:
                dept, _ = Department.objects.get_or_create(
                    hospital=hospital, code=code,
                    defaults={'name': name, 'avg_minutes': avg, 'daily_limit': limit})
                login = f"dr_{h['slug']}_{code.lower()}"
                user = self._staff(SHORT_LOGINS.get(login, login), Profile.Role.DOCTOR, hospital, first, last)
                Doctor.objects.get_or_create(user=user, defaults={'department': dept, 'room': f'R-{code}'})
            self._wards(hospital)
            self._medicines(hospital)
            for role, key, first, last in ((Profile.Role.RECEPTIONIST, 'reception', 'Front', 'Desk'),
                                           (Profile.Role.PHARMACIST, 'pharmacist', 'Chief', 'Pharmacist')):
                login = f"{key}_{h['slug']}"
                self._staff(SHORT_LOGINS.get(login, login), role, hospital, first, last)
        self._demo_patient_and_admin(Hospital.objects.get(name=HOSPITALS[0]['name']))
        self.stdout.write(self.style.SUCCESS(
            f'Seed done: {Hospital.objects.count()} hospitals, {Department.objects.count()} departments, '
            f'{Doctor.objects.count()} doctors, {Bed.objects.count()} beds. Every demo password: {DEMO_PASSWORD}'))
        if options.get('activity'):
            self._activity()

    def _activity(self):
        """Today's demo activity through the real services. Skipped if tokens already exist today."""
        from opd import services as opd
        from opd.models import Token
        from pharmacy import services as pharmacy
        from wards import services as wards

        self._history()
        if Token.objects.filter(date=timezone.localdate()).exists():
            self.stdout.write('Activity already exists for today; skipped.')
            return
        names = [('Asha Verma', 'F'), ('Ravi Kumar', 'M'), ('Simran Kaur', 'F'), ('Imran Ali', 'M'),
                 ('Neha Gupta', 'F'), ('Arjun Mehta', 'M'), ('Pooja Rani', 'F'), ('Vikram Singh', 'M'),
                 ('Fatima Sheikh', 'F'), ('Harpreet Gill', 'M'), ('Kiran Bala', 'F'), ('Manoj Yadav', 'M'),
                 ('Sunita Devi', 'F'), ('Deepak Joshi', 'M'), ('Ananya Rao', 'F'), ('Gurpreet Sandhu', 'M'),
                 ('Meena Iyer', 'F')]
        seq = 0

        def patient():
            nonlocal seq
            seq += 1
            name, gender = names[seq % len(names)]
            return opd.find_or_create_patient(name, f'98{seq:08d}', 18 + (seq * 7) % 60, gender)

        for h_index, hospital in enumerate(Hospital.objects.order_by('name')):
            for d_index, dept in enumerate(hospital.departments.order_by('code')):
                for i in range(3 + (h_index + d_index) % 4):
                    opd.book_token(patient(), dept, is_priority=(i == 2))
                doctor = dept.doctors.first()
                done = opd.call_next(dept, doctor)
                if done:
                    opd.start_consultation(done)
                    opd.complete(done)
                    med = hospital.medicines.order_by('name').first()
                    rx = pharmacy.prescribe(done, doctor, [(med, 10)])
                    if d_index % 2:
                        pharmacy.dispense(rx)
                current = opd.call_next(dept, doctor)
                if current and d_index % 2 == 0:
                    opd.start_consultation(current)
            for ward in hospital.wards.all():
                fill = ward.beds.count() - (0 if ward.ward_type == 'ICU' else 2 + h_index)
                for i in range(fill + (2 if ward.ward_type == 'ICU' else 0)):
                    wards.admit_patient(patient(), ward, priority=(i == fill + 1))
                admitted = ward.admissions.filter(status='ADMITTED').first()
                if admitted and ward.ward_type != 'ICU':
                    wards.discharge(admitted)
        self.stdout.write(self.style.SUCCESS('Demo activity created for today.'))

    def _history(self, days=13):
        """Closed tokens for the previous `days` days (for the overview chart). Skipped if any exist."""
        from opd.models import Patient, Token

        today = timezone.localdate()
        if Token.objects.filter(date__lt=today).exists():
            return
        pool = list(Patient.objects.order_by('pk')[:40])
        if len(pool) < 10:
            for i in range(30):
                pool.append(Patient.objects.create(name=f'Visitor {i + 1}', phone=f'97{i:08d}',
                                                   age=20 + (i * 3) % 55, gender='MF'[i % 2]))
        batch = []
        for d in range(days, 0, -1):
            date = today - timedelta(days=d)
            weekday_boost = 4 if date.weekday() == 0 else -3 if date.weekday() == 6 else 0
            for h_index, hospital in enumerate(Hospital.objects.order_by('name')):
                for d_index, dept in enumerate(hospital.departments.order_by('code')):
                    n = max(2, 6 + (d * 5 + h_index * 3 + d_index * 7) % 7 + weekday_boost)
                    for k in range(1, n + 1):
                        roll = (d * 11 + k * 7 + d_index) % 20
                        status = (Token.Status.NO_SHOW if roll == 0 else
                                  Token.Status.CANCELLED if roll == 1 else Token.Status.COMPLETED)
                        batch.append(Token(patient=pool[(d * 7 + k * 3 + d_index) % len(pool)], department=dept,
                                           number=k, date=date, status=status, call_count=1))
        Token.objects.bulk_create(batch)
        self.stdout.write(f'History: {len(batch)} closed tokens over {days} days.')

    def _wards(self, hospital):
        """Create wards with numbered beds (existing beds are left untouched)."""
        for name, ward_type, count in WARDS:
            ward, _ = Ward.objects.get_or_create(hospital=hospital, name=name, defaults={'ward_type': ward_type})
            for n in range(1, count + 1):
                Bed.objects.get_or_create(ward=ward, number=str(n))

    def _medicines(self, hospital):
        """Create the demo medicine stock (existing rows are left untouched)."""
        today = timezone.localdate()
        for name, category, qty, reorder, days, price in MEDICINES:
            if Medicine.objects.filter(hospital=hospital, name=name).exists():
                continue  # expiry is relative to today, so match on name to stay idempotent across days
            Medicine.objects.get_or_create(
                hospital=hospital, name=name, expiry_date=today + timedelta(days=days),
                defaults={'category': category, 'quantity': qty, 'reorder_level': reorder, 'unit_price': price})

    def _rename_legacy_logins(self):
        """Older dev databases have the long usernames; rename them so no duplicates are created."""
        for old, new in SHORT_LOGINS.items():
            if User.objects.filter(username=old).exists() and not User.objects.filter(username=new).exists():
                User.objects.filter(username=old).update(username=new)

    def _demo_patient_and_admin(self, hospital):
        """One patient login and one admin (superuser) login, both with the demo password."""
        patient, _ = User.objects.get_or_create(username='patient', defaults={'first_name': 'Demo', 'last_name': 'Patient'})
        patient.set_password(DEMO_PASSWORD)
        patient.save()
        admin, _ = User.objects.get_or_create(username='admin', defaults={'first_name': 'Demo', 'last_name': 'Admin'})
        admin.is_staff = admin.is_superuser = True
        admin.set_password(DEMO_PASSWORD)
        admin.save()
        profile = admin.profile
        profile.role, profile.hospital = Profile.Role.ADMIN, hospital
        profile.save()

    def _staff(self, username, role, hospital, first, last):
        """Get or create a staff user with the given role and hospital (password reset to the demo one)."""
        user, _ = User.objects.get_or_create(
            username=username, defaults={'first_name': first, 'last_name': last})
        user.set_password(DEMO_PASSWORD)
        user.save()
        profile = user.profile
        profile.role, profile.hospital = role, hospital
        profile.save()
        return user
