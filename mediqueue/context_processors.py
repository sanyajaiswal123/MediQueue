"""Template context shared by every page: role flags and the role-aware staff navigation."""
from django.urls import reverse

from accounts.models import Profile
from accounts.permissions import user_role

Role = Profile.Role
STAFF_ROLES = (Role.RECEPTIONIST, Role.DOCTOR, Role.PHARMACIST, Role.ADMIN)

# (url name, icon, label, roles that see it)
NAV = [
    ('staff_home', 'overview', 'Overview', STAFF_ROLES),
    ('opd:reception', 'queue', 'Reception desk', (Role.RECEPTIONIST, Role.ADMIN)),
    ('opd:console', 'consult', 'Consultations', (Role.DOCTOR,)),
    ('wards:board', 'bed', 'Ward board', (Role.RECEPTIONIST, Role.DOCTOR, Role.ADMIN)),
    ('wards:admissions', 'admit', 'Admissions', (Role.RECEPTIONIST, Role.DOCTOR, Role.ADMIN)),
    ('wards:discharges', 'discharge', 'Discharge and cleaning', (Role.RECEPTIONIST, Role.DOCTOR, Role.ADMIN)),
    ('pharmacy:dispense_list', 'pill', 'Dispense', (Role.PHARMACIST, Role.ADMIN)),
    ('pharmacy:stock', 'stock', 'Stock and alerts', (Role.PHARMACIST, Role.ADMIN)),
    ('city', 'city', 'City dashboard', STAFF_ROLES),
]


def nav(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    role = user_role(user)
    superuser = user.is_superuser
    current = request.resolver_match.view_name if request.resolver_match else ''
    items = [{'url': reverse(name), 'icon': icon, 'label': label, 'active': current == name}
             for name, icon, label, roles in NAV if (superuser and Role.ADMIN in roles) or role in roles]
    return {
        'staff_nav': items,
        'is_staff_user': superuser or role in STAFF_ROLES,
        'is_patient': not superuser and role == Role.PATIENT,
    }
