from django.conf import settings
from django.db import models
from django.utils import timezone


class Medicine(models.Model):
    """A stocked medicine at one hospital."""

    hospital = models.ForeignKey('hospitals.Hospital', on_delete=models.CASCADE, related_name='medicines')
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=80, blank=True)
    quantity = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=20)
    expiry_date = models.DateField()
    unit_price = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    class Meta:
        ordering = ['hospital__name', 'name']
        constraints = [
            models.UniqueConstraint(fields=['hospital', 'name', 'expiry_date'], name='uniq_medicine_batch'),
        ]

    @property
    def is_expired(self):
        return self.expiry_date < timezone.localdate()

    @property
    def is_low(self):
        return self.quantity <= self.reorder_level

    def __str__(self):
        return f'{self.name} ({self.hospital.name})'


class Prescription(models.Model):
    """Medicines prescribed by a doctor for a token; dispensed by the pharmacy."""

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        DISPENSED = 'DISPENSED', 'Dispensed'
        CANCELLED = 'CANCELLED', 'Cancelled'

    token = models.ForeignKey('opd.Token', on_delete=models.CASCADE, related_name='prescriptions')
    doctor = models.ForeignKey('hospitals.Doctor', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='prescriptions')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Rx #{self.pk} for {self.token} [{self.status}]'


class PrescriptionItem(models.Model):
    prescription = models.ForeignKey(Prescription, on_delete=models.CASCADE, related_name='items')
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT, related_name='prescription_items')
    quantity = models.PositiveIntegerField()

    def __str__(self):
        return f'{self.medicine.name} x{self.quantity}'


class StockMovement(models.Model):
    """Audit trail: every stock change (positive = received, negative = dispensed/written off)."""

    class Reason(models.TextChoices):
        RECEIVED = 'RECEIVED', 'Stock received'
        DISPENSED = 'DISPENSED', 'Dispensed'
        EXPIRED = 'EXPIRED', 'Written off (expired)'
        ADJUSTMENT = 'ADJUSTMENT', 'Adjustment'

    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='movements')
    change = models.IntegerField()
    reason = models.CharField(max_length=12, choices=Reason.choices)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name='stock_movements')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-pk']

    def __str__(self):
        return f'{self.medicine.name} {self.change:+d} ({self.reason})'
