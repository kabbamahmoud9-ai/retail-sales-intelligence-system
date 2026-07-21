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

from products.models import Product, Category
from sales.models import Sale, SaleItem
from delivery.models import DeliveryZone
from . import services
from blockchain.services import create_ledger_entry


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

    # --- Customer intelligence (Step 11) --------------------------------
    lifetime_spending = models.DecimalField(
        max_digits=12, decimal_places=2, default=0.00,
        help_text="Cumulative total of all confirmed order amounts"
    )
    total_orders = models.PositiveIntegerField(default=0)
    last_purchase_date = models.DateTimeField(null=True, blank=True)

    preferred_categories = models.ManyToManyField(
        Category, blank=True, related_name='preferred_by_customers',
        help_text="System-computed top purchase categories, refreshed on each confirmed order"
    )

    trust_score = models.PositiveIntegerField(
        default=50,
        help_text="Rule-based trust score (0-100), auto-updated on each confirmed order. "
                   "See ecommerce.services.calculate_trust_score()."
    )

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
    # ------------------------------------------------------------------
    # Customer intelligence (Step 11)
    # ------------------------------------------------------------------

    @property
    def loyalty_tier(self):
        """
        Loyalty tier name, derived from lifetime_spending.

        Delegates to services.calculate_loyalty_tier() rather than
        computing thresholds inline, so tier logic can later factor in
        purchase frequency, trust_score, or promotions without touching
        this model.
        """
        return services.calculate_loyalty_tier(self)

    def record_confirmed_order(self, order):
        """
        Called from OnlineOrder.confirm_order() right after an order is
        confirmed. Updates all customer-intelligence stats in one place:

          1. lifetime_spending / total_orders / last_purchase_date
          2. preferred_categories (recomputed from full order history)
          3. trust_score (recalculated via services.calculate_trust_score)

        Kept as a single entry point so future AI features (Step 12/13)
        have one place to trigger customer-stat refreshes from, rather
        than duplicating this logic wherever an order gets confirmed.
        """
        self.lifetime_spending += order.total_amount
        self.total_orders += 1
        self.last_purchase_date = order.order_date

        # Recompute preferred categories from full confirmed order history.
        # Simple frequency-based top-3; refined ranking is future AI work.
        category_ids = (
            OnlineOrderItem.objects
            .filter(order__customer=self, order__status__in=['confirmed', 'delivered'])
            .values_list('product__category_id', flat=True)
        )
        from collections import Counter
        top_category_ids = [cid for cid, _ in Counter(category_ids).most_common(3) if cid]
        self.preferred_categories.set(top_category_ids)

        self.trust_score = services.calculate_trust_score(self)

        self.save()


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

    # --- Delivery costing (Step 11) -------------------------------------
    DELIVERY_STATUS_CHOICES = [
        ('assigned',   'Assigned'),
        ('in_transit', 'In Transit'),
        ('delivered',  'Delivered'),
        ('failed',     'Failed'),
    ]
    DELIVERY_METHOD_CHOICES = [
        ('own_rider',        'Own Rider'),
        ('third_party',      'Third-Party Courier'),
        ('customer_pickup',  'Customer Pickup'),
    ]

    delivery_zone = models.ForeignKey(
        DeliveryZone, on_delete=models.PROTECT, null=True, blank=True,
        related_name='orders',
        help_text="Zone selected at checkout; determines delivery_fee"
    )
    # Snapshotted at checkout — same "freeze it" pattern as unit_price on
    # OnlineOrderItem, so historical orders stay accurate if zone pricing
    # changes later.
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    delivery_distance_km = models.DecimalField(
        max_digits=6, decimal_places=2, default=0.00,
        help_text="Distance used to calculate delivery_fee at checkout time"
    )
    delivery_status = models.CharField(
        max_length=20, choices=DELIVERY_STATUS_CHOICES, blank=True,
        help_text="Tracks the delivery leg specifically, independent of overall order status"
    )
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_METHOD_CHOICES, blank=True)
    delivery_notes = models.TextField(blank=True)

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
    def record_payment_confirmation(self, payment_reference):
        """
        Confirms payment for this order and records the event on the
        blockchain audit ledger.

        Single entry point for marking payment_confirmed=True — every
        payment method (Cash on Delivery, Orange Money, Afrimoney, Credit,
        and any future method) goes through this same path, so checkout
        views stay thin and blockchain logic is never duplicated.
        """
        self.payment_reference = payment_reference
        self.payment_confirmed = True
        self.save()

        create_ledger_entry(
            record_type='payment_confirmation',
            record_reference=self.order_reference,
            payload_snapshot={
                'order_reference': self.order_reference,
                'payment_method': self.payment_method,
                'payment_reference': payment_reference,
                'total_amount': str(self.total_amount),
                'delivery_fee': str(self.delivery_fee),
                'confirmed_at': timezone.now().isoformat(),
            },
        )
        
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

        # --- 7. Update customer intelligence (Step 11) -------------------
        # Lifetime spending, order count, preferred categories, and trust
        # score all refresh here so nothing else has to remember to do it.
        self.customer.record_confirmed_order(self)

        # --- 8. Record this confirmation on the audit ledger (Step 14a) --
        ledger_entry = create_ledger_entry(
            record_type='online_order_confirmation',
            record_reference=self.order_reference,
            payload_snapshot={
                'order_reference': self.order_reference,
                'total_amount': str(self.total_amount),
                'status': self.status,
                'payment_method': self.payment_method,
                'linked_sale_id': sale.id,
                'confirmed_at': timezone.now().isoformat(),
            },
        )
        self.transaction_hash = ledger_entry.current_hash
        self.save(update_fields=['transaction_hash'])

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

# ---------------------------------------------------------------------------
# CreditRepayment
# ---------------------------------------------------------------------------

class CreditRepayment(models.Model):
    """
    Append-only log of a staff-recorded credit repayment. Mirrors the
    operational-record-plus-blockchain-entry pattern already used for
    order/payment confirmations: this model supports history/reporting/
    Metabase, while the corresponding blockchain LedgerEntry is the
    tamper-evident audit trail. Never edited or deleted after creation.

    Staff-triggered only — there is no real payment gateway in this
    system (simulate_payment() already stands in for that elsewhere),
    so a human must attest that repayment actually happened, the same
    reasoning that makes credit limit approval staff-triggered too.
    """
    customer = models.ForeignKey(
        OnlineCustomer, on_delete=models.CASCADE, related_name='credit_repayments'
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    recorded_by = models.ForeignKey(
        'accounts.CustomUser', on_delete=models.SET_NULL, null=True,
        related_name='recorded_credit_repayments'
    )
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    transaction_hash = models.CharField(max_length=256, blank=True)
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-recorded_at']
        verbose_name = 'Credit Repayment'
        verbose_name_plural = 'Credit Repayments'

    def __str__(self):
        return f"{self.customer.full_name} — Le {self.amount} repaid @ {self.recorded_at:%Y-%m-%d %H:%M}"