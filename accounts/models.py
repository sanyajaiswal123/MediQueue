from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

phone_validator = RegexValidator(r'^\d{10}$', 'Enter a 10-digit phone number.')


class Profile(models.Model):
    """Role and hospital for a Django User. Created automatically by a signal."""

    class Role(models.TextChoices):
        PATIENT = 'PATIENT', 'Patient'
        RECEPTIONIST = 'RECEPTIONIST', 'Receptionist'
        DOCTOR = 'DOCTOR', 'Doctor'
        PHARMACIST = 'PHARMACIST', 'Pharmacist'
        ADMIN = 'ADMIN', 'Admin'

    STAFF_ROLES = (Role.RECEPTIONIST, Role.DOCTOR, Role.PHARMACIST)

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PATIENT)
    hospital = models.ForeignKey('hospitals.Hospital', null=True, blank=True, on_delete=models.SET_NULL, related_name='staff')
    phone = models.CharField(max_length=10, blank=True, validators=[phone_validator])

    def __str__(self):
        return f'{self.user.get_username()} ({self.get_role_display()})'

    def clean(self):
        if self.role in self.STAFF_ROLES and not self.hospital_id:
            raise ValidationError({'hospital': 'Staff roles must be assigned to a hospital.'})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.sync_group()

    def sync_group(self):
        """Keep the user in exactly one role group (used for Django permissions / Admin)."""
        from django.contrib.auth.models import Group
        role_names = [label for _, label in self.Role.choices]
        self.user.groups.remove(*Group.objects.filter(name__in=role_names))
        group, _ = Group.objects.get_or_create(name=self.get_role_display())
        self.user.groups.add(group)
