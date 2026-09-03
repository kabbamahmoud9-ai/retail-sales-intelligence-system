from django.test import TestCase
from .services import calculate_sales_notification
class SalesNotificationTests(TestCase):
    def test_equal_sales_no_notification(self):
        self.assertIsNone(calculate_sales_notification(today_sales=100, yesterday_sales=100))

    def test_fifty_percent_increase(self):
        result = calculate_sales_notification(today_sales=1500, yesterday_sales=1000)
        self.assertIn("Up 50%", result['title'])

    def test_double_sales_hundred_percent_increase(self):
        result = calculate_sales_notification(today_sales=2000, yesterday_sales=1000)
        self.assertIn("Up 100%", result['title'])

    def test_more_than_double_sales(self):
        result = calculate_sales_notification(today_sales=3500, yesterday_sales=1000)
        self.assertIn("Up 250%", result['title'])

    def test_fifty_percent_decrease(self):
        result = calculate_sales_notification(today_sales=500, yesterday_sales=1000)
        self.assertIn("Down 50%", result['title'])

    def test_zero_previous_period_with_sales_today(self):
        result = calculate_sales_notification(today_sales=500, yesterday_sales=0)
        self.assertEqual(result['title'], "First Sales Recorded Today")

    def test_zero_previous_and_zero_today(self):
        self.assertIsNone(calculate_sales_notification(today_sales=0, yesterday_sales=0))

    def test_near_zero_baseline_does_not_produce_extreme_percentage(self):
        # regression test for the "Sales Up 12367%" bug
        result = calculate_sales_notification(today_sales=998, yesterday_sales=8)
        self.assertIsNone(result)

    def test_small_change_below_threshold_no_notification(self):
        result = calculate_sales_notification(today_sales=1050, yesterday_sales=1000)  # 5%, below 10% threshold
        self.assertIsNone(result)