"""
ecommerce/models.py

Three models power the online store:
  - OnlineCustomer  : separate from staff users, has credit system
  - OnlineOrder     : customer's order with payment method + status
  - OnlineOrderItem : line items; on save() triggers Sale creation

Key integration point: OnlineOrder.confirm_order() creates Sale + SaleItems
in the existing sales pipeline so the dashboard and inventory update automatically.
"""

from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
import uuid

from products.models import Product
from sales.models import Sale, SaleItem


# ---------------------------------------------------------------------------
# OnlineCustomer
# ---------------------------------------------------------------------------

class OnlineCustomer(models.Model):
    """
    A customer who shops via the online store.
    Completely separate from staff CustomUser accounts.
    Has a built-in credit system for 'Buy Now, Pay Later' orders.
    """

    full_name       = models.CharField(max_length=200)
    email           = models.EmailField(unique=True)
    phone           = models.CharField(max_length=20, blank=True)
    address         = models.TextField(blank=True, help_text="Default delivery address")

    # Hashed with Django's make_password — never stored plain
    password        = models.CharField(max_length=255)

    # Credit system — used when payment_method = 'credit'
    credit_limit    = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Maximum credit the customer can carry"
    )
    credit_balance  = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00,
        help_text="Current outstanding credit owed by customer"
    )

    is_active       = models.BooleanField(default=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Online Customer"
        verbose_name_plural = "Online Customers"

    def __str__(self):
        return f"{self.full_name} ({self.email})"

    # ------------------------------------------------------------------
    # Password helpers — mirrors Django's AbstractUser pattern
    # ------------------------------------------------------------------

    def set_password(self, raw_password):
        """Hash and store password. Call this instead of assigning directly."""
        self.password = make_password(raw_password)

    def check_password(self, raw_password):
        """Return True if raw_password matches the stored hash."""
        return check_password(raw_password, self.password)

    # ------------------------------------------------------------------
    # Credit helpers
    # ------------------------------------------------------------------

    @property
    def available_credit(self):
        """How much more the customer can charge on credit."""
        return self.credit_limit - self.credit_balance

    def can_afford_credit(self, amount):
        """Return True if the customer has enough available credit."""
        return self.available_credit >= amount


# ---------------------------------------------------------------------------
# OnlineOrder
# ---------------------------------------------------------------------------

class OnlineOrder(models.Model):
    """
    Represents a single customer order from the online store.

    Status flow:
        pending → confirmed → processing → shipped → delivered
                           ↘ cancelled

    Payment methods include local mobile money options (Orange Money, Afrimoney)
    and credit purchases. Payment is simulated — architecture allows real
    API integration later by swapping simulate_payment().
    """

    STATUS_CHOICES = [
        ('pending',    'Pending'),
        ('confirmed',  'Confirmed'),
        ('processing', 'Processing'),
        ('shipped',    'Shipped'),
        ('delivered',  'Delivered'),
        ('cancelled',  'Cancelled'),
    ]

    PAYMENT_CHOICES = [
        ('cash_on_delivery', 'Cash on Delivery'),
        ('orange_money',     'Orange Money'),
        ('afrimoney',        'Afrimoney'),
        ('credit',           'Credit Purchase'),
    ]

    customer         = models.ForeignKey(
        OnlineCustomer,
        on_delete=models.PROTECT,      # Never delete a customer with orders
        related_name='orders'
    )

    # Human-readable order reference, e.g. ORD-2024-A3F9
    order_reference  = models.CharField(max_length=50, unique=True, blank=True)

    order_date       = models.DateTimeField(default=timezone.now)
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    delivery_address = models.TextField()
    payment_method   = models.CharField(max_length=20, choices=PAYMENT_CHOICES)

    # Populated by simulate_payment() — architecture allows real API swap
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_confirmed = models.BooleanField(default=False)

    total_amount     = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    # Reserved for Step 11 — Blockchain hash chain
    transaction_hash = models.CharField(max_length=256, blank=True)

    # FK to the Sale record created when this order is confirmed
    # Null until confirm_order() is called
    linked_sale      = models.OneToOneField(
        Sale,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='online_order',
        help_text="The Sale record created when this order was confirmed"
    )

    notes            = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order_date']
        verbose_name = "Online Order"
        verbose_name_plural = "Online Orders"

    def __str__(self):
        return f"{self.order_reference} — {self.customer.full_name}"

    # ------------------------------------------------------------------
    # Auto-generate a readable order reference before first save
    # ------------------------------------------------------------------

    def save(self, *args, **kwargs):
        if not self.order_reference:
            # e.g. ORD-2024-A3F9  — year + first 4 chars of UUID
            uid = uuid.uuid4().hex[:6].upper()
            year = timezone.now().year
            self.order_reference = f"ORD-{year}-{uid}"
        super().save(*args, **kwargs)

    # ------------------------------------------------------------------
    # Payment simulation
    # ------------------------------------------------------------------

    def simulate_payment(self):
        """
        Generates a fake transaction reference.
        Replace this method body with a real API call in production.
        Returns (success: bool, reference: str).
        """
        if self.payment_method == 'cash_on_delivery':
            # No upfront payment — always succeeds
            ref = f"COD-{uuid.uuid4().hex[:8].upper()}"
            return True, ref

        elif self.payment_method == 'orange_money':
            ref = f"OM-{uuid.uuid4().hex[:10].upper()}"
            return True, ref

        elif self.payment_method == 'afrimoney':
            ref = f"AFM-{uuid.uuid4().hex[:10].upper()}"
            return True, ref

        elif self.payment_method == 'credit':
            # Real check: does the customer have enough credit?
            if self.customer.can_afford_credit(self.total_amount):
                ref = f"CRED-{uuid.uuid4().hex[:8].upper()}"
                return True, ref
            else:
                return False, "Insufficient credit limit"

        return False, "Unknown payment method"

    # ------------------------------------------------------------------
    # Core integration: confirm order → create Sale in existing pipeline
    # ------------------------------------------------------------------

    def confirm_order(self):
        """
        Called after payment succeeds.

        1. Validates stock for every item
        2. Creates a Sale record (so dashboard/reports update)
        3. Creates SaleItem records (which deduct stock via existing save() logic)
        4. Links the Sale back to this order
        5. Updates credit balance if payment was by credit
        6. Marks order as confirmed

        Raises ValueError with a user-friendly message if anything fails.
        This method is atomic-safe — wrap in transaction.atomic() in the view.
        """

        # --- 1. Stock validation (fixes known gap) ----------------------
        for item in self.items.all():
            if item.product.quantity_in_stock < item.quantity:
                raise ValueError(
                    f"Sorry — '{item.product.product_name}' only has "
                    f"{item.product.quantity_in_stock} units in stock. "
                    f"You requested {item.quantity}."
                )

        # --- 2. Create the Sale record -----------------------------------
        # Sale model has no customer field — put customer name in notes instead
        sale = Sale.objects.create(
            sale_date=self.order_date,
            notes=f"Online order {self.order_reference} — Customer: {self.customer.full_name}",
        )
        
        # --- 3. Create SaleItems (their save() deducts stock) -----------
        for item in self.items.all():
            SaleItem.objects.create(
                sale=sale,
                product=item.product,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )

        # Recalculate sale total using existing method
        sale.calculate_total()
        sale.save()

        # --- 4. Link Sale back to this order ----------------------------
        self.linked_sale = sale

        # --- 5. Handle credit payment -----------------------------------
        if self.payment_method == 'credit':
            self.customer.credit_balance += self.total_amount
            self.customer.save()

        # --- 6. Mark confirmed ------------------------------------------
        self.status = 'confirmed'
        self.save()

        return sale


# ---------------------------------------------------------------------------
# OnlineOrderItem
# ---------------------------------------------------------------------------

class OnlineOrderItem(models.Model):
    """
    A single product line within an OnlineOrder.

    unit_price is snapshotted at order time — so if the product price
    changes later, the order history remains accurate.
    """

    order      = models.ForeignKey(
        OnlineOrder,
        on_delete=models.CASCADE,
        related_name='items'
    )
    product    = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,   # Don't delete products with order history
        related_name='online_order_items'
    )
    quantity   = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Price at time of order — frozen, not live"
    )

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"

    def __str__(self):
        return f"{self.quantity}x {self.product.product_name} (Order {self.order.order_reference})"

    @property
    def subtotal(self):
        return self.quantity * self.unit_price