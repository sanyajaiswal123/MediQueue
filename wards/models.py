from django.db import models


class Ward(models.Model):
    """A ward inside a hospital (General, ICU, ...)."""

    class WardType(models.TextChoices):
        GENERAL = 'GENERAL', 'General'
        ICU = 'ICU', 'ICU'
        MATERNITY = 'MATERNITY', 'Maternity'
        PAEDIATRIC = 'PAEDIATRIC', 'Paediatric'

    hospital = models.ForeignKey('hospitals.Hospital', on_delete=models.CASCADE, related_name='wards')
    name = models.CharField(max_length=100)
    ward_type = models.CharField(max_length=12, choices=WardType.choices, default=WardType.GENERAL)

    class Meta:
        ordering = ['hospital__name', 'name']
        constraints = [
            models.UniqueConstraint(fields=['hospital', 'name'], name='uniq_ward_name_per_hospital'),
        ]

    def __str__(self):
        return f'{self.name} ({self.hospital.name})'


class Bed(models.Model):
    """A single bed. CLEANING beds are not assignable until marked clean."""

    class Status(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        OCCUPIED = 'OCCUPIED', 'Occupied'
        CLEANING = 'CLEANING', 'Cleaning'

    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name='beds')
    number = models.CharField(max_length=10)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)

    class Meta:
        ordering = ['ward', 'number']
        constraints = [
            models.UniqueConstraint(fields=['ward', 'number'], name='uniq_bed_number_per_ward'),
        ]

    def __str__(self):
        return f'{self.ward.name} / {self.number}'


class Admission(models.Model):
    """A request to admit a patient to a ward; WAITING until a bed is assigned."""

    class Status(models.TextChoices):
        WAITING = 'WAITING', 'Waiting for bed'
        ADMITTED = 'ADMITTED', 'Admitted'
        DISCHARGED = 'DISCHARGED', 'Discharged'
        CANCELLED = 'CANCELLED', 'Withdrawn'

    ACTIVE_STATUSES = (Status.WAITING, Status.ADMITTED)

    patient = models.ForeignKey('opd.Patient', on_delete=models.CASCADE, related_name='admissions')
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, related_name='admissions')
    bed = models.ForeignKey(Bed, null=True, blank=True, on_delete=models.SET_NULL, related_name='admissions')
    doctor = models.ForeignKey('hospitals.Doctor', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='admissions')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.WAITING)
    priority = models.BooleanField(default=False, help_text='Emergency: served first on the waiting list')
    requested_at = models.DateTimeField(auto_now_add=True)
    admitted_at = models.DateTimeField(null=True, blank=True)
    discharged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-priority', 'requested_at']

    def __str__(self):
        return f'{self.patient.name} -> {self.ward.name} [{self.status}]'
