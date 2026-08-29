"""
Exports the synthetic/demo evaluation dataset to CSV files in test_data/,
for dissertation Chapter 4 supplementary evidence.

READ-ONLY: this command never calls .save(), .update(), .create(), or
.delete() on any model. All access goes through .values() querysets to
avoid triggering save() side effects present on several models in this
project (e.g. SaleItem.save() decrements stock).

Synthetic-record identification (confirmed from seed_retail_data.py and
seed_demo_customer_history.py, not assumed):
  - OnlineCustomer: email ends with @seed.retailintel.local or
    @demo.retailintelligence.local
  - Sale (walk-in, no customer link): notes contains "[SEED] walk-in sale"
  - Sale (online-order-linked): reached via online_order.customer being
    in the seed/demo customer set
  - StockReceipt: notes contains "[SEED]"
  - InventoryAdjustment: reason contains "[SEED]"
  - Expense: description contains "[SEED]"
  - Product: no seed marker exists; the full current catalogue is
    exported as the "evaluation product catalogue" per explicit
    confirmation, not because it is seed-generated.
  - DemandForecast / CustomerInsightSnapshot: no seed marker exists on
    either model. Latest row per product/customer is exported (matching
    how the live system itself consumes these append-only tables),
    NOT the full history, to avoid presenting repeated test-run rows
    as if they were a curated longitudinal record.

Usage:
    python manage.py export_evaluation_data --dry-run
    python manage.py export_evaluation_data
"""
import csv
import os
from django.core.management.base import BaseCommand
from django.conf import settings

from products.models import Product
from ecommerce.models import OnlineCustomer, OnlineOrder
from sales.models import Sale, SaleItem
from inventory.models import StockReceipt, InventoryAdjustment
from expenses.models import Expense
from forecasting.models import DemandForecast
from customer_insights.models import CustomerEvent, CustomerInsightSnapshot

SEED_DOMAIN = "seed.retailintel.local"
DEMO_DOMAIN = "demo.retailintelligence.local"
SEED_MARKER = "[SEED]"

OUTPUT_DIR = os.path.join(settings.BASE_DIR, "test_data")


class Command(BaseCommand):
    help = "Exports synthetic/demo evaluation data to CSV files in test_data/. Read-only."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would be exported (file names + row counts) without writing any files."
        )

    def handle(self, *args, **opts):
        dry_run = opts["dry_run"]

        seed_customer_ids = list(
            OnlineCustomer.objects.filter(email__iendswith=f"@{SEED_DOMAIN}")
            .values_list("id", flat=True)
        )
        demo_customer_ids = list(
            OnlineCustomer.objects.filter(email__iendswith=f"@{DEMO_DOMAIN}")
            .values_list("id", flat=True)
        )
        cust_ids = seed_customer_ids + demo_customer_ids

        walkin_sale_ids = list(
            Sale.objects.filter(notes__icontains=f"{SEED_MARKER} walk-in sale")
            .values_list("id", flat=True)
        )
        online_sale_ids = list(
            Sale.objects.filter(online_order__customer_id__in=cust_ids)
            .values_list("id", flat=True)
        )
        all_sale_ids = list(set(walkin_sale_ids) | set(online_sale_ids))

        exports = []

        exports.append((
            "products.csv",
            Product.objects.all().order_by("id").values(
                "id", "category_id", "supplier_id", "product_name", "description",
                "unit_price", "quantity_in_stock", "reorder_level", "is_active",
                "is_available_online", "online_price", "created_at",
            )
        ))

        exports.append((
            "customers.csv",
            OnlineCustomer.objects.filter(id__in=cust_ids).order_by("id").values(
                "id", "full_name", "email", "phone", "address",
                "credit_limit", "credit_balance", "is_active", "created_at",
                "lifetime_spending", "total_orders", "last_purchase_date", "trust_score",
            )
        ))

        exports.append((
            "online_orders.csv",
            OnlineOrder.objects.filter(customer_id__in=cust_ids).order_by("id").values(
                "id", "customer_id", "order_reference", "order_date", "status",
                "payment_method", "delivery_zone_id", "delivery_fee",
                "delivery_distance_km", "delivery_status", "delivery_method",
                "payment_reference", "payment_confirmed", "total_amount",
                "linked_sale_id", "created_at",
            )
        ))

        exports.append((
            "sales.csv",
            Sale.objects.filter(id__in=all_sale_ids).order_by("id").values(
                "id", "sale_date", "total_amount", "status", "notes",
            )
        ))

        exports.append((
            "sale_items.csv",
            SaleItem.objects.filter(sale_id__in=all_sale_ids).order_by("id").values(
                "id", "sale_id", "product_id", "quantity", "unit_price",
            )
        ))

        exports.append((
            "stock_receipts.csv",
            StockReceipt.objects.filter(notes__icontains=SEED_MARKER).order_by("id").values(
                "id", "product_id", "quantity_received", "receipt_date", "notes",
            )
        ))

        exports.append((
            "inventory_adjustments.csv",
            InventoryAdjustment.objects.filter(reason__icontains=SEED_MARKER).order_by("id").values(
                "id", "product_id", "adjustment_type", "quantity", "reason", "adjusted_at",
            )
        ))

        exports.append((
            "expenses.csv",
            Expense.objects.filter(description__icontains=SEED_MARKER).order_by("id").values(
                "id", "category_id", "description", "amount", "expense_date", "created_at",
            )
        ))

        exports.append((
            "demand_forecasts.csv",
            DemandForecast.objects.order_by("product_id", "-generated_at")
            .distinct("product_id").values(
                "id", "product_id", "forecast_period_start", "forecast_period_end",
                "predicted_quantity", "historical_average", "trend", "confidence_score",
                "recommended_restock_quantity", "has_sufficient_data",
                "insufficient_data_message", "generated_at", "model_version",
            )
        ))

        exports.append((
            "customer_insights.csv",
            CustomerInsightSnapshot.objects.filter(customer_id__in=cust_ids)
            .order_by("customer_id", "-generated_at").distinct("customer_id").values(
                "id", "customer_id", "generated_at", "segment", "avg_order_value",
                "order_frequency_days", "favorite_category_id", "preferred_payment_method",
                "preferred_shopping_time", "has_sufficient_data", "prediction_method",
                "churn_risk_score", "predicted_next_purchase_date",
                "estimated_lifetime_value", "ai_summary_text", "recommended_product_ids",
                "model_version",
            )
        ))

        exports.append((
            "customer_events.csv",
            CustomerEvent.objects.filter(customer_id__in=cust_ids).order_by("id").values(
                "id", "customer_id", "session_key", "event_type", "product_id",
                "category_id", "search_term", "created_at",
            )
        ))

        self.stdout.write(self.style.NOTICE(
            f"{'DRY RUN — ' if dry_run else ''}Evaluation dataset export plan:"
        ))
        for filename, qs in exports:
            count = qs.count()
            self.stdout.write(f"  {filename}: {count} rows")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run only — no files written."))
            return

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        for filename, qs in exports:
            rows = list(qs)
            path = os.path.join(OUTPUT_DIR, filename)
            if not rows:
                self.stdout.write(self.style.WARNING(f"  {filename}: 0 rows — writing header-only file"))
                fieldnames = qs.query.values_select or []
            else:
                fieldnames = list(rows[0].keys())

            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in rows:
                    writer.writerow(row)

            self.stdout.write(self.style.SUCCESS(f"  wrote {filename}: {len(rows)} rows"))

        self.stdout.write(self.style.SUCCESS(f"\nDone. Files written to {OUTPUT_DIR}"))
