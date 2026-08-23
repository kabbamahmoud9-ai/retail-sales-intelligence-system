"""
advisor/tests.py

Automated tests for the Business Advisor's domain-based diagnostic
routing (Priority 2 of the AI-improvement session). Zero prior test
coverage existed for advisor/ before this file.
"""
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth import get_user_model

from advisor.conversational import _detect_diagnostic_domains
from advisor import data_gathering as dg


class DiagnosticDomainDetectionTests(SimpleTestCase):
    """
    _detect_diagnostic_domains() is pure -- no DB access -- so these use
    SimpleTestCase (no test database needed, faster).
    """

    def test_churn_question_detects_churn_domain(self):
        domains = _detect_diagnostic_domains("Why is customer retention concerning this month?")
        self.assertIn('churn', domains)

    def test_delivery_question_detects_delivery_domain(self):
        domains = _detect_diagnostic_domains("How are our delivery zones performing?")
        self.assertIn('delivery', domains)

    def test_blockchain_question_detects_blockchain_domain(self):
        domains = _detect_diagnostic_domains("Has the audit ledger been tampered with?")
        self.assertIn('blockchain', domains)

    def test_question_spanning_multiple_domains_detects_both(self):
        domains = _detect_diagnostic_domains("How do sales compare to expenses this month?")
        self.assertIn('sales', domains)
        self.assertIn('expenses', domains)

    def test_generic_question_returns_empty_set(self):
        domains = _detect_diagnostic_domains("How is the business doing overall?")
        self.assertEqual(domains, set())

    def test_plural_and_inflected_forms_still_match(self):
        domains = _detect_diagnostic_domains("What sold well this week?")
        self.assertIn('sales', domains)

    def test_unmet_demand_question_detects_unmet_demand_domain(self):
        domains = _detect_diagnostic_domains("What have customers requested that we don't stock?")
        self.assertIn('unmet_demand', domains)

    def test_inventory_activity_question_detects_inventory_activity_domain(self):
        domains = _detect_diagnostic_domains("Were there any recent stock adjustments?")
        self.assertIn('inventory_activity', domains)


class DiagnosticContextScopingTests(TestCase):
    """
    Mocks each individual get_* computer function rather than hitting
    real models across forecasting/sales/customer_insights/delivery/
    expenses/blockchain -- this tests the scoping logic itself (which
    functions get called for which domain set) without depending on
    field names or fixtures from six different apps.
    """

    def _mock_all_computers(self):
        """Patches every function get_business_diagnostic_context() can
        call. Most return a generic sentinel; get_delivery_zone_profitability
        must return a real list, since its computer slices the result
        ([:3]) -- a sentinel isn't subscriptable."""
        return_values = {
            'get_todays_sales_summary': mock.sentinel.value,
            'get_top_selling_products': mock.sentinel.value,
            'get_slow_moving_products': mock.sentinel.value,
            'get_forecast_trend_summary': mock.sentinel.value,
            'get_expense_summary': mock.sentinel.value,
            'get_highest_churn_risk_customers': mock.sentinel.value,
            'get_delivery_zone_profitability': [],
            'get_blockchain_status': mock.sentinel.value,
            'get_period_over_period_comparison': mock.sentinel.value,
            'get_pending_customer_requests': mock.sentinel.value,
            'get_recent_inventory_activity': mock.sentinel.value,
        }
        patchers = {
            name: mock.patch.object(dg, name, return_value=value)
            for name, value in return_values.items()
        }
        mocks = {name: p.start() for name, p in patchers.items()}
        for p in patchers.values():
            self.addCleanup(p.stop)
        return mocks

    def test_domains_none_computes_everything(self):
        mocks = self._mock_all_computers()
        context = dg.get_business_diagnostic_context(domains=None)

        for name, m in mocks.items():
            m.assert_called_once()
        self.assertEqual(len(context), len(mocks))

    def test_churn_only_domain_skips_delivery_and_blockchain(self):
        mocks = self._mock_all_computers()
        context = dg.get_business_diagnostic_context(domains={'churn'})

        mocks['get_highest_churn_risk_customers'].assert_called_once()
        mocks['get_delivery_zone_profitability'].assert_not_called()
        mocks['get_blockchain_status'].assert_not_called()
        mocks['get_forecast_trend_summary'].assert_not_called()

        self.assertIn('highest_churn_risk_customers', context)
        self.assertNotIn('delivery_zone_profitability', context)
        self.assertNotIn('blockchain_status', context)

    def test_delivery_only_domain_computes_only_delivery(self):
        mocks = self._mock_all_computers()
        context = dg.get_business_diagnostic_context(domains={'delivery'})

        mocks['get_delivery_zone_profitability'].assert_called_once()
        mocks['get_blockchain_status'].assert_not_called()
        mocks['get_highest_churn_risk_customers'].assert_not_called()
        self.assertEqual(set(context.keys()), {'delivery_zone_profitability'})

    def test_sales_domain_includes_period_comparison(self):
        mocks = self._mock_all_computers()
        context = dg.get_business_diagnostic_context(domains={'sales'})

        mocks['get_period_over_period_comparison'].assert_called_once()
        self.assertIn('period_over_period_comparison', context)
        self.assertIn('todays_sales', context)
        mocks['get_blockchain_status'].assert_not_called()
    
    def test_unmet_demand_domain_computes_only_pending_requests(self):
        mocks = self._mock_all_computers()
        context = dg.get_business_diagnostic_context(domains={'unmet_demand'})

        mocks['get_pending_customer_requests'].assert_called_once()
        mocks['get_recent_inventory_activity'].assert_not_called()
        mocks['get_blockchain_status'].assert_not_called()
        self.assertEqual(set(context.keys()), {'pending_customer_requests'})

    def test_inventory_activity_domain_computes_only_activity(self):
        mocks = self._mock_all_computers()
        context = dg.get_business_diagnostic_context(domains={'inventory_activity'})

        mocks['get_recent_inventory_activity'].assert_called_once()
        mocks['get_pending_customer_requests'].assert_not_called()
        mocks['get_forecast_trend_summary'].assert_not_called()
        self.assertEqual(set(context.keys()), {'recent_inventory_activity'})

    def test_unrecognized_domain_falls_back_to_full_context(self):
        mocks = self._mock_all_computers()
        context = dg.get_business_diagnostic_context(domains={'not_a_real_domain'})

        for name, m in mocks.items():
            m.assert_called_once()
        self.assertEqual(len(context), len(mocks))

    def test_empty_set_falls_back_to_full_context(self):
        mocks = self._mock_all_computers()
        context = dg.get_business_diagnostic_context(domains=set())

        for name, m in mocks.items():
            m.assert_called_once()


class BusinessSummaryDiagnosticContextRegressionTests(TestCase):
    """
    Regression test for a pre-existing bug (found and fixed alongside
    Priority 2, not caused by it): process_message() referenced
    diagnostic_context on the business_summary branch without ever
    setting it, which raised NameError whenever AI_PROVIDER was not
    'rule_based'. Fixed by adding diagnostic_context = None to that
    branch.
    """

    def setUp(self):
        from advisor.models import AdvisorConversationSession

        User = get_user_model()
        self.staff_user = User.objects.create_user(
            username="advisor_test_staff", password="testpass123",
        )
        self.session = AdvisorConversationSession.objects.create(staff_user=self.staff_user)

    @override_settings(AI_PROVIDER='openai')
    def test_business_summary_does_not_raise_with_non_rule_based_provider(self):
        from advisor.conversational import process_message

        with mock.patch(
            "advisor.conversational.generate_business_health_summary",
            return_value={"headline": "steady"},
        ), mock.patch(
            "advisor.llm_explainer.explain",
            return_value="Rephrased summary.",
        ) as mock_explain:
            reply_text = process_message(self.session, self.staff_user, "give me a business summary")

        self.assertEqual(reply_text, "Rephrased summary.")
        mock_explain.assert_called_once_with("headline: steady", "give me a business summary")

    @override_settings(AI_PROVIDER='rule_based')
    def test_business_summary_unaffected_when_rule_based(self):
        from advisor.conversational import process_message

        with mock.patch(
            "advisor.conversational.generate_business_health_summary",
            return_value={"headline": "steady"},
        ):
            reply_text = process_message(self.session, self.staff_user, "give me a business summary")

        self.assertEqual(reply_text, "headline: steady")

class LlmExplainerSerializationTests(TestCase):
    """
    Covers _json_default() in advisor/llm_explainer.py -- the fix for
    CustomerInsightSnapshot/DeliveryZone/Product losing their relevant
    fields when structured_context was serialized with json.dumps(...,
    default=str). Confirms the LLM-facing serializer surfaces the
    figures each model's __str__ alone would have dropped, without
    touching data_gathering.py's return shapes or any rule-based
    handler.
    """

    def setUp(self):
        from products.models import Category, Product
        from delivery.models import DeliveryZone
        from ecommerce.models import OnlineCustomer
        from customer_insights.models import CustomerInsightSnapshot
        from decimal import Decimal

        category = Category.objects.create(category_name="Rice & Grains")
        self.product = Product.objects.create(
            product_name="Local Rice 5kg", category=category,
            unit_price=Decimal("120.00"), online_price=Decimal("120.00"),
            quantity_in_stock=7, reorder_level=2,
            is_active=True, is_available_online=True,
        )
        self.zone = DeliveryZone.objects.create(
            zone_name="Freetown Central",
            base_fee=Decimal("10.00"), per_km_rate=Decimal("2.00"),
            average_distance_km=Decimal("5.00"),
            estimated_operational_cost=Decimal("15.00"),
        )
        self.customer = OnlineCustomer.objects.create(
            full_name="Serialization Test Customer", email="serialization_test@example.com", phone="0000000005",
        )
        self.customer.set_password("testpass123")
        self.customer.save()
        self.snapshot = CustomerInsightSnapshot.objects.create(
            customer=self.customer, segment='at_risk', churn_risk_score=0.82,
        )

    def test_product_serialization_preserves_stock_not_just_name(self):
        from advisor.llm_explainer import _json_default

        result = _json_default(self.product)
        self.assertEqual(result["product_name"], "Local Rice 5kg")
        self.assertEqual(result["quantity_in_stock"], 7)

    def test_delivery_zone_serialization_preserves_name(self):
        from advisor.llm_explainer import _json_default

        result = _json_default(self.zone)
        self.assertEqual(result["zone_name"], "Freetown Central")

    def test_customer_insight_snapshot_serialization_preserves_churn_score(self):
        from advisor.llm_explainer import _json_default

        result = _json_default(self.snapshot)
        self.assertEqual(result["customer_name"], "Serialization Test Customer")
        self.assertEqual(result["churn_risk_score"], 0.82)
        self.assertIn("segment", result)

    def test_unrecognized_type_falls_back_to_str(self):
        from advisor.llm_explainer import _json_default

        result = _json_default(self.customer)
        self.assertEqual(result, str(self.customer))

    def test_explain_produces_valid_json_containing_model_instances(self):
        """
        End-to-end guard: explain() must not raise when structured_context
        embeds real model instances, and the resulting JSON must actually
        contain the churn score / stock figure, not just a bare __str__.
        """
        from unittest import mock
        from advisor.llm_explainer import explain

        context = {
            "highest_churn_risk_customers": [self.snapshot],
            "delivery_zone_profitability": [
                {"zone": self.zone, "estimated_profit_per_delivery": 3.50, "order_count": 12}
            ],
            "forecast_trend": {"increasing_products": [self.product]},
        }

        captured_prompt = {}

        def _fake_generate(prompt, system_instruction=None):
            captured_prompt["value"] = prompt
            return "Explained."

        with mock.patch("advisor.llm_explainer.ai_generate", side_effect=_fake_generate):
            result = explain("base reply", "why is churn high?", structured_context=context)

        self.assertEqual(result, "Explained.")
        self.assertIn("0.82", captured_prompt["value"])
        self.assertIn("Freetown Central", captured_prompt["value"])
        self.assertIn("Local Rice 5kg", captured_prompt["value"])