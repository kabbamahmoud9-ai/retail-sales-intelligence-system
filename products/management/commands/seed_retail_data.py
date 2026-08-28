"""
products/management/commands/seed_retail_data.py

Generates a realistic historical dataset on top of the EXISTING product
catalogue, so the AI Advisor and Conversational AI have enough history
to produce meaningful analysis. Additive only:

  - Never deletes or modifies existing products, customers, orders,
    or expenses.
  - Reuses existing model/service methods wherever they exist
    (OnlineOrder.confirm_order(), OnlineCustomer.record_confirmed_order(),
    customer_insights.generate_customer_insight(),
    forecasting.generate_forecasts_for_all()) instead of reimplementing
    any of that logic — same "never duplicate business logic" discipline
    used everywhere else in this project.

Usage:
    python manage.py seed_retail_data
    python manage.py seed_retail_data --customers 150 --months 12
    python manage.py seed_retail_data --force        # re-seed even if
                                                       # seed data already
                                                       # detected

IMPORTANT KNOWN GOTCHA THIS COMMAND WORKS AROUND:
    Several date fields in this project are auto_now_add=True
    (Sale.sale_date, StockReceipt.receipt_date,
    InventoryAdjustment.adjusted_at, OnlineCustomer.created_at). Django
    silently ignores any value passed to these fields on .save()/.create()
    and always stamps the real current timestamp. This command always
    creates such rows first, then immediately fixes the date with a
    queryset .update() call (which bypasses auto_now_add, since that
    behavior only fires on instance .save()). If you ever see historical
    data with today's date on any of those four fields, that's this bug,
    not a seeding error.

LIMITATIONS, BY DESIGN:
    - No Cost of Goods Sold field exists in this schema and none is
      added here (out of scope — see project notes). Only real,
      already-supported metrics are populated.
    - Only products with is_available_online=True can appear in
      customer-linked OnlineOrder history (a schema requirement, not a
      choice made here). To still exercise the FULL catalogue for
      sales-history analysis (top sellers / slow movers), this command
      also generates a smaller stream of anonymous walk-in Sale/SaleItem
      records across every active product, mirroring how the existing
      codebase already treats in-store sales as customer-anonymous.
"""
import random
from collections import defaultdict
from datetime import timedelta, datetime, time
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction, models
from django.utils import timezone

from products.models import Product, Category
from accounts.models import CustomUser
from sales.models import Sale, SaleItem
from ecommerce.models import OnlineCustomer, OnlineOrder, OnlineOrderItem
from expenses.models import Expense, ExpenseCategory
from inventory.models import StockReceipt, InventoryAdjustment

try:
    from delivery.models import DeliveryZone
except Exception:
    DeliveryZone = None

from customer_insights.models import CustomerEvent
from customer_insights.services import generate_customer_insight
from forecasting.services import generate_forecasts_for_all


SEED_EMAIL_DOMAIN = "seed.retailintel.local"
SEED_MARKER = "[SEED]"

FIRST_NAMES = [
    "Aminata", "Mohamed", "Fatmata", "Ibrahim", "Isatu", "Abu", "Mariama",
    "Alhaji", "Adama", "Foday", "Kadiatu", "Sorie", "Hawa", "Sahr",
    "Zainab", "Alusine", "Mabinty", "Santigie", "Yeanoh", "Momoh",
    "Kadija", "Brima", "Fanta", "Sheku", "Ramatu", "Lamin", "Aisha",
    "Musa", "Marie", "Osman",
]
LAST_NAMES = [
    "Kamara", "Sesay", "Koroma", "Bangura", "Conteh", "Turay", "Kargbo",
    "Mansaray", "Jalloh", "Kanu", "Fofanah", "Sankoh", "Bah", "Kabba",
    "Kanneh", "Vandy", "Tholley", "Gbla", "Sillah", "Barrie",
]

EXPENSE_CATEGORIES = [
    ("Rent", 3_500, 3_800, "monthly"),
    ("Electricity", 400, 900, "monthly"),
    ("Internet", 150, 200, "monthly"),
    ("Transportation", 300, 700, "weekly"),
    ("Delivery", 200, 600, "weekly"),
    ("Staff/Salaries", 4_000, 5_500, "monthly"),
    ("Packaging", 150, 400, "weekly"),
    ("Maintenance", 100, 500, "monthly"),
    ("Marketing", 100, 900, "monthly"),
    ("Utilities", 100, 300, "monthly"),
]

# (archetype key, weight, orders_range, interval_days_range, order_value_multiplier)
ARCHETYPES = [
    ("new",                  0.14, (1, 1),   (0, 0),      (0.8, 1.3)),
    ("occasional",           0.20, (2, 4),   (35, 70),    (0.7, 1.2)),
    ("loyal",                0.18, (8, 16),  (12, 24),    (0.9, 1.4)),
    ("vip",                  0.06, (10, 20), (8, 18),     (1.8, 3.0)),
    ("at_risk",              0.14, (4, 8),   (14, 25),    (0.8, 1.3)),
    ("dormant",              0.10, (2, 5),   (20, 40),    (0.7, 1.1)),
    ("frequent_low_value",   0.10, (10, 20), (9, 18),     (0.4, 0.7)),
    ("infrequent_high_value",0.08, (2, 4),   (60, 120),   (2.0, 3.5)),
]

POPULARITY_TIERS = [("fast", 0.20, (3.0, 5.0)), ("medium", 0.50, (1.0, 2.5)), ("slow", 0.30, (0.2, 0.8))]

SCHOOL_KEYWORDS = {"exercise book", "pen", "pencil", "school", "uniform", "bag"}
BEVERAGE_KEYWORDS = {"beverage", "drink", "soft drink", "water", "soda", "juice"}
FOOD_KEYWORDS = {"rice", "oil", "food", "cooking", "grain", "spice", "sauce"}

COMBO_GROUPS = [
    {"Rice & Grains", "Cooking Oil", "Spices & Seasonings", "Canned Foods"},
    {"Bread & Bakery", "Dairy Products", "Tea & Coffee"},
    {"Water & Soft Drinks", "Biscuits & Snacks", "Confectionery"},
]


class Command(BaseCommand):
    help = "Seeds realistic historical retail data on top of existing products/customers."

    def add_arguments(self, parser):
        parser.add_argument("--customers", type=int, default=150)
        parser.add_argument("--months", type=int, default=12)
        parser.add_argument("--seed", type=int, default=42)
        parser.add_argument("--skip-expenses", action="store_true")
        parser.add_argument("--skip-inventory", action="store_true")
        parser.add_argument("--skip-insights", action="store_true",
                             help="Skip running generate_customer_insight() per customer.")
        parser.add_argument("--skip-forecasts", action="store_true",
                             help="Skip running generate_forecasts_for_all() at the end.")
        parser.add_argument("--force", action="store_true",
                             help="Re-seed even if prior seed data is detected.")
        parser.add_argument("--cleanup-only", action="store_true",
                             help="Delete all previously seeded data (identified via the "
                                  "@%s email domain and [SEED] markers) and exit without "
                                  "generating new data." % SEED_EMAIL_DOMAIN)

    # ------------------------------------------------------------------
    def handle(self, *args, **opts):
        random.seed(opts["seed"])
        self.months = opts["months"]
        self.now = timezone.now()
        self.window_start = self.now - timedelta(days=self.months * 30)

        if opts["cleanup_only"]:
            self._cleanup_seed_data()
            return

        if OnlineCustomer.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}").exists() and not opts["force"]:
            self.stdout.write(self.style.WARNING(
                "Seed data already detected (customers with @%s emails exist). "
                "Re-run with --force to add more anyway." % SEED_EMAIL_DOMAIN
            ))
            return

        products = list(Product.objects.filter(is_active=True))
        if not products:
            self.stdout.write(self.style.ERROR("No active products found — nothing to seed against."))
            return

        online_products = [p for p in products if p.is_available_online and p.online_price]
        if not online_products:
            self.stdout.write(self.style.WARNING(
                "No products are is_available_online with an online_price set — "
                "customer-linked order history will be skipped, only walk-in Sales will be generated."
            ))

        self.stdout.write("Assigning popularity tiers to products...")
        self.tiers = self._assign_popularity_tiers(products)

        self.stdout.write("Inflating stock buffers so historical sales don't stock out...")
        self._inflate_stock(products)

        staff_users = list(CustomUser.objects.all())
        if not staff_users:
            self.stdout.write(self.style.ERROR("No staff users (CustomUser) exist — cannot attribute walk-in sales."))
            return

        self.delivery_zones = list(DeliveryZone.objects.filter(is_active=True)) if DeliveryZone else []

        n_customers = opts["customers"]
        self.stdout.write(f"Creating {n_customers} customers with behavioral archetypes...")
        customers = self._create_customers(n_customers)

        self.stdout.write("Generating online order history per customer...")
        seeded_customers = []
        for customer, archetype in customers:
            ok = self._generate_customer_orders(customer, archetype, online_products)
            if ok:
                seeded_customers.append(customer)

        self.stdout.write("Fixing OnlineCustomer.created_at (auto_now_add workaround)...")
        self._fix_customer_join_dates(seeded_customers)

        self.stdout.write("Generating browsing events (CustomerEvent) for a subset of customers...")
        self._generate_customer_events(seeded_customers, online_products)

        self.stdout.write("Generating full-catalogue walk-in Sale history...")
        self._generate_walk_in_sales(products, staff_users)

        if not opts["skip_expenses"]:
            self.stdout.write("Generating historical expenses...")
            self._generate_expenses(staff_users)

        if not opts["skip_inventory"]:
            self.stdout.write("Generating additional periodic stock receipts/adjustments...")
            self._generate_inventory_history(products, staff_users)

        if not opts["skip_insights"]:
            self.stdout.write(f"Running generate_customer_insight() for {len(seeded_customers)} customers...")
            for c in seeded_customers:
                try:
                    generate_customer_insight(c)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  insight failed for {c.email}: {e}"))

        if not opts["skip_forecasts"]:
            self.stdout.write("Running generate_forecasts_for_all()...")
            summary = generate_forecasts_for_all()
            self.stdout.write(f"  forecasts generated: {summary}")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Seeded {len(seeded_customers)} customers with order history over {self.months} months."
        ))

    # ------------------------------------------------------------------
    # Popularity tiers & stock buffer
    # ------------------------------------------------------------------
    def _assign_popularity_tiers(self, products):
        tiers = {}
        for p in products:
            r = random.random()
            cumulative = 0.0
            for name, weight, _ in POPULARITY_TIERS:
                cumulative += weight
                if r <= cumulative:
                    tiers[p.id] = name
                    break
            else:
                tiers[p.id] = POPULARITY_TIERS[-1][0]
        return tiers

    def _tier_multiplier(self, product_id):
        tier = self.tiers.get(product_id, "medium")
        for name, _, mult_range in POPULARITY_TIERS:
            if name == tier:
                return random.uniform(*mult_range)
        return 1.0

    def _inflate_stock(self, products):
        weeks = max(1, (self.months * 30) // 7)
        adjustments = []
        for p in products:
            base_weekly_demand = 3 * self._tier_multiplier(p.id)
            expected_total_demand = int(base_weekly_demand * weeks)
            buffer_needed = max(0, expected_total_demand - p.quantity_in_stock + 20)
            if buffer_needed > 0:
                adj = InventoryAdjustment.objects.create(
                    product=p, adjustment_type="addition", quantity=buffer_needed,
                    reason=f"{SEED_MARKER} initial stock buffer for historical seeding",
                    adjusted_by=None,
                )
                adjustments.append((adj.id, self.window_start))
        self._fix_dates(InventoryAdjustment, "adjusted_at", adjustments)

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------
    def _weighted_archetype(self):
        r = random.random()
        cumulative = 0.0
        for key, weight, *_ in ARCHETYPES:
            cumulative += weight
            if r <= cumulative:
                return key
        return ARCHETYPES[-1][0]

    def _create_customers(self, n):
        result = []
        used_emails = set()
        for i in range(n):
            archetype = self._weighted_archetype()
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            full_name = f"{first} {last}"
            email = f"{first.lower()}.{last.lower()}.{i}@{SEED_EMAIL_DOMAIN}"
            if email in used_emails:
                email = f"{first.lower()}.{last.lower()}.{i}.{random.randint(100,999)}@{SEED_EMAIL_DOMAIN}"
            used_emails.add(email)

            customer = OnlineCustomer(
                full_name=full_name,
                email=email,
                phone=f"+232{random.randint(70000000, 79999999)}",
                address=f"{random.randint(1, 200)} {last} Street, Freetown",
                credit_limit=Decimal(random.choice([0, 0, 500, 1000, 2000])),
                is_active=True,
            )
            customer.set_password("seed-not-a-real-password")
            customer.save()
            result.append((customer, archetype))
        return result

    def _fix_customer_join_dates(self, customers):
        rows = []
        for c in customers:
            first_order = OnlineOrder.objects.filter(customer=c).order_by("order_date").first()
            if first_order:
                join_date = first_order.order_date - timedelta(days=random.randint(0, 14))
            else:
                join_date = self.window_start + timedelta(days=random.randint(0, 30))
            rows.append((c.id, join_date))
        self._fix_dates(OnlineCustomer, "created_at", rows)

    # ------------------------------------------------------------------
    # Order generation
    # ------------------------------------------------------------------
    def _seasonal_weekly_multiplier(self, product, dt):
        name = (product.product_name or "").lower()
        cat = (product.category.category_name.lower() if product.category else "")
        text = f"{name} {cat}"
        multiplier = 1.0

        if any(k in text for k in SCHOOL_KEYWORDS) and dt.month in (1, 9):
            multiplier *= 1.4
        if any(k in text for k in BEVERAGE_KEYWORDS) and dt.weekday() in (4, 5, 6):
            multiplier *= 1.2
        if any(k in text for k in FOOD_KEYWORDS) and dt.month in (12, 1):
            multiplier *= 1.15
        return multiplier

    def _pick_basket(self, online_products, n_items):
        by_category = defaultdict(list)
        for p in online_products:
            cat = p.category.category_name if p.category else "Uncategorized"
            by_category[cat].append(p)

        basket = []
        if random.random() < 0.5:
            group = random.choice(COMBO_GROUPS)
            candidates = [p for cat in group for p in by_category.get(cat, [])]
            if candidates:
                weights = [self._tier_multiplier(p.id) for p in candidates]
                basket = random.choices(candidates, weights=weights, k=min(n_items, len(candidates)))

        if len(basket) < n_items:
            remaining = n_items - len(basket)
            weights = [self._tier_multiplier(p.id) for p in online_products]
            extra = random.choices(online_products, weights=weights, k=remaining)
            basket.extend(extra)

        # de-dup, keep order
        seen = set()
        deduped = []
        for p in basket:
            if p.id not in seen:
                deduped.append(p)
                seen.add(p.id)
        return deduped or random.sample(online_products, min(n_items, len(online_products)))

    def _generate_customer_orders(self, customer, archetype, online_products):
        if not online_products:
            return False

        cfg = next(a for a in ARCHETYPES if a[0] == archetype)
        _, _, orders_range, interval_range, value_mult_range = cfg

        n_orders = random.randint(*orders_range)
        if n_orders == 0:
            return False

        value_mult = random.uniform(*value_mult_range)

        if archetype in ("dormant", "at_risk"):
            last_order_offset_days = random.randint(70, 150) if archetype == "dormant" else random.randint(35, 70)
            end_point = self.now - timedelta(days=last_order_offset_days)
        else:
            end_point = self.now - timedelta(days=random.randint(0, 5))

        dates = []
        cursor = end_point
        for _ in range(n_orders):
            dates.append(cursor)
            gap = random.randint(*interval_range) if interval_range != (0, 0) else 0
            cursor -= timedelta(days=max(gap, 1))
            if cursor < self.window_start:
                break
        dates = sorted(d for d in dates if d >= self.window_start)
        if not dates:
            return False

        any_created = False
        for order_dt in dates:
            order_dt = timezone.make_aware(
                datetime.combine(order_dt.date(), time(hour=random.randint(8, 20), minute=random.randint(0, 59)))
            ) if timezone.is_naive(order_dt) else order_dt

            n_items = random.randint(2, 6)
            basket = self._pick_basket(online_products, n_items)
            if not basket:
                continue

            order = OnlineOrder.objects.create(
                customer=customer,
                order_date=order_dt,
                delivery_address=customer.address,
                payment_method=random.choice(
                    ["cash_on_delivery", "orange_money", "afrimoney"]
                    + (["credit"] if customer.credit_limit and customer.credit_limit > 0 else [])
                ),
                delivery_zone=random.choice(self.delivery_zones) if self.delivery_zones else None,
                status="pending",
            )

            total = Decimal("0.00")
            for p in basket:
                qty = random.randint(1, 3)
                seasonal = self._seasonal_weekly_multiplier(p, order_dt)
                if random.random() > min(seasonal, 1.5) / 1.5:
                    continue
                unit_price = (p.online_price or Decimal("0.00")) * Decimal(str(value_mult))
                unit_price = unit_price.quantize(Decimal("0.01"))
                OnlineOrderItem.objects.create(order=order, product=p, quantity=qty, unit_price=unit_price)
                total += unit_price * qty

            if total == 0:
                order.delete()
                continue

            order.total_amount = total.quantize(Decimal("0.01"))
            order.save(update_fields=["total_amount"])

            success, ref = order.simulate_payment()
            if not success:
                order.status = "cancelled"
                order.save(update_fields=["status"])
                continue

            order.record_payment_confirmation(ref)

            try:
                order.confirm_order()
            except ValueError:
                # stock genuinely insufficient despite the buffer — skip this one order
                order.status = "cancelled"
                order.save(update_fields=["status"])
                continue

            if order.linked_sale_id:
                Sale.objects.filter(id=order.linked_sale_id).update(sale_date=order_dt)

            any_created = True

        return any_created

    # ------------------------------------------------------------------
    # Browsing events (for price_sensitive segment to be reachable)
    # ------------------------------------------------------------------
    def _generate_customer_events(self, customers, online_products):
        if not online_products:
            return
        sample_size = max(1, len(customers) // 4)
        sample = random.sample(customers, min(sample_size, len(customers)))
        rows = []
        for c in sample:
            n_views = random.randint(15, 40)
            for _ in range(n_views):
                p = random.choice(online_products)
                dt = self.window_start + timedelta(
                    seconds=random.randint(0, int((self.now - self.window_start).total_seconds()))
                )
                rows.append(CustomerEvent(
                    customer=c, event_type="product_view", product=p,
                    category=p.category, created_at=dt,
                ))
        CustomerEvent.objects.bulk_create(rows, batch_size=500)

    # ------------------------------------------------------------------
    # Walk-in (anonymous) sales across the FULL catalogue
    # ------------------------------------------------------------------
    def _generate_walk_in_sales(self, products, staff_users):
        weeks = max(1, (self.months * 30) // 7)
        for p in products:
            base_weekly = 1.2 * self._tier_multiplier(p.id)
            for week in range(weeks):
                expected = base_weekly
                n_sales = max(0, int(round(random.gauss(expected, expected * 0.4 + 0.01))))
                for _ in range(n_sales):
                    day_offset = week * 7 + random.randint(0, 6)
                    dt = self.now - timedelta(days=(weeks * 7 - day_offset))
                    dt = timezone.make_aware(
                        datetime.combine(dt.date(), time(hour=random.randint(9, 19)))
                    ) if timezone.is_naive(dt) else dt
                    if dt < self.window_start or dt > self.now:
                        continue

                    seasonal = self._seasonal_weekly_multiplier(p, dt)
                    if random.random() > min(seasonal, 1.5) / 1.5:
                        continue

                    qty = random.randint(1, 4)
                    if p.quantity_in_stock < qty:
                        continue

                    sale = Sale.objects.create(
                        served_by=random.choice(staff_users),
                        status="completed",
                        notes=f"{SEED_MARKER} walk-in sale",
                    )
                    SaleItem.objects.create(sale=sale, product=p, quantity=qty, unit_price=p.unit_price)
                    sale.calculate_total()
                    Sale.objects.filter(id=sale.id).update(sale_date=dt)

    # ------------------------------------------------------------------
    # Expenses
    # ------------------------------------------------------------------
    def _generate_expenses(self, staff_users):
        categories = {}
        for name, lo, hi, freq in EXPENSE_CATEGORIES:
            cat, _ = ExpenseCategory.objects.get_or_create(
                name=name, defaults={"description": f"{SEED_MARKER} generated category"}
            )
            categories[name] = (cat, lo, hi, freq)

        current = self.window_start.date()
        end = self.now.date()
        while current <= end:
            for name, (cat, lo, hi, freq) in categories.items():
                should_record = (
                    (freq == "monthly" and current.day == 1)
                    or (freq == "weekly" and current.weekday() == 0)
                )
                if should_record:
                    amount = Decimal(random.randint(lo, hi))
                    # gentle upward drift for realism (costs rising over the window)
                    days_in = (current - self.window_start.date()).days
                    drift = Decimal("1.0") + Decimal(str(days_in)) / Decimal(str(max(self.months * 30, 1))) * Decimal("0.15")
                    amount = (amount * drift).quantize(Decimal("0.01"))
                    Expense.objects.create(
                        category=cat,
                        description=f"{SEED_MARKER} {name} — {current.strftime('%B %Y')}",
                        amount=amount,
                        expense_date=current,
                        recorded_by=random.choice(staff_users),
                    )
            current += timedelta(days=1)

    # ------------------------------------------------------------------
    # Additional periodic inventory history (beyond the initial buffer)
    # ------------------------------------------------------------------
    def _generate_inventory_history(self, products, staff_users):
        rows = []
        for p in products:
            n_events = random.randint(2, 6)
            for _ in range(n_events):
                dt = self.window_start + timedelta(
                    seconds=random.randint(0, int((self.now - self.window_start).total_seconds()))
                )
                qty = int(20 * self._tier_multiplier(p.id))
                receipt = StockReceipt.objects.create(
                    product=p, quantity_received=max(qty, 5),
                    received_by=random.choice(staff_users),
                    notes=f"{SEED_MARKER} periodic restock",
                )
                rows.append((receipt.id, dt))
        self._fix_dates(StockReceipt, "receipt_date", rows)

    # ------------------------------------------------------------------
    # Cleanup — removes everything this command previously created,
    # identified ONLY via the markers this command itself writes
    # (@SEED_EMAIL_DOMAIN emails, SEED_MARKER text in notes/reason/
    # description). Never touches anything without one of those markers.
    # Also reverses the net stock quantity change caused by seeded
    # StockReceipt/InventoryAdjustment/SaleItem rows before deleting
    # them, so Product.quantity_in_stock returns to its pre-seed value
    # rather than staying permanently skewed by deleted history.
    # ------------------------------------------------------------------
    def _cleanup_seed_data(self):
        from django.db.models import Sum

        self.stdout.write("Reversing stock effects of seeded inventory/sales records...")

        stock_delta = defaultdict(int)  # product_id -> net change to REVERSE (subtract this)

        for row in InventoryAdjustment.objects.filter(reason__icontains=SEED_MARKER).values(
            "product_id", "adjustment_type"
        ).annotate(total=Sum("quantity")):
            sign = 1 if row["adjustment_type"] == "addition" else -1
            stock_delta[row["product_id"]] += sign * row["total"]

        for row in StockReceipt.objects.filter(notes__icontains=SEED_MARKER).values(
            "product_id"
        ).annotate(total=Sum("quantity_received")):
            stock_delta[row["product_id"]] += row["total"]

        seeded_customer_ids = list(
            OnlineCustomer.objects.filter(email__iendswith=f"@{SEED_EMAIL_DOMAIN}").values_list("id", flat=True)
        )

        walk_in_sale_ids = list(Sale.objects.filter(notes__icontains=f"{SEED_MARKER} walk-in sale").values_list("id", flat=True))
        online_seed_sale_ids = list(
            Sale.objects.filter(online_order__customer_id__in=seeded_customer_ids).values_list("id", flat=True)
        )
        all_seed_sale_ids = list(set(walk_in_sale_ids) | set(online_seed_sale_ids))

        for row in SaleItem.objects.filter(sale_id__in=all_seed_sale_ids).values("product_id").annotate(total=Sum("quantity")):
            stock_delta[row["product_id"]] -= row["total"]  # sales REDUCED stock, so reversing means ADDING it back

        for product_id, delta in stock_delta.items():
            if delta:
                Product.objects.filter(id=product_id).update(
                    quantity_in_stock=models.F("quantity_in_stock") - delta
                )

        self.stdout.write("Deleting seeded online orders and their linked Sale records...")
        SaleItem.objects.filter(sale_id__in=all_seed_sale_ids).delete()
        Sale.objects.filter(id__in=all_seed_sale_ids).delete()
        OnlineOrder.objects.filter(customer_id__in=seeded_customer_ids).delete()  # cascades OnlineOrderItem

        self.stdout.write("Deleting seeded browsing events and insight snapshots...")
        CustomerEvent.objects.filter(customer_id__in=seeded_customer_ids).delete()
        from customer_insights.models import CustomerInsightSnapshot
        CustomerInsightSnapshot.objects.filter(customer_id__in=seeded_customer_ids).delete()

        self.stdout.write(f"Deleting {len(seeded_customer_ids)} seeded customers...")
        OnlineCustomer.objects.filter(id__in=seeded_customer_ids).delete()

        self.stdout.write("Deleting seeded inventory adjustments, stock receipts, and expenses...")
        InventoryAdjustment.objects.filter(reason__icontains=SEED_MARKER).delete()
        StockReceipt.objects.filter(notes__icontains=SEED_MARKER).delete()
        Expense.objects.filter(description__icontains=SEED_MARKER).delete()

        self.stdout.write(self.style.SUCCESS("Seed data removed. Original data was not touched."))
        self.stdout.write(self.style.WARNING(
            "NOTE: DemandForecast rows are NOT touched by this cleanup — that model has no "
            "seed marker and no reliable way to distinguish test-run forecasts from real ones "
            "(it's append-only history and every generate_forecasts_for_all() run adds fresh "
            "rows without deleting old ones, seeded or not). This is harmless for correctness: "
            "the Advisor only ever reads the LATEST row per product, so stale test-run forecasts "
            "are never surfaced and will be superseded the next time you run forecasts. If you "
            "want the table itself fully clean, you would need to manually inspect "
            "DemandForecast.generated_at timestamps and decide a cutoff yourself — I don't have "
            "a safe automated way to identify which specific rows came from the test run."
        ))

    # ------------------------------------------------------------------
    # Shared auto_now_add workaround
    # ------------------------------------------------------------------
    def _fix_dates(self, model, field_name, id_date_pairs):
        """
        Fixes an auto_now_add field after creation. .update() bypasses
        auto_now_add (which only fires on instance .save()), so this is
        the correct way to backdate these rows without touching the
        model definitions themselves.
        """
        for obj_id, dt in id_date_pairs:
            model.objects.filter(id=obj_id).update(**{field_name: dt})