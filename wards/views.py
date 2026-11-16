"""Ward screens: bed board (S7), admissions + waiting list (S8), discharge / mark clean (S9)."""
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.permissions import role_required
from opd.models import Patient
from opd.services import find_or_create_patient
from mediqueue.utils import hospital_or_404, redirect_back

from . import services
from .forms import AdmissionForm
from .models import Admission, Bed

Role = Profile.Role
WARD_ROLES = (Role.RECEPTIONIST, Role.DOCTOR, Role.ADMIN)


@role_required(*WARD_ROLES)
def board(request):
    """S7: every bed of every ward with its status (always labelled) and the patient in it."""
    hospital = hospital_or_404(request.user)
    admitted = {a.bed_id: a for a in Admission.objects.filter(
        ward__hospital=hospital, status=Admission.Status.ADMITTED).select_related('patient')}
    wards = []
    for ward in hospital.wards.prefetch_related('beds'):
        beds = list(ward.beds.all())
        for bed in beds:
            bed.admission = admitted.get(bed.pk)
        wards.append({'ward': ward, 'beds': beds,
                      'free': sum(b.status == Bed.Status.AVAILABLE for b in beds),
                      'waiting': services.waiting_list(ward).count()})
    return render(request, 'wards/board.html', {
        'hospital': hospital, 'wards': wards, 'counts': services.bed_counts(hospital)})


@role_required(*WARD_ROLES)
def admissions(request):
    """S8: request admission (auto-assigns a bed or queues) and manage each ward's waiting list."""
    hospital = hospital_or_404(request.user)
    initial = {}
    pid = request.GET.get('patient')
    if pid and pid.isdigit():
        patient = (Patient.objects.filter(pk=pid)
                   .filter(Q(tokens__department__hospital=hospital) | Q(admissions__ward__hospital=hospital))
                   .distinct().first())
        if patient:
            initial = {'name': patient.name, 'phone': patient.phone, 'age': patient.age, 'gender': patient.gender}
    doctor = getattr(request.user, 'doctor', None)
    if doctor:
        initial['doctor'] = doctor.pk
    form = AdmissionForm(request.POST or None, hospital=hospital, initial=initial)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        patient = find_or_create_patient(data['name'], data['phone'], data['age'], data['gender'])
        try:
            adm = services.admit_patient(patient, data['ward'], doctor=data['doctor'], priority=data['priority'])
        except services.WardError as exc:
            form.add_error(None, str(exc))
        else:
            if adm.status == Admission.Status.ADMITTED:
                messages.success(request, f'{patient.name} admitted to {adm.ward.name}, bed {adm.bed.number}.')
            else:
                messages.info(request, f'No free bed in {adm.ward.name}. {patient.name} is on the waiting list.')
            return redirect('wards:admissions')

    queues = [{'ward': w, 'items': list(services.waiting_list(w).select_related('patient', 'doctor__user')),
               'free': w.beds.filter(status=Bed.Status.AVAILABLE).count()} for w in hospital.wards.all()]
    return render(request, 'wards/admissions.html', {
        'hospital': hospital, 'form': form, 'queues': queues,
        'waiting_total': sum(len(q['items']) for q in queues)})


@role_required(*WARD_ROLES)
def discharges(request):
    """S9: discharge admitted patients and turn cleaned beds around (which auto-admits the next waiting)."""
    hospital = hospital_or_404(request.user)
    admitted = (Admission.objects.filter(ward__hospital=hospital, status=Admission.Status.ADMITTED)
                .select_related('patient', 'ward', 'bed', 'doctor__user').order_by('ward__name', 'admitted_at'))
    cleaning = Bed.objects.filter(ward__hospital=hospital, status=Bed.Status.CLEANING).select_related('ward')
    return render(request, 'wards/discharges.html', {
        'hospital': hospital, 'admitted': admitted, 'cleaning': cleaning})


@require_POST
@role_required(*WARD_ROLES)
def discharge(request, pk):
    hospital = hospital_or_404(request.user)
    adm = get_object_or_404(Admission, pk=pk, ward__hospital=hospital)
    try:
        adm = services.discharge(adm)
    except services.WardError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'{adm.patient.name} discharged. Bed {adm.bed.number} needs cleaning.')
    return redirect_back(request, 'wards:discharges')


@require_POST
@role_required(*WARD_ROLES)
def mark_clean(request, pk):
    hospital = hospital_or_404(request.user)
    bed = get_object_or_404(Bed, pk=pk, ward__hospital=hospital)
    try:
        nxt = services.mark_clean(bed)
    except services.WardError as exc:
        messages.error(request, str(exc))
    else:
        if nxt:
            messages.success(request, f'Bed {bed.number} is clean and was given to {nxt.patient.name} (waiting list).')
        else:
            messages.success(request, f'Bed {bed.number} in {bed.ward.name} is available.')
    return redirect_back(request, 'wards:discharges')


@require_POST
@role_required(*WARD_ROLES)
def cancel_waiting(request, pk):
    hospital = hospital_or_404(request.user)
    adm = get_object_or_404(Admission, pk=pk, ward__hospital=hospital)
    try:
        services.cancel_waiting(adm)
    except services.WardError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'Request for {adm.patient.name} withdrawn.')
    return redirect_back(request, 'wards:admissions')
