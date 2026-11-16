"""Data for the staff overview (Doctrack-style dashboard). Read-only aggregates; no business rules."""
from datetime import timedelta

from django.db.models import Count, Q
from django.urls import reverse
from django.utils import timezone

from opd import services as opd_services
from opd.models import Patient, Token
from pharmacy import services as pharmacy_services
from pharmacy.models import Prescription
from wards import services as ward_services

Status = Token.Status
HISTORY_DAYS = 14


def initials(user):
    """Two-letter avatar text for a user."""
    first, last = (user.first_name or user.username)[:1], (user.last_name or '')[:1]
    return (first + last).upper()


def greeting(now=None):
    hour = (now or timezone.localtime()).hour
    return 'Good morning' if hour < 12 else 'Good afternoon' if hour < 17 else 'Good evening'


def _arcs(segments, gap=2.5):
    """Dash arrays on a pathLength=100 path. segments: [(key, label, value)]; gaps leave room for round caps."""
    total = sum(v for _, _, v in segments)
    shown = [s for s in segments if s[2]]
    usable = 100 - gap * max(len(shown) - 1, 0)
    arcs, start = [], 0.0
    for key, label, value in segments:
        length = usable * value / total if total else 0
        arcs.append({'key': key, 'label': label, 'value': value,
                     'dash': f'{length:.2f} 200', 'offset': f'{-start:.2f}'})
        if value:
            start += length + gap
    return {'arcs': arcs, 'total': total}


def _history(tokens, today):
    """Tokens per day for the last HISTORY_DAYS days, split into completed and other."""
    start = today - timedelta(days=HISTORY_DAYS - 1)
    rows = {r['date']: r for r in tokens.filter(date__gte=start).exclude(status=Status.CANCELLED)
            .values('date').annotate(total=Count('pk'), completed=Count('pk', filter=Q(status=Status.COMPLETED)))}
    days = []
    for i in range(HISTORY_DAYS):
        d = start + timedelta(days=i)
        r = rows.get(d, {'total': 0, 'completed': 0})
        days.append({'date': d, 'total': r['total'], 'completed': r['completed'],
                     'other': r['total'] - r['completed'], 'today': d == today})
    peak = max((d['total'] for d in days), default=0) or 1
    step = max(5, -(-peak // 20) * 5)  # four ticks on multiples of 5
    scale = step * 4
    for d in days:
        d['height'] = round(d['total'] / scale * 100, 1)
    ticks = [step * f for f in (4, 3, 2, 1)]
    return days, ticks


def _live_rows(hospital, today):
    """One row per department: who is being served now, by which doctor, and who is next."""
    rows = []
    for dept in hospital.departments.prefetch_related('doctors__user'):
        serving = (Token.objects.filter(department=dept, date=today, status__in=(Status.CALLED, Status.IN_CONSULT))
                   .select_related('doctor__user').order_by('-number').first())
        nxt = opd_services.waiting_queue(dept, today).select_related('patient').first()
        doctor = (serving.doctor if serving and serving.doctor else dept.doctors.first())
        rows.append({
            'dept': dept, 'serving': serving, 'next': nxt, 'doctor': doctor,
            'initials': initials(doctor.user) if doctor else dept.code[:2],
            'load': opd_services.department_load(dept, today),
        })
    return rows


def _notices(hospital, rows, beds, pending_rx):
    """Real, actionable alerts for the welcome card."""
    notes = []
    for row in rows:
        dept, load = row['dept'], row['load']
        if dept.is_open and load['tokens_left'] <= max(3, dept.daily_limit // 10):
            notes.append({'icon': 'alert', 'strong': dept.name, 'text': f"has {load['tokens_left']} tokens left today.",
                          'href': reverse('opd:reception') + f'?dept={dept.pk}', 'cta': 'Open queue'})
    for ward in hospital.wards.all():
        waiting = ward_services.waiting_list(ward).count()
        if waiting:
            notes.append({'icon': 'bed', 'strong': ward.name, 'text': f'is full with {waiting} waiting for a bed.',
                          'href': reverse('wards:admissions'), 'cta': 'See waiting list'})
    if beds['cleaning']:
        notes.append({'icon': 'sparkles', 'strong': f"{beds['cleaning']} bed{'s' if beds['cleaning'] != 1 else ''}",
                      'text': 'waiting to be marked clean.', 'href': reverse('wards:discharges'), 'cta': 'Turn beds around'})
    low = pharmacy_services.low_stock(hospital).count()
    if low:
        notes.append({'icon': 'pill', 'strong': f'{low} medicine batch{"es" if low != 1 else ""}',
                      'text': 'at or below reorder level.', 'href': reverse('pharmacy:stock'), 'cta': 'Check stock'})
    if pending_rx:
        notes.append({'icon': 'consult', 'strong': f'{pending_rx} prescription{"s" if pending_rx != 1 else ""}',
                      'text': 'waiting at the pharmacy counter.', 'href': reverse('pharmacy:dispense_list'),
                      'cta': 'Open dispense'})
    return notes


def _allowed_urls(user):
    """URLs of the staff screens this user's role may open (same rules as the sidebar)."""
    from accounts.permissions import user_role
    from .context_processors import NAV
    role = user_role(user)
    return {reverse(name) for name, _, _, roles in NAV if user.is_superuser or role in roles}


def overview(hospital, user):
    """Everything the staff overview template needs."""
    today = timezone.localdate()
    allowed = _allowed_urls(user)
    tokens = Token.objects.filter(department__hospital=hospital)
    todays = tokens.filter(date=today)
    counts = todays.aggregate(
        issued=Count('pk', filter=~Q(status=Status.CANCELLED)),
        completed=Count('pk', filter=Q(status=Status.COMPLETED)),
        busy=Count('pk', filter=Q(status__in=(Status.CALLED, Status.IN_CONSULT))),
        waiting=Count('pk', filter=Q(status=Status.WAITING)),
        no_show=Count('pk', filter=Q(status=Status.NO_SHOW)),
    )
    days, ticks = _history(tokens, today)
    capacity = sum(d.daily_limit for d in hospital.departments.filter(is_open=True))
    beds = ward_services.bed_counts(hospital)
    rows = _live_rows(hospital, today)
    pending_rx = Prescription.objects.filter(token__department__hospital=hospital,
                                             status=Prescription.Status.PENDING).count()

    patient_ids = list(todays.values_list('patient_id', flat=True).distinct())
    returning = (Token.objects.filter(patient_id__in=patient_ids, date__lt=today)
                 .values('patient_id').distinct().count())
    genders = dict(Patient.objects.filter(pk__in=patient_ids).values_list('gender').annotate(n=Count('pk')))
    people = len(patient_ids)
    women, men = genders.get('F', 0), genders.get('M', 0)

    serving_now = (todays.filter(status__in=(Status.CALLED, Status.IN_CONSULT))
                   .select_related('department').order_by('-pk').first())
    longest = max((r['load']['estimated_wait_minutes'] for r in rows if r['dept'].is_open), default=0)
    return {
        'hospital': hospital,
        'today': today,
        'greeting': greeting(),
        'first_name': user.first_name or user.username,
        'counts': counts,
        'capacity_pct': round(counts['issued'] / capacity * 100) if capacity else 0,
        'longest_wait': longest,
        'beds': beds,
        'occupancy': round(beds['occupied'] / beds['total'] * 100) if beds['total'] else 0,
        'rows': rows,
        'queue': _arcs([('completed', 'Completed', counts['completed']),
                        ('busy', 'In consultation', counts['busy']),
                        ('waiting', 'Waiting', counts['waiting'])]),
        'days': days,
        'ticks': ticks,
        'fortnight_total': sum(d['total'] for d in days),
        'people': people,
        'new_pct': round((people - returning) / people * 100) if people else 0,
        'new': people - returning,
        'returning': returning,
        'gender': _arcs([('women', 'Women', women), ('men', 'Men', men)], gap=4),
        'women': women,
        'men': men,
        'women_pct': round(women / people * 100) if people else 0,
        'serving_now': serving_now,
        'notices': [n for n in _notices(hospital, rows, beds, pending_rx) if n['href'].split('?')[0] in allowed],
        'can_reception': reverse('opd:reception') in allowed,
        'pending_rx': pending_rx,
    }
