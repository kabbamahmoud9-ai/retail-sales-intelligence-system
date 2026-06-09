from django.db import models
from products.models import Product
from accounts.models import CustomUser

class StockReceipt(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity_received = models.IntegerField()
    received_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    receipt_date = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.product.product_name} - {self.quantity_received} units"

    def save(self, *args, **kwargs):
        # Automatically update product stock when receipt is saved
        self.product.quantity_in_stock += self.quantity_received
        self.product.save()
        super().save(*args, **kwargs)


class InventoryAdjustment(models.Model):
    ADJUSTMENT_TYPES = (
        ('addition', 'Addition'),
        ('deduction', 'Deduction'),
    )
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    adjustment_type = models.CharField(max_length=20, choices=ADJUSTMENT_TYPES)
    quantity = models.IntegerField()
    reason = models.TextField(blank=True, null=True)
    adjusted_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    adjusted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.adjustment_type} - {self.product.product_name} ({self.quantity})"

    def save(self, *args, **kwargs):
        if self.adjustment_type == 'addition':
            self.product.quantity_in_stock += self.quantity
        else:
            self.product.quantity_in_stock -= self.quantity
        self.product.save()
        super().save(*args, **kwargs)