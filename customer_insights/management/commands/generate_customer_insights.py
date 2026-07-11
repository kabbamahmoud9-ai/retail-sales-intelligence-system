from django.core.management.base import BaseCommand
from ecommerce.models import OnlineCustomer
from customer_insights.services import generate_customer_insight


class Command(BaseCommand):
    help = "Generates a fresh CustomerInsightSnapshot for every active customer. Append-only — never overwrites prior snapshots."

    def handle(self, *args, **options):
        customers = OnlineCustomer.objects.filter(is_active=True)
        total = customers.count()
        self.stdout.write(f"Generating insights for {total} customers...")

        ml_count = 0
        rule_count = 0

        for customer in customers:
            snapshot = generate_customer_insight(customer)
            method_label = "ML" if snapshot.prediction_method == 'ml' else "rule-based"
            if snapshot.prediction_method == 'ml':
                ml_count += 1
            else:
                rule_count += 1
            self.stdout.write(f"  {customer.full_name}: {snapshot.get_segment_display()} ({method_label})")

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {total} snapshots created — {ml_count} ML-based, {rule_count} rule-based fallback."
        ))