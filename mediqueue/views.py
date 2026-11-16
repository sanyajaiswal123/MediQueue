from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from accounts.permissions import role_required
from hospitals.models import Department, Hospital
from mediqueue import dashboard
from mediqueue.utils import hospital_or_404
from opd import services as opd_services
from opd.models import Token
from pharmacy import services as pharmacy_services
from pharmacy.models import Medicine
from wards.models import Admission, Bed

Status = Token.Status


def home(request):
    """S1: public landing page with live city-wide numbers (aggregates only)."""
    today = timezone.localdate()
    tokens = Token.objects.filter(date=today)
    stats = {
        'hospitals': Hospital.objects.filter(is_active=True).count(),
        'beds_free': Bed.objects.filter(ward__hospital__is_active=True, status=Bed.Status.AVAILABLE).count(),
        'beds_total': Bed.objects.filter(ward__hospital__is_active=True).count(),
        'waiting': tokens.filter(status=Status.WAITING).count(),
        'served': tokens.filter(status=Status.COMPLETED).count(),
        'departments': Department.objects.filter(hospital__is_active=True, is_open=True).count(),
    }
    ticker = []
    for dept in Department.objects.filter(hospital__is_active=True, is_open=True).select_related('hospital'):
        load = opd_services.department_load(dept)
        ticker.append({'code': dept.code, 'name': dept.name, 'hospital': dept.hospital.name,
                       'wait': load['estimated_wait_minutes'], 'waiting': load['waiting'],
                       'left': load['tokens_left']})
    bookable = [t for t in ticker if t['left']]
    stats['shortest'] = min(bookable, key=lambda t: t['wait']) if bookable else None
    stats['tokens_left'] = sum(t['left'] for t in ticker)
    stats['low_stock'] = sum(pharmacy_services.low_stock(h).count() for h in Hospital.objects.filter(is_active=True))
    # Aggregates only: admission queue length and shelf health (never names or per-patient rows).
    active = Hospital.objects.filter(is_active=True)
    stats['admissions_waiting'] = Admission.objects.filter(ward__hospital__in=active, status=Admission.Status.WAITING).count()
    stats['medicines_in_stock'] = Medicine.objects.filter(
        hospital__in=active, quantity__gt=0, expiry_date__gte=today).values('name').distinct().count()
    stats['expiring'] = sum(pharmacy_services.expiring_soon(h).count() for h in active)
    # An empty queue is good news, not a broken page: the hero says so instead of showing 0 min.
    stats['quiet'] = stats['waiting'] == 0
    roles = [
        ('Patient', 'Book a token', reverse('opd:book')),
        ('Reception · Doctor', 'Run the queue', reverse('accounts:login')),
        ('Wards · Pharmacy', 'Beds and stock', reverse('accounts:login')),
        ('Anyone', 'City dashboard', reverse('city')),
    ]
    return render(request, 'home.html', {'stats': stats, 'ticker': ticker, 'roles': roles})


def city(request):
    """S12: City Dashboard (React widget reading the public API)."""
    return render(request, 'city.html')


@role_required(Profile.Role.RECEPTIONIST, Profile.Role.DOCTOR, Profile.Role.PHARMACIST, Profile.Role.ADMIN)
def staff_home(request):
    """Staff overview (Doctrack-style): stats, live queue, queue status, 14-day chart, patients, notices."""
    hospital = hospital_or_404(request.user)
    return render(request, 'staff/home.html', dashboard.overview(hospital, request.user))
