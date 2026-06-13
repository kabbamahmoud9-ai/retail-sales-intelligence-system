from django.db import models
from products.models import Product
from accounts.models import CustomUser

class CustomerRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('fulfilled', 'Fulfilled'),
        ('cancelled', 'Cancelled'),
    )
    # If the product exists in our system, link it. Otherwise just store the name.
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    product_name_requested = models.CharField(max_length=255, help_text="Name of product if not in our system")
    customer_name = models.CharField(max_length=150, blank=True, null=True)
    customer_phone = models.CharField(max_length=30, blank=True, null=True)
    quantity_requested = models.IntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True, null=True)
    recorded_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product_name_requested} - {self.status}"

    class Meta:
        ordering = ['-requested_at']