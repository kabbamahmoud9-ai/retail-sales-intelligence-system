from django import forms
from .models import CustomerRequest

class CustomerRequestForm(forms.ModelForm):
    class Meta:
        model = CustomerRequest
        fields = ['product', 'product_name_requested', 'customer_name',
                  'customer_phone', 'quantity_requested', 'status', 'notes']
        widgets = {
            'product': forms.Select(attrs={'class': 'form-control'}),
            'product_name_requested': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. iPhone 15 Charger'}),
            'customer_name': forms.TextInput(attrs={'class': 'form-control'}),
            'customer_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity_requested': forms.NumberInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }