from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse

from .forms import PatientRegistrationForm
from .models import Profile


def register(request):
    """Patient self-registration. Logs the new user in and redirects (POST-redirect-GET)."""
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)
    form = PatientRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect(settings.LOGIN_REDIRECT_URL)
    return render(request, 'registration/register.html', {'form': form})


class RoleLoginView(LoginView):
    """Login that sends staff to their portal and patients to the home page (unless ?next= is set)."""

    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        user = self.request.user
        if user.is_authenticated and (user.is_superuser or user.profile.role != Profile.Role.PATIENT):
            return reverse('staff_home')
        return super().get_default_redirect_url()
