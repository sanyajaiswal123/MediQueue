"""Pharmacy screens: dispense prescriptions (S10), stock list and alerts (S11)."""
from datetime import timedelta

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import Profile
from accounts.permissions import role_required
from mediqueue.utils import hospital_or_404

from . import services
from .forms import ReceiveStockForm
from .models import Medicine, Prescription, StockMovement

Role = Profile.Role
PHARMACY_ROLES = (Role.PHARMACIST, Role.ADMIN)


@role_required(*PHARMACY_ROLES)
def dispense_list(request):
    """S10: pending prescriptions with a per-item stock check, plus today's dispensed ones."""
    hospital = hospital_or_404(request.user)
    rx = (Prescription.objects.filter(token__department__hospital=hospital)
          .select_related('token__patient', 'token__department', 'doctor__user')
          .prefetch_related('items__medicine'))
    today = timezone.localdate()
    pending = list(rx.filter(status=Prescription.Status.PENDING).order_by('created_at'))
    for p in pending:
        p.problems = []
        for item in p.items.all():
            med = item.medicine
            if med.expiry_date < today:
                item.issue = 'Expired'
            elif med.quantity < item.quantity:
                item.issue = f'Only {med.quantity} left'
            else:
                item.issue = ''
            if item.issue:
                p.problems.append(item.issue)
    done = rx.filter(status=Prescription.Status.DISPENSED, created_at__date=today)[:10]
    return render(request, 'pharmacy/dispense.html', {'hospital': hospital, 'pending': pending, 'done': done})


@require_POST
@role_required(*PHARMACY_ROLES)
def dispense(request, pk):
    hospital = hospital_or_404(request.user)
    rx = get_object_or_404(Prescription, pk=pk, token__department__hospital=hospital)
    try:
        services.dispense(rx, user=request.user)
    except services.PharmacyError as exc:
        messages.error(request, f'Nothing was dispensed. {exc}')
    else:
        messages.success(request, f'Prescription for {rx.token.label} dispensed.')
    return redirect('pharmacy:dispense_list')


@require_POST
@role_required(*PHARMACY_ROLES)
def reject(request, pk):
    """Refuse a pending prescription of this hospital that cannot be filled."""
    hospital = hospital_or_404(request.user)
    rx = get_object_or_404(Prescription.objects.select_related('token'), pk=pk, token__department__hospital=hospital)
    try:
        services.reject(rx, user=request.user)
    except services.PharmacyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'Prescription for {rx.token.label} rejected. The doctor can write a new one.')
    return redirect('pharmacy:dispense_list')


@role_required(*PHARMACY_ROLES)
def stock(request):
    """S11: all medicine batches with status labels, alerts, receive stock and write off expired."""
    hospital = hospital_or_404(request.user)
    form = ReceiveStockForm(request.POST or None, hospital=hospital)
    if request.method == 'POST' and form.is_valid():
        med = services.receive_stock(form.cleaned_data['medicine'], form.cleaned_data['quantity'], user=request.user)
        messages.success(request, f'{form.cleaned_data["quantity"]} added to {med.name}. Now {med.quantity}.')
        return redirect('pharmacy:stock')

    today = timezone.localdate()
    soon = today + timedelta(days=30)
    medicines = list(Medicine.objects.filter(hospital=hospital).order_by('name', 'expiry_date'))
    for m in medicines:
        if m.expiry_date < today:
            m.state = ('expired', 'Expired')
        elif m.is_low:
            m.state = ('low', 'Low stock')
        elif m.expiry_date <= soon:
            m.state = ('soon', 'Expiring soon')
        else:
            m.state = ('ok', 'In stock')
    return render(request, 'pharmacy/stock.html', {
        'hospital': hospital, 'form': form, 'medicines': medicines,
        'low': services.low_stock(hospital), 'expiring': services.expiring_soon(hospital),
        'expired': services.expired(hospital),
        'movements': StockMovement.objects.filter(medicine__hospital=hospital)
                                          .select_related('medicine', 'performed_by')[:8],
    })


@require_POST
@role_required(*PHARMACY_ROLES)
def write_off(request):
    hospital = hospital_or_404(request.user)
    count = services.write_off_expired(hospital, user=request.user)
    messages.success(request, f'{count} expired batch{"es" if count != 1 else ""} written off.')
    return redirect('pharmacy:stock')
