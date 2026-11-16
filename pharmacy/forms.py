"""Pharmacy forms."""
from django import forms

from .models import Medicine


class ReceiveStockForm(forms.Form):
    """Add delivered stock to an existing medicine batch."""

    medicine = forms.ModelChoiceField(queryset=Medicine.objects.none(), empty_label='Select medicine')
    quantity = forms.IntegerField(min_value=1, max_value=100000)

    def __init__(self, *args, hospital, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['medicine'].queryset = Medicine.objects.filter(hospital=hospital).order_by('name', 'expiry_date')
        self.fields['medicine'].label_from_instance = lambda m: f'{m.name} (exp. {m.expiry_date:%d %b %Y})'
