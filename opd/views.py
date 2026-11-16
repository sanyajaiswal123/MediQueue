"""OPD screens: patient booking (S3) and tracker (S4), reception desk (S5), doctor console (S6)."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.permissions import role_required, staff_hospital, user_role
from hospitals.models import Hospital
from mediqueue.utils import hospital_or_404, redirect_back
from pharmacy import services as pharmacy_services
from pharmacy.models import Prescription

from . import services
from .forms import BookTokenForm, PrescriptionFormSet, WalkInForm
from .models import Patient, Token

Role = Profile.Role
Status = Token.Status
PREFERRED_HOSPITAL_COOKIE = 'preferred_hospital'
ACTIVE_TOKEN_SESSION_KEY = 'active_token_id'
COOKIE_AGE = 60 * 60 * 24 * 180


# ---------- helpers ----------

def _queue_rows(department):
    """Today's live queue for a department: busy tokens first, then the waiting line with estimates."""
    today = timezone.localdate()
    busy = list(Token.objects.filter(department=department, date=today,
                                     status__in=(Status.CALLED, Status.IN_CONSULT))
                .select_related('patient', 'doctor__user').order_by('-status', 'number'))
    waiting = list(services.waiting_queue(department).select_related('patient'))
    for i, token in enumerate(waiting):
        token.position = i + 1
        token.wait = (i + len(busy)) * department.avg_minutes
    return busy, waiting


# ---------- patient (S3, S4) ----------

def _pick_hospital(request):
    """Hospital from ?hospital=, else the preferred-hospital cookie, else the first active one."""
    hospitals = Hospital.objects.filter(is_active=True)
    wanted = request.GET.get('hospital') or request.COOKIES.get(PREFERRED_HOSPITAL_COOKIE)
    hospital = hospitals.filter(pk=wanted).first() if wanted and str(wanted).isdigit() else None
    return hospital or hospitals.first(), hospitals


@role_required(Role.PATIENT)
def book(request):
    """S3: choose hospital + department and book a token (POST-redirect-GET to the tracker)."""
    hospital, hospitals = _pick_hospital(request)
    if hospital is None:
        raise Http404('No hospitals yet.')
    services.close_stale_tokens()
    patient = Patient.objects.filter(user=request.user).first()
    form = BookTokenForm(request.POST or None, hospital=hospital, needs_profile=patient is None)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            patient = patient or services.patient_for_user(request.user, data.get('age'), data.get('gender'))
            token = services.book_token(patient, data['department'])
        except services.QueueError as exc:
            form.add_error(None, str(exc))
        else:
            request.session[ACTIVE_TOKEN_SESSION_KEY] = token.pk
            response = redirect(f"{reverse('opd:track', kwargs={'pk': token.pk})}?new=1")
            response.set_cookie(PREFERRED_HOSPITAL_COOKIE, hospital.pk, max_age=COOKIE_AGE, samesite='Lax')
            return response

    selected = str(form['department'].value() or '')
    departments = []
    for dept in hospital.departments.all():
        load = services.department_load(dept)
        fill = round(10 * load['tokens_left'] / dept.daily_limit) if dept.daily_limit else 0
        departments.append({'dept': dept, 'load': load, 'selected': selected == str(dept.pk),
                            'bookable': dept.is_open and load['tokens_left'] > 0, 'fill': fill})
    active = (Token.objects.filter(patient=patient, date=timezone.localdate(), status__in=Token.ACTIVE_STATUSES)
              .select_related('department') if patient else [])
    response = render(request, 'opd/book.html', {
        'form': form, 'hospital': hospital, 'hospitals': hospitals, 'departments': departments,
        'active_tokens': active, 'needs_profile': patient is None,
    })
    if request.GET.get('hospital'):
        response.set_cookie(PREFERRED_HOSPITAL_COOKIE, hospital.pk, max_age=COOKIE_AGE, samesite='Lax')
    return response


@role_required(Role.PATIENT)
def track(request, pk):
    """S4: live tracker for the patient's own token (React widget, server-rendered fallback)."""
    services.close_stale_tokens()
    token = get_object_or_404(Token.objects.select_related('department__hospital', 'doctor'),
                              pk=pk, patient__user=request.user)
    if token.status in Token.ACTIVE_STATUSES:
        request.session[ACTIVE_TOKEN_SESSION_KEY] = token.pk
    return render(request, 'opd/track.html', {
        'token': token,
        'people_ahead': services.people_ahead(token),
        'wait': services.estimated_wait_minutes(token),
    })


@role_required(Role.PATIENT)
def my_token(request):
    """Jump to the active token kept in the session, else today's latest active token, else booking."""
    services.close_stale_tokens()
    mine = Token.objects.filter(patient__user=request.user, status__in=Token.ACTIVE_STATUSES)
    token = mine.filter(pk=request.session.get(ACTIVE_TOKEN_SESSION_KEY)).first() \
        or mine.filter(date=timezone.localdate()).order_by('-created_at').first()
    if token is None:
        request.session.pop(ACTIVE_TOKEN_SESSION_KEY, None)
        return redirect('opd:book')
    return redirect('opd:track', pk=token.pk)


@role_required(Role.PATIENT)
def history(request):
    """The patient's own visits, newest first, with prescription status (never the medicines)."""
    services.close_stale_tokens()
    visits = list(Token.objects.filter(patient__user=request.user)
                  .select_related('department__hospital').prefetch_related('prescriptions')
                  .order_by('-date', '-created_at')[:50])
    for token in visits:
        live = [p for p in token.prescriptions.all() if p.status != Prescription.Status.CANCELLED]
        token.rx_status = live[0].get_status_display() if live else ''
    return render(request, 'opd/history.html', {'visits': visits})


# ---------- reception (S5) ----------

@role_required(Role.RECEPTIONIST, Role.ADMIN)
def reception(request):
    """S5: register a walk-in and issue a token; see and manage each department's live queue."""
    hospital = hospital_or_404(request.user)
    form = WalkInForm(request.POST or None, hospital=hospital)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        patient = services.find_or_create_patient(data['name'], data['phone'], data['age'], data['gender'])
        try:
            token = services.book_token(patient, data['department'], is_priority=data['is_priority'])
        except services.QueueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f'Token {token.label} issued to {patient.name}.')
            return redirect(f"{reverse('opd:reception')}?dept={token.department_id}")

    departments = list(hospital.departments.all())
    wanted = request.GET.get('dept') or (form['department'].value() if request.method == 'POST' else None)
    current = next((d for d in departments if str(d.pk) == str(wanted)), departments[0] if departments else None)
    tabs = [{'dept': d, 'load': services.department_load(d)} for d in departments]
    busy, waiting = _queue_rows(current) if current else ([], [])
    return render(request, 'opd/reception.html', {
        'form': form, 'hospital': hospital, 'tabs': tabs, 'current': current,
        'busy': busy, 'waiting': waiting,
    })


# ---------- doctor (S6) ----------

def _doctor_or_403(user):
    doctor = getattr(user, 'doctor', None)
    if doctor is None:
        raise PermissionDenied("doctors, because it runs from a doctor's own department and room")
    return doctor


@role_required(Role.DOCTOR)
def console(request):
    """S6: call the next patient, run the consultation, write a prescription and complete."""
    doctor = _doctor_or_403(request.user)
    dept = doctor.department
    today = timezone.localdate()
    current = (Token.objects.filter(department=dept, date=today, doctor=doctor,
                                    status__in=(Status.CALLED, Status.IN_CONSULT))
               .select_related('patient').order_by('number').first())
    formset = PrescriptionFormSet(request.POST or None, prefix='rx', form_kwargs={'hospital': dept.hospital})

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'call_next':
            if current:
                messages.error(request, f'Finish {current.label} before calling the next patient.')
            else:
                called = services.call_next(dept, doctor)
                if called:
                    messages.success(request, f'{called.label} called to room {doctor.room or "-"}.')
                else:
                    messages.info(request, 'Nobody is waiting.')
            return redirect('opd:console')
        if action == 'complete' and current and current.status == Status.IN_CONSULT and formset.is_valid():
            items = [(f.cleaned_data.get('medicine'), f.cleaned_data.get('quantity')) for f in formset]
            try:
                with transaction.atomic():
                    rx = pharmacy_services.prescribe(current, doctor, items)
                    services.complete(current)
            except (pharmacy_services.PharmacyError, services.QueueError) as exc:
                messages.error(request, str(exc))
            else:
                note = ' Prescription sent to the pharmacy.' if rx else ''
                messages.success(request, f'{current.label} completed.{note}')
                return redirect('opd:console')

    busy, waiting = _queue_rows(dept)
    todays = Token.objects.filter(department=dept, date=today)
    return render(request, 'opd/console.html', {
        'doctor': doctor, 'dept': dept, 'current': current, 'formset': formset, 'waiting': waiting,
        'max_calls': services.MAX_CALLS,
        'stats': {
            'waiting': len(waiting),
            'seen': todays.filter(doctor=doctor, status=Status.COMPLETED).count(),
            'no_show': todays.filter(status=Status.NO_SHOW).count(),
            'avg': dept.avg_minutes,
        },
    })


# ---------- token actions (POST only) ----------

TOKEN_ACTIONS = {
    # action: (service, roles allowed)
    'cancel': (services.cancel, {Role.RECEPTIONIST, Role.ADMIN}),
    'no_show': (services.mark_no_show, {Role.RECEPTIONIST, Role.DOCTOR, Role.ADMIN}),
    'recall': (services.recall, {Role.DOCTOR}),
    'start': (services.start_consultation, {Role.DOCTOR}),
}


@require_POST
@role_required(Role.RECEPTIONIST, Role.DOCTOR, Role.ADMIN)
def token_action(request, pk, action):
    """Apply one queue transition to a token of the staff member's own hospital."""
    if action not in TOKEN_ACTIONS:
        raise Http404
    service, roles = TOKEN_ACTIONS[action]
    if not request.user.is_superuser and user_role(request.user) not in roles:
        raise PermissionDenied
    token = get_object_or_404(Token.objects.select_related('department'), pk=pk,
                              department__hospital=staff_hospital(request.user))
    if not request.user.is_superuser and user_role(request.user) == Role.DOCTOR:
        doctor = getattr(request.user, 'doctor', None)
        if doctor is None or token.department_id != doctor.department_id or (token.doctor_id and token.doctor_id != doctor.pk):
            raise PermissionDenied('doctors of that department, for the patients they called')
    try:
        token = service(token)
    except services.QueueError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'{token.label}: {token.get_status_display().lower()}.')
    return redirect_back(request, 'staff_home')
