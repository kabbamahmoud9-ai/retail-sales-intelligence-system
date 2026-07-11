"""
Generates realistic demo customer/order/browsing history purely for
Customer Insights Engine development, ML validation, and dissertation
demonstration. Bypasses OnlineOrder.confirm_order() entirely — does NOT
touch stock, Sale, forecasting data, or the blockchain ledger. Demo
orders are identified by a 'DEMO-' order_reference prefix; demo
customers are identified by the @demo.retailintelligence.local email
domain — no schema changes to ecommerce models.

Idempotent: reruns update/recreate the same fixed set of demo customer
profiles rather than piling up duplicates. Use --reset to wipe and
regenerate all demo data cleanly.
"""
import random
from decimal import Decimal
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from ecommerce.models import OnlineCustomer, OnlineOrder, OnlineOrderItem
from products.models import Product, Category
from customer_insights.models import CustomerEvent

DEMO_DOMAIN = "demo.retailintelligence.local"
DEMO_PASSWORD = "DemoPass123"

# Explicit profile design — deliberately covers all 7 segments so the
# dissertation has clean, demonstrable examples of each, rather than
# relying on pure randomness to happen to produce variety.
PROFILES = [
    # (name_prefix, count, order_count_range, interval_days_range, order_value_multiplier, last_order_days_ago_range)
    ("VIP",             3, (12, 20), (5, 12),   3.0, (1, 10)),
    ("Frequent",        4, (6, 11),  (7, 18),   1.0, (1, 15)),
    ("Premium",         3, (3, 5),   (20, 40),  2.5, (5, 20)),
    ("Loyal",           3, (3, 6),   (15, 30),  1.0, (5, 25)),
    ("AtRisk",          3, (3, 7),   (10, 20),  1.0, (90, 150)),
    ("PriceSensitive",  2, (2, 3),   (25, 45),  0.6, (10, 40)),
    ("New",             2, (0, 1),   (0, 0),    1.0, (0, 5)),
]

PAYMENT_METHODS = ['cash_on_delivery', 'orange_money', 'afrimoney', 'credit']


class Command(BaseCommand):
    help = "Seeds realistic demo customer/order/browsing history for Customer Insights development and demo."

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Delete all existing demo data before reseeding.')
        parser.add_argument('--seed', type=int, default=42, help='Random seed for reproducibility.')

    def handle(self, *args, **options):
        random.seed(options['seed'])

        if options['reset']:
            demo_customers = OnlineCustomer.objects.filter(email__iendswith=f"@{DEMO_DOMAIN}")
            count = demo_customers.count()

            # OnlineOrder.customer uses on_delete=PROTECT (by design, to
            # protect real customer order history) — so orders and events
            # must be deleted explicitly BEFORE the customers themselves,
            # rather than relying on a cascade.
            OnlineOrder.objects.filter(customer__in=demo_customers).delete()
            CustomerEvent.objects.filter(customer__in=demo_customers).delete()
            demo_customers.delete()

            self.stdout.write(self.style.WARNING(f"Reset: deleted {count} existing demo customers and their data."))

        active_products = list(Product.objects.filter(is_active=True, is_available_online=True))
        if not active_products:
            self.stderr.write(self.style.ERROR("No active, online-available products found — cannot seed orders."))
            return

        categories = list(Category.objects.all())
        total_created = 0

        for prefix, count, order_range, interval_range, value_mult, last_order_range in PROFILES:
            for i in range(1, count + 1):
                email = f"{prefix.lower()}{i}@{DEMO_DOMAIN}"
                customer, created = OnlineCustomer.objects.get_or_create(
                    email=email,
                    defaults={
                        'full_name': f"Demo {prefix} Customer {i}",
                        'phone': f"0800{random.randint(100000, 999999)}",
                        'address': "123 Demo Street, Freetown",
                    }
                )
                if created:
                    customer.set_password(DEMO_PASSWORD)
                    customer.save()
                    # Force a DB round-trip so Decimal fields (lifetime_spending,
                    # credit_limit, credit_balance) come back as real Decimal
                    # instances rather than the raw float default — avoids a
                    # float/Decimal TypeError in record_confirmed_order() below
                    # for brand-new customers created in this same process.
                    customer.refresh_from_db()

                order_count = random.randint(*order_range)
                last_order_days_ago = random.randint(*last_order_range)

                # Work backwards from "days ago of most recent order" so
                # AtRisk profiles genuinely have a stale last order date.
                order_date = timezone.now() - timedelta(days=last_order_days_ago)

                order_dates = [order_date]
                for _ in range(order_count - 1):
                    gap = random.randint(*interval_range) if interval_range != (0, 0) else 0
                    order_date = order_date - timedelta(days=gap, hours=random.randint(0, 23))
                    order_dates.append(order_date)
                order_dates.reverse()  # chronological order

                for od in order_dates:
                    # Browsing events leading up to this order (2-5 views/searches
                    # in the days before purchase) — richer behaviour signal.
                    event_count = random.randint(2, 5)
                    for _ in range(event_count):
                        event_time = od - timedelta(
                            days=random.randint(0, 4), hours=random.randint(0, 23)
                        )
                        event_type = random.choices(
                            ['product_view', 'category_view', 'search_query'],
                            weights=[0.6, 0.25, 0.15],
                        )[0]
                        product = random.choice(active_products)
                        if event_type == 'product_view':
                            CustomerEvent.objects.create(
                                customer=customer, event_type='product_view',
                                product=product, created_at=event_time,
                            )
                        elif event_type == 'category_view' and categories:
                            CustomerEvent.objects.create(
                                customer=customer, event_type='category_view',
                                category=random.choice(categories), created_at=event_time,
                            )
                        else:
                            CustomerEvent.objects.create(
                                customer=customer, event_type='search_query',
                                search_term=product.product_name.split()[0], created_at=event_time,
                            )

                    # Extra "window shopping" events for Price-Sensitive profiles —
                    # more views without a proportional purchase.
                    if prefix == "PriceSensitive":
                        for _ in range(random.randint(4, 8)):
                            event_time = od - timedelta(days=random.randint(0, 10), hours=random.randint(0, 23))
                            CustomerEvent.objects.create(
                                customer=customer, event_type='product_view',
                                product=random.choice(active_products), created_at=event_time,
                            )

                    # Build the order itself
                    item_count = random.randint(1, 4)
                    chosen_products = random.sample(active_products, min(item_count, len(active_products)))

                    order = OnlineOrder.objects.create(
                        customer=customer,
                        order_reference=f"DEMO-{customer.id}-{od.strftime('%Y%m%d%H%M%S')}",
                        order_date=od,
                        status='confirmed',
                        delivery_address=customer.address,
                        payment_method=random.choice(PAYMENT_METHODS),
                        payment_confirmed=True,
                        payment_reference=f"DEMO-PAY-{random.randint(100000, 999999)}",
                        total_amount=0,  # computed below
                    )

                    order_total = 0
                    for product in chosen_products:
                        qty = random.randint(1, 3)
                        unit_price = (product.online_price or product.unit_price) * Decimal(str(value_mult))
                        OnlineOrderItem.objects.create(
                            order=order, product=product,
                            quantity=qty, unit_price=unit_price,
                        )
                        order_total += unit_price * qty

                    order.total_amount = order_total
                    order.save(update_fields=['total_amount'])

                    # Reuse the existing single entry point for customer-stat
                    # updates — safe here since it only touches OnlineCustomer
                    # fields, never Sale/stock/blockchain (Decision 20).
                    customer.record_confirmed_order(order)

                total_created += 1
                self.stdout.write(f"  Seeded: {customer.full_name} — {order_count} orders")

        self.stdout.write(self.style.SUCCESS(f"\nDone. Seeded/updated {total_created} demo customers."))