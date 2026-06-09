from django import forms
from .models import StockReceipt, InventoryAdjustment

class StockReceiptForm(forms.ModelForm):
    class Meta:
        model = StockReceipt
        fields = ['product', 'quantity_received', 'notes']

class InventoryAdjustmentForm(forms.ModelForm):
    class Meta:
        model = InventoryAdjustment
        fields = ['product', 'adjustment_type', 'quantity', 'reason']