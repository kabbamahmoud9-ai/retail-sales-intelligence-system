from django.db import models
from products.models import Product
from accounts.models import CustomUser

class Sale(models.Model):
    STATUS_CHOICES = (
        ('completed', 'Completed'),
        ('pending', 'Pending'),
        ('cancelled', 'Cancelled'),
    )
    sale_date = models.DateTimeField(auto_now_add=True)
    served_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Sale #{self.id} - {self.sale_date.strftime('%Y-%m-%d')}"

    def calculate_total(self):
        total = sum(item.subtotal for item in self.saleitem_set.all())
        self.total_amount = total
        self.save()


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

    def __str__(self):
        return f"{self.product.product_name} x {self.quantity}"

    def save(self, *args, **kwargs):
        self.product.quantity_in_stock -= self.quantity
        self.product.save()
        super().save(*args, **kwargs)