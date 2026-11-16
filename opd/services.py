"""Business logic for the OPD queue (keep views thin)."""
from django.db import transaction
from django.utils import timezone

from hospitals.models import Department

from .models import Token

Status = Token.Status


class QueueError(Exception):
    """Base class for rule violations; the message is safe to show to users."""


class ProfileIncomplete(QueueError):
    """The patient still has to give age and gender before a token can be booked."""


class DepartmentClosed(QueueError):
    pass


class QuotaExceeded(QueueError):
    pass


class DuplicateToken(QueueError):
    pass


class InvalidTransition(QueueError):
    pass


@transaction.atomic
def book_token(patient, department, is_priority=False, date=None):
    """Issue the next token number for a department.

    Rules: department must be open; the daily quota (non-cancelled tokens) must not be
    exceeded; a patient may hold only one active token per department per day.
    The department row is locked so concurrent bookings never get the same number.
    """
    date = date or timezone.localdate()
    department = Department.objects.select_for_update().get(pk=department.pk)
    if not department.is_open:
        raise DepartmentClosed(f'{department.name} is closed for new tokens.')
    todays = Token.objects.filter(department=department, date=date)
    if todays.exclude(status=Status.CANCELLED).count() >= department.daily_limit:
        raise QuotaExceeded(f'Daily limit of {department.daily_limit} tokens reached.')
    if todays.filter(patient=patient, status__in=Token.ACTIVE_STATUSES).exists():
        raise DuplicateToken('You already have an active token in this department today.')
    last = todays.order_by('-number').values_list('number', flat=True).first() or 0
    return Token.objects.create(patient=patient, department=department, number=last + 1,
                                date=date, is_priority=is_priority)


def waiting_queue(department, date=None):
    """WAITING tokens in serving order: priority first, then by token number."""
    date = date or timezone.localdate()
    return Token.objects.filter(department=department, date=date, status=Status.WAITING
                                ).order_by('-is_priority', 'number')


def people_ahead(token):
    """Tokens served before this one: waiting tokens ahead plus those already called/in consult."""
    if token.status != Status.WAITING:
        return 0
    busy = Token.objects.filter(department=token.department, date=token.date,
                                status__in=(Status.CALLED, Status.IN_CONSULT)).count()
    order = list(waiting_queue(token.department, token.date).values_list('pk', flat=True))
    return order.index(token.pk) + busy if token.pk in order else busy


def estimated_wait_minutes(token):
    """Estimated wait = people ahead x the department's average consultation time."""
    return people_ahead(token) * token.department.avg_minutes


@transaction.atomic
def call_next(department, doctor=None):
    """Call the next waiting token (priority first). Returns None when the queue is empty."""
    nxt = waiting_queue(department).select_for_update().first()
    if nxt is None:
        return None
    nxt.status = Status.CALLED
    nxt.call_count += 1
    nxt.doctor = doctor or nxt.doctor
    nxt.save(update_fields=['status', 'call_count', 'doctor'])
    return nxt


def _transition(token, allowed_from, new_status):
    """Move a token to new_status if it is currently in allowed_from."""
    with transaction.atomic():
        token = Token.objects.select_for_update().get(pk=token.pk)
        if token.status not in allowed_from:
            raise InvalidTransition(f'Cannot move a {token.get_status_display().lower()} token to {new_status}.')
        token.status = new_status
        token.save(update_fields=['status'])
    return token


def start_consultation(token):
    """CALLED -> IN_CONSULT."""
    return _transition(token, (Status.CALLED,), Status.IN_CONSULT)


def complete(token):
    """IN_CONSULT -> COMPLETED."""
    return _transition(token, (Status.IN_CONSULT,), Status.COMPLETED)


def mark_no_show(token):
    """CALLED -> NO_SHOW (patient did not turn up when called)."""
    return _transition(token, (Status.CALLED,), Status.NO_SHOW)


def cancel(token):
    """Cancel a token. Only WAITING tokens can be cancelled; once called it is too late."""
    return _transition(token, (Status.WAITING,), Status.CANCELLED)


MAX_CALLS = 3


def recall(token):
    """Call a CALLED patient again. After MAX_CALLS unanswered calls the token becomes NO_SHOW."""
    with transaction.atomic():
        token = Token.objects.select_for_update().get(pk=token.pk)
        if token.status != Status.CALLED:
            raise InvalidTransition('Only a called token can be called again.')
        if token.call_count >= MAX_CALLS:
            token.status = Status.NO_SHOW
        else:
            token.call_count += 1
        token.save(update_fields=['status', 'call_count'])
    return token


def close_stale_tokens(today=None):
    """End of day: tokens from earlier dates that were never finished become NO_SHOW. Returns how many."""
    today = today or timezone.localdate()
    return Token.objects.filter(date__lt=today, status__in=Token.ACTIVE_STATUSES).update(status=Status.NO_SHOW)


def find_or_create_patient(name, phone, age, gender):
    """Walk-in lookup: reuse the Patient with this phone and name, else create one."""
    from .models import Patient
    patient = Patient.objects.filter(phone=phone, name__iexact=name.strip()).first()
    if patient:
        return patient
    return Patient.objects.create(name=name.strip(), phone=phone, age=age, gender=gender)


def patient_for_user(user, age=None, gender=None):
    """Return the Patient linked to a login, creating it on first use from the user's name and phone.

    `age` and `gender` are required only when the Patient does not exist yet.
    """
    from .models import Patient
    patient = Patient.objects.filter(user=user).first()
    if patient:
        return patient
    name = user.get_full_name() or user.get_username()
    walk_in = Patient.objects.filter(user__isnull=True, phone=user.profile.phone, name__iexact=name).first()
    if walk_in:  # same person visited reception before: keep one record and one history
        walk_in.user = user
        walk_in.save(update_fields=['user'])
        return walk_in
    if age is None or not gender:
        raise ProfileIncomplete('Please provide your age and gender to complete your patient profile.')
    return Patient.objects.create(user=user, name=name, phone=user.profile.phone, age=age, gender=gender)


def department_load(department, date=None):
    """Aggregate queue numbers for a department (no patient data)."""
    date = date or timezone.localdate()
    todays = Token.objects.filter(department=department, date=date)
    waiting = todays.filter(status=Status.WAITING).count()
    busy = todays.filter(status__in=(Status.CALLED, Status.IN_CONSULT)).count()
    issued = todays.exclude(status=Status.CANCELLED).count()
    return {
        'waiting': waiting,
        'estimated_wait_minutes': (waiting + busy) * department.avg_minutes,
        'tokens_left': max(department.daily_limit - issued, 0),
    }
