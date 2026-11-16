"""Business logic for pharmacy stock and dispensing (keep views thin)."""
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Medicine, Prescription, PrescriptionItem, StockMovement

Reason = StockMovement.Reason
RxStatus = Prescription.Status


class PharmacyError(Exception):
    """Base class for rule violations; the message is safe to show to users."""


class InsufficientStock(PharmacyError):
    pass


class ExpiredMedicine(PharmacyError):
    pass


class InvalidPrescription(PharmacyError):
    pass


@transaction.atomic
def receive_stock(medicine, quantity, user=None):
    """Add stock to a medicine and record a RECEIVED movement."""
    if quantity <= 0:
        raise PharmacyError('Quantity received must be positive.')
    Medicine.objects.filter(pk=medicine.pk).update(quantity=F('quantity') + quantity)
    StockMovement.objects.create(medicine=medicine, change=quantity, reason=Reason.RECEIVED, performed_by=user)
    medicine.refresh_from_db()
    return medicine


@transaction.atomic
def prescribe(token, doctor, items):
    """Create a PENDING prescription for a token from [(medicine, quantity), ...].

    Returns None when `items` is empty. Every medicine must belong to the token's hospital.
    """
    items = [(med, qty) for med, qty in items if med and qty]
    if not items:
        return None
    merged = {}
    for med, qty in items:
        merged.setdefault(med.pk, [med, 0])[1] += qty
    items = [(med, qty) for med, qty in merged.values()]
    hospital_id = token.department.hospital_id
    for med, _ in items:
        if med.hospital_id != hospital_id:
            raise InvalidPrescription(f'{med.name} is not stocked by this hospital.')
    prescription = Prescription.objects.create(token=token, doctor=doctor)
    PrescriptionItem.objects.bulk_create(
        PrescriptionItem(prescription=prescription, medicine=med, quantity=qty) for med, qty in items)
    return prescription


@transaction.atomic
def dispense(prescription, user=None):
    """Dispense every item of a PENDING prescription, all or nothing.

    Checks: medicine belongs to the token's hospital, is not expired, and has enough stock.
    Stock is deducted with a guarded F() update, so concurrent dispenses cannot drive it
    below zero. Any failure rolls the whole transaction back (no partial dispensing).
    """
    prescription = Prescription.objects.select_for_update().get(pk=prescription.pk)
    if prescription.status != RxStatus.PENDING:
        raise InvalidPrescription(f'Prescription is already {prescription.get_status_display().lower()}.')
    items = list(prescription.items.select_related('medicine'))
    if not items:
        raise InvalidPrescription('Prescription has no items.')
    hospital_id = prescription.token.department.hospital_id
    today = timezone.localdate()
    for item in items:
        med = item.medicine
        if med.hospital_id != hospital_id:
            raise InvalidPrescription(f'{med.name} is not stocked by this hospital.')
        if med.expiry_date < today:
            raise ExpiredMedicine(f'{med.name} expired on {med.expiry_date:%d %b %Y}.')
        updated = Medicine.objects.filter(pk=med.pk, quantity__gte=item.quantity).update(
            quantity=F('quantity') - item.quantity)
        if not updated:
            raise InsufficientStock(f'Not enough {med.name} in stock (need {item.quantity}).')
        StockMovement.objects.create(medicine=med, change=-item.quantity, reason=Reason.DISPENSED,
                                     performed_by=user)
    prescription.status = RxStatus.DISPENSED
    prescription.save(update_fields=['status'])
    return prescription


@transaction.atomic
def reject(prescription, user=None):
    """Pharmacist refuses a PENDING prescription it cannot fill (expired, out of stock). Stock is untouched."""
    prescription = Prescription.objects.select_for_update().get(pk=prescription.pk)
    if prescription.status != RxStatus.PENDING:
        raise InvalidPrescription(f'Prescription is already {prescription.get_status_display().lower()}.')
    prescription.status = RxStatus.CANCELLED
    prescription.save(update_fields=['status'])
    return prescription


def low_stock(hospital):
    """Medicines at or below their reorder level (not expired), lowest quantity first."""
    return Medicine.objects.filter(hospital=hospital, quantity__lte=F('reorder_level'),
                                   expiry_date__gte=timezone.localdate()).order_by('quantity', 'name')


def expired(hospital):
    """Expired medicines that still have stock on the shelf."""
    return Medicine.objects.filter(hospital=hospital, expiry_date__lt=timezone.localdate(), quantity__gt=0)


def expiring_soon(hospital, days=30):
    """Unexpired medicines with stock expiring within `days` days."""
    today = timezone.localdate()
    return Medicine.objects.filter(hospital=hospital, quantity__gt=0, expiry_date__gte=today,
                                   expiry_date__lte=today + timedelta(days=days)).order_by('expiry_date')


@transaction.atomic
def write_off_expired(hospital, user=None):
    """Zero out expired stock, recording an EXPIRED movement per medicine. Returns count written off."""
    count = 0
    for med in expired(hospital).select_for_update():
        StockMovement.objects.create(medicine=med, change=-med.quantity, reason=Reason.EXPIRED, performed_by=user)
        Medicine.objects.filter(pk=med.pk).update(quantity=0)
        count += 1
    return count
