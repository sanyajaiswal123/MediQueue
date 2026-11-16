from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Hospital(models.Model):
    """A hospital instance. Department/Doctor are added in P2."""

    name = models.CharField(max_length=150, unique=True)
    area = models.CharField(max_length=100, help_text='Locality / district in the city')
    phone = models.CharField(max_length=15, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Department(models.Model):
    """An OPD department (e.g. Cardiology) with its own daily token quota."""

    hospital = models.ForeignKey(Hospital, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=5, help_text='Short token prefix, e.g. CAR')
    avg_minutes = models.PositiveSmallIntegerField(default=10, help_text='Average consultation minutes')
    is_open = models.BooleanField(default=True)
    daily_limit = models.PositiveIntegerField(default=50, help_text='Max tokens per day')

    class Meta:
        ordering = ['hospital__name', 'name']
        constraints = [
            models.UniqueConstraint(fields=['hospital', 'name'], name='uniq_department_name_per_hospital'),
            models.UniqueConstraint(fields=['hospital', 'code'], name='uniq_department_code_per_hospital'),
        ]

    def __str__(self):
        return f'{self.name} ({self.hospital.name})'


class Doctor(models.Model):
    """A doctor: a User with the DOCTOR role, attached to one department."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='doctor')
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='doctors')
    room = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ['department', 'user__first_name']

    def __str__(self):
        return f'Dr. {self.user.get_full_name() or self.user.get_username()}'

    def clean(self):
        profile = getattr(self.user, 'profile', None)
        if profile is not None and profile.role != profile.Role.DOCTOR:
            raise ValidationError({'user': 'The user must have the Doctor role.'})

    @property
    def hospital(self):
        return self.department.hospital
