from django.test import TestCase

def test_churn_risk_percent_matches_narrative(self):
    """The three representations of churn risk must never disagree."""
    customer = make_customer_with_orders(...)  # however your existing fixtures build one
    snapshot = generate_customer_insight(customer)

    expected_pct = round(snapshot.churn_risk_score * 100)

    self.assertEqual(snapshot.churn_risk_percent, expected_pct)
    self.assertIn(f"{expected_pct}%", snapshot.ai_summary_text)

def test_churn_risk_percent_scale_conversion(self):
    snapshot = CustomerInsightSnapshot(churn_risk_score=0.80)
    self.assertEqual(snapshot.churn_risk_percent, 80)

def test_churn_risk_percent_none_when_score_none(self):
    snapshot = CustomerInsightSnapshot(churn_risk_score=None)
    self.assertIsNone(snapshot.churn_risk_percent)

def test_churn_risk_percent_rounding(self):
    # guards against the exact 0.8 -> "1%" bug
    snapshot = CustomerInsightSnapshot(churn_risk_score=0.005)
    self.assertEqual(snapshot.churn_risk_percent, 1)  # rounds up, not floatformat-on-fraction
    snapshot2 = CustomerInsightSnapshot(churn_risk_score=0.994)
    self.assertEqual(snapshot2.churn_risk_percent, 99)