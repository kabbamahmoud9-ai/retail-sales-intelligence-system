from django import forms
from .models import DeliveryZone


class DeliveryZoneForm(forms.ModelForm):
    class Meta:
        model = DeliveryZone
        fields = [
            'zone_name', 'base_fee', 'per_km_rate', 'average_distance_km',
            'estimated_operational_cost', 'estimated_delivery_time_minutes',
            'is_active',
        ]
        widgets = {
            'zone_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Freetown Central'}),
            'base_fee': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'per_km_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'average_distance_km': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
            'estimated_operational_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'estimated_delivery_time_minutes': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }