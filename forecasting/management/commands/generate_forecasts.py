"""
Production management command.
Generates a fresh weekly DemandForecast for every active product,
then triggers the AI Business Advisor to turn forecasts into
actionable recommendations.

Intended to run on a schedule (e.g. weekly cron / Task Scheduler),
but can also be run manually at any time.
"""
from django.core.management.base import BaseCommand

from forecasting.services import generate_forecasts_for_all
from advisor.services import generate_recommendations


class Command(BaseCommand):
    help = "Generates AI demand forecasts for all active products and advisor recommendations."

    def handle(self, *args, **options):
        self.stdout.write("Generating demand forecasts...")
        forecast_summary = generate_forecasts_for_all()
        self.stdout.write(self.style.SUCCESS(
            f"Forecasts complete: {forecast_summary['generated']} generated, "
            f"{forecast_summary['insufficient_data']} insufficient data, "
            f"{forecast_summary['total']} total active products."
        ))

        self.stdout.write("Generating AI Advisor recommendations...")
        advisor_summary = generate_recommendations()
        self.stdout.write(self.style.SUCCESS(
            f"Recommendations complete: {advisor_summary['created']} created "
            f"({advisor_summary['critical']} critical, {advisor_summary['high']} high, "
            f"{advisor_summary['medium']} medium, {advisor_summary['low']} low)."
        ))