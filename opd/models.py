from django.conf import settings
from django.db import models
from django.utils import timezone


class Patient(models.Model):
    """A person seeking care. May be linked to a login (self-registered) or walk-in (no user)."""

    class Gender(models.TextChoices):
        MALE = 'M', 'Male'
        FEMALE = 'F', 'Female'
        OTHER = 'O', 'Other'

    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=10)
    age = models.PositiveSmallIntegerField()
    gender = models.CharField(max_length=1, choices=Gender.choices)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, null=True, blank=True,
                                on_delete=models.SET_NULL, related_name='patient')

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.phone})'


class Token(models.Model):
    """A queue token for one department on one day."""

    class Status(models.TextChoices):
        WAITING = 'WAITING', 'Waiting'
        CALLED = 'CALLED', 'Called'
        IN_CONSULT = 'IN_CONSULT', 'In consultation'
        COMPLETED = 'COMPLETED', 'Completed'
        NO_SHOW = 'NO_SHOW', 'No show'
        CANCELLED = 'CANCELLED', 'Cancelled'

    ACTIVE_STATUSES = (Status.WAITING, Status.CALLED, Status.IN_CONSULT)

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='tokens')
    department = models.ForeignKey('hospitals.Department', on_delete=models.CASCADE, related_name='tokens')
    doctor = models.ForeignKey('hospitals.Doctor', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='tokens')
    number = models.PositiveIntegerField()
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.WAITING)
    is_priority = models.BooleanField(default=False)
    call_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'number']
        constraints = [
            models.UniqueConstraint(fields=['department', 'date', 'number'], name='uniq_token_number_per_day'),
        ]

    @property
    def label(self):
        """Display form such as CAR-007."""
        return f'{self.department.code}-{self.number:03d}'

    def __str__(self):
        return self.label
