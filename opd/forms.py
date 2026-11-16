"""Forms for booking (patient), walk-in registration (reception) and prescriptions (doctor)."""
from django import forms
from django.utils import timezone

from accounts.models import phone_validator
from hospitals.models import Department
from pharmacy.models import Medicine

from .models import Patient

GENDER_CHOICES = [('', 'Select')] + list(Patient.Gender.choices)


class BookTokenForm(forms.Form):
    """Patient books a token. Age and gender are asked only once, to create the patient record."""

    department = forms.ModelChoiceField(queryset=Department.objects.none(), widget=forms.RadioSelect,
                                        empty_label=None, error_messages={'required': 'Choose a department.'})
    age = forms.IntegerField(min_value=0, max_value=120)
    gender = forms.ChoiceField(choices=GENDER_CHOICES)

    def __init__(self, *args, hospital, needs_profile, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = hospital.departments.filter(is_open=True)
        if not needs_profile:
            del self.fields['age']
            del self.fields['gender']


class WalkInForm(forms.Form):
    """Reception registers a walk-in patient and issues a token in one step."""

    name = forms.CharField(max_length=120, label='Patient name')
    phone = forms.CharField(max_length=10, validators=[phone_validator], label='Phone (10 digits)')
    age = forms.IntegerField(min_value=0, max_value=120)
    gender = forms.ChoiceField(choices=GENDER_CHOICES)
    department = forms.ModelChoiceField(queryset=Department.objects.none(), empty_label='Select department')
    is_priority = forms.BooleanField(required=False, label='Priority (emergency, elderly, pregnant)')

    def __init__(self, *args, hospital, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = hospital.departments.filter(is_open=True)


class PrescriptionItemForm(forms.Form):
    """One medicine line. Blank lines are ignored."""

    medicine = forms.ModelChoiceField(queryset=Medicine.objects.none(), required=False, empty_label='Medicine')
    quantity = forms.IntegerField(min_value=1, max_value=500, required=False)

    def __init__(self, *args, hospital, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['medicine'].queryset = Medicine.objects.filter(
            hospital=hospital, quantity__gt=0, expiry_date__gte=timezone.localdate()).order_by('name')

    def clean(self):
        data = super().clean()
        if data.get('medicine') and not data.get('quantity'):
            self.add_error('quantity', 'Enter a quantity.')
        if data.get('quantity') and not data.get('medicine'):
            self.add_error('medicine', 'Choose a medicine.')
        return data


PrescriptionFormSet = forms.formset_factory(PrescriptionItemForm, extra=3, max_num=6)
