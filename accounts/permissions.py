"""Role-based access control for staff views."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import Profile


def user_role(user):
    """Return the user's role string, or None if anonymous / no profile."""
    if not user.is_authenticated:
        return None
    try:
        return user.profile.role
    except Profile.DoesNotExist:
        return None


def staff_hospital(user):
    """The hospital a staff user works at. Admins without one fall back to the first active hospital."""
    from hospitals.models import Hospital
    profile = getattr(user, 'profile', None)
    hospital = getattr(profile, 'hospital', None)
    return hospital or Hospital.objects.filter(is_active=True).first()


def who_for(roles):
    """Plain-English owner of a page, e.g. 'doctors' or 'receptionists and admins' (shown on the 403 page)."""
    names = [f'{Profile.Role(r).label.lower()}s' for r in roles]
    return ' and '.join([', '.join(names[:-1]), names[-1]] if len(names) > 1 else names)


def role_required(*roles):
    """Allow a view only for the given roles (Profile.Role values). Superusers always pass.

    Anonymous users are redirected to login; logged-in users with the wrong role get 403.
    """
    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.user.is_superuser or user_role(request.user) in roles:
                return view(request, *args, **kwargs)
            raise PermissionDenied(who_for(roles))
        return login_required(wrapper)
    return decorator
