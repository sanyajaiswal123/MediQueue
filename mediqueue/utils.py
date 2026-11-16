"""Small view helpers shared by the staff apps."""
from django.http import Http404
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme

from accounts.permissions import staff_hospital


def hospital_or_404(user):
    """The staff user's hospital, or 404 when none exists yet."""
    hospital = staff_hospital(user)
    if hospital is None:
        raise Http404('No hospital configured.')
    return hospital


def redirect_back(request, fallback):
    """Redirect to a safe `next` (POST field) or the referring page, else to `fallback`."""
    nxt = request.POST.get('next') or request.META.get('HTTP_REFERER')
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return redirect(nxt)
    return redirect(fallback)
