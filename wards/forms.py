"""Admission request form (S8)."""
from django import forms

from accounts.models import phone_validator
from hospitals.models import Doctor
from opd.forms import GENDER_CHOICES

from .models import Ward


class AdmissionForm(forms.Form):
    """Request a bed for a patient. A free bed is assigned at once, otherwise they join the waiting list."""

    name = forms.CharField(max_length=120, label='Patient name')
    phone = forms.CharField(max_length=10, validators=[phone_validator], label='Phone (10 digits)')
    age = forms.IntegerField(min_value=0, max_value=120)
    gender = forms.ChoiceField(choices=GENDER_CHOICES)
    ward = forms.ModelChoiceField(queryset=Ward.objects.none(), empty_label='Select ward')
    doctor = forms.ModelChoiceField(queryset=Doctor.objects.none(), required=False, empty_label='Not assigned')
    priority = forms.BooleanField(required=False, label='Emergency (goes to the top of the waiting list)')

    def __init__(self, *args, hospital, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ward'].queryset = hospital.wards.all()
        self.fields['doctor'].queryset = Doctor.objects.filter(
            department__hospital=hospital).select_related('user', 'department')
