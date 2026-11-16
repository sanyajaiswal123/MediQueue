from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import phone_validator


class PatientRegistrationForm(UserCreationForm):
    """Public registration: always creates a Patient (staff are created by the admin)."""

    first_name = forms.CharField(max_length=60, label='Full name')
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=10, validators=[phone_validator], label='Phone (10 digits)')

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'first_name', 'email', 'phone')

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            user.profile.phone = self.cleaned_data['phone']
            user.profile.save()
        return user
