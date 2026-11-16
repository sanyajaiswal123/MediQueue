"""Business logic for wards, beds and admissions (keep views thin)."""
from django.db import transaction
from django.utils import timezone

from .models import Admission, Bed

AdmStatus = Admission.Status
BedStatus = Bed.Status


class WardError(Exception):
    """Base class for rule violations; the message is safe to show to users."""


class AlreadyAdmitted(WardError):
    pass


class InvalidAdmissionState(WardError):
    pass


class InvalidBedState(WardError):
    pass


def _assign_free_bed(admission):
    """Give `admission` the first AVAILABLE bed of its ward, if any. Caller must be in a transaction.

    The bed row is locked (select_for_update) so two requests can never take the same bed.
    """
    bed = (Bed.objects.select_for_update()
           .filter(ward=admission.ward, status=BedStatus.AVAILABLE).order_by('number').first())
    if bed is None:
        return False
    bed.status = BedStatus.OCCUPIED
    bed.save(update_fields=['status'])
    admission.bed = bed
    admission.status = AdmStatus.ADMITTED
    admission.admitted_at = timezone.now()
    admission.save(update_fields=['bed', 'status', 'admitted_at'])
    return True


@transaction.atomic
def admit_patient(patient, ward, doctor=None, priority=False):
    """Request admission. A free bed is assigned immediately, otherwise the patient waits.

    Returns the Admission (status ADMITTED or WAITING). A patient can hold only one active admission.
    """
    if Admission.objects.filter(patient=patient, status__in=Admission.ACTIVE_STATUSES).exists():
        raise AlreadyAdmitted(f'{patient.name} already has an active admission.')
    admission = Admission.objects.create(patient=patient, ward=ward, doctor=doctor, priority=priority)
    _assign_free_bed(admission)
    return admission


def waiting_list(ward):
    """WAITING admissions for a ward: emergencies first, then first come first served."""
    return Admission.objects.filter(ward=ward, status=AdmStatus.WAITING).order_by('-priority', 'requested_at', 'pk')


@transaction.atomic
def allocate_waiting(ward):
    """Assign free beds to the waiting list in order. Returns the list of admissions admitted."""
    admitted = []
    for admission in waiting_list(ward).select_for_update():
        if not _assign_free_bed(admission):
            break
        admitted.append(admission)
    return admitted


@transaction.atomic
def discharge(admission):
    """Discharge an ADMITTED patient; the bed moves to CLEANING (not reusable until marked clean)."""
    admission = Admission.objects.select_for_update().get(pk=admission.pk)
    if admission.status != AdmStatus.ADMITTED:
        raise InvalidAdmissionState(f'Cannot discharge: admission is {admission.get_status_display().lower()}.')
    bed = Bed.objects.select_for_update().get(pk=admission.bed_id)
    bed.status = BedStatus.CLEANING
    bed.save(update_fields=['status'])
    admission.status = AdmStatus.DISCHARGED
    admission.discharged_at = timezone.now()
    admission.save(update_fields=['status', 'discharged_at'])
    return admission


@transaction.atomic
def mark_clean(bed):
    """CLEANING -> AVAILABLE, then give the bed to the next waiting patient. Returns the admission or None."""
    bed = Bed.objects.select_for_update().get(pk=bed.pk)
    if bed.status != BedStatus.CLEANING:
        raise InvalidBedState(f'Bed {bed.number} is {bed.get_status_display().lower()}, not awaiting cleaning.')
    bed.status = BedStatus.AVAILABLE
    bed.save(update_fields=['status'])
    admitted = allocate_waiting(bed.ward)
    return admitted[0] if admitted else None


@transaction.atomic
def cancel_waiting(admission):
    """Withdraw a WAITING admission request. It stays on record as CANCELLED, never as a discharge."""
    admission = Admission.objects.select_for_update().get(pk=admission.pk)
    if admission.status != AdmStatus.WAITING:
        raise InvalidAdmissionState('Only waiting requests can be withdrawn.')
    admission.status = AdmStatus.CANCELLED
    admission.save(update_fields=['status'])
    return admission


def bed_counts(hospital):
    """Aggregate bed numbers for a hospital: {'total','available','occupied','cleaning','waiting'}."""
    beds = Bed.objects.filter(ward__hospital=hospital)
    return {
        'total': beds.count(),
        'available': beds.filter(status=BedStatus.AVAILABLE).count(),
        'occupied': beds.filter(status=BedStatus.OCCUPIED).count(),
        'cleaning': beds.filter(status=BedStatus.CLEANING).count(),
        'waiting': Admission.objects.filter(ward__hospital=hospital, status=AdmStatus.WAITING).count(),
    }
