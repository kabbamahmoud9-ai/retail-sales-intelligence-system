"""
ai_commerce/tests.py

Automated tests for the recommendation engine's context-aware scoring
(occasion detection, family_size, shopping_purpose) — the logic that
went through the most debugging today.
"""
from decimal import Decimal
from django.test import TestCase
from unittest import mock

from products.models import Product, Category
from ecommerce.models import OnlineCustomer
from ai_commerce.models import ShoppingSession
from ai_commerce.services import generate_shopping_recommendations, _detect_dish_categories


class OccasionDetectionTests(TestCase):
    """Covers the exact bug chain debugged today: birthday/wedding -> Cooking Oil."""

    def test_birthday_maps_to_party_categories_not_cooking_oil(self):
        categories = _detect_dish_categories("I'm having my birthday party")
        self.assertIn('Beverages', categories)
        self.assertNotIn('Cooking Oil', categories)

    def test_wedding_maps_to_beverage_categories(self):
        categories = _detect_dish_categories("I need food for a wedding")
        self.assertIn('Beverages', categories)

    def test_generic_food_request_has_no_occasion_match(self):
        """No forced occasion for genuinely generic requests."""
        categories = _detect_dish_categories("I need some food")
        self.assertEqual(categories, [])

    def test_occasion_categories_preserve_priority_order(self):
        """The tie-breaking fix: first-listed category should win ties."""
        categories = _detect_dish_categories("birthday party")
        self.assertTrue(len(categories) > 0)
        # 'birthday' is defined before 'party' in the map, first match should lead
        self.assertEqual(categories[0], 'Water & Soft Drinks')


class RecommendationEngineTests(TestCase):

    def setUp(self):
        self.beverages = Category.objects.create(category_name='Beverages')
        self.frozen = Category.objects.create(category_name='Frozen Foods')

        self.soda = Product.objects.create(
            product_name='Test Soda', category=self.beverages,
            unit_price=Decimal('10.00'), online_price=Decimal('10.00'),
            quantity_in_stock=50, is_active=True, is_available_online=True,
        )
        self.chicken = Product.objects.create(
            product_name='Test Frozen Chicken', category=self.frozen,
            unit_price=Decimal('50.00'), online_price=Decimal('50.00'),
            quantity_in_stock=50, is_active=True, is_available_online=True,
        )

        self.customer = OnlineCustomer(full_name='Test Customer', email='rec_test@example.com')
        self.customer.set_password('testpass123')
        self.customer.save()

    def test_birthday_party_prioritizes_beverages_over_frozen_food(self):
        """
        Direct regression test for today's actual bug: a birthday-party
        request should rank Beverages products above Frozen Foods, even
        though 'food' could fuzzy-match Frozen Foods too.
        """
        session = ShoppingSession.objects.create(
            customer=self.customer, mode='guided_planner',
            shopping_purpose="I'm having my birthday party and want food for guests",
        )
        recommendations = generate_shopping_recommendations(session)
        self.assertTrue(len(recommendations) > 0)
        # The Beverages product should outrank the Frozen Foods product
        soda_rec = next((r for r in recommendations if r.product == self.soda), None)
        chicken_rec = next((r for r in recommendations if r.product == self.chicken), None)
        if soda_rec and chicken_rec:
            self.assertLess(soda_rec.rank, chicken_rec.rank)

    def test_family_size_increases_basket_size(self):
        """Regression test for basket-size scaling (Step A)."""
        small_session = ShoppingSession.objects.create(
            customer=self.customer, mode='guided_planner', family_size=2,
        )
        large_session = ShoppingSession.objects.create(
            customer=self.customer, mode='guided_planner', family_size=10,
        )
        from ai_commerce.services import _effective_max_recommendations
        self.assertGreaterEqual(
            _effective_max_recommendations(large_session),
            _effective_max_recommendations(small_session),
        )

    def test_out_of_stock_products_never_recommended(self):
        """Grounding guarantee: zero-stock products must never appear."""
        self.soda.quantity_in_stock = 0
        self.soda.save()

        session = ShoppingSession.objects.create(
            customer=self.customer, mode='natural_language', raw_query='soda',
        )
        session.parsed_intent = {'categories': ['Beverages'], 'keywords': ['soda'], 'price_sensitivity': 'medium'}
        session.save()

        recommendations = generate_shopping_recommendations(session)
        recommended_products = [r.product for r in recommendations]
        self.assertNotIn(self.soda, recommended_products)

class _FakeRecommendation:
    """Minimal stand-in exposing only what build_validated_basket() reads."""
    def __init__(self, product, reasoning="test reasoning"):
        self.product = product
        self.reasoning = reasoning


class BasketValidationTests(TestCase):
    def setUp(self):
        from products.models import Category, Product
        from decimal import Decimal
        self.category = Category.objects.create(category_name="Rice & Grains")
        self.product_a = Product.objects.create(
            product_name="Test Rice 5kg", category=self.category,
            unit_price=Decimal("120.00"), online_price=Decimal("120.00"), quantity_in_stock=10,
            reorder_level=2, is_active=True, is_available_online=True,
        )
        self.product_b = Product.objects.create(
            product_name="Test Cooking Oil 1L", category=self.category,
            unit_price=Decimal("64.50"), online_price=Decimal("64.50"), quantity_in_stock=10,
            reorder_level=2, is_active=True, is_available_online=True,
        )

    def test_total_sums_correctly_across_multiple_items(self):
        from decimal import Decimal
        from ai_commerce.services import build_validated_basket
        recs = [_FakeRecommendation(self.product_a), _FakeRecommendation(self.product_b)]
        basket = build_validated_basket(recs, budget=None)
        self.assertEqual(basket["total"], Decimal("184.50"))
        self.assertEqual(len(basket["items"]), 2)

    def test_exceeds_budget_true_with_correct_negative_remaining(self):
        from decimal import Decimal
        from ai_commerce.services import build_validated_basket
        recs = [_FakeRecommendation(self.product_a), _FakeRecommendation(self.product_b)]
        basket = build_validated_basket(recs, budget=Decimal("150.00"))
        self.assertTrue(basket["exceeds_budget"])
        self.assertEqual(basket["remaining"], Decimal("-34.50"))

    def test_exceeds_budget_false_with_correct_positive_remaining(self):
        from decimal import Decimal
        from ai_commerce.services import build_validated_basket
        recs = [_FakeRecommendation(self.product_a), _FakeRecommendation(self.product_b)]
        basket = build_validated_basket(recs, budget=Decimal("200.00"))
        self.assertFalse(basket["exceeds_budget"])
        self.assertEqual(basket["remaining"], Decimal("15.50"))

    def test_no_budget_gives_none_remaining_and_exceeds(self):
        from decimal import Decimal
        from ai_commerce.services import build_validated_basket
        recs = [_FakeRecommendation(self.product_a)]
        basket = build_validated_basket(recs, budget=None)
        self.assertIsNone(basket["remaining"])
        self.assertIsNone(basket["exceeds_budget"])
        self.assertEqual(basket["total"], Decimal("120.00"))

    def test_empty_recommendation_list_gives_zero_total(self):
        from decimal import Decimal
        from ai_commerce.services import build_validated_basket
        basket = build_validated_basket([], budget=Decimal("100.00"))
        self.assertEqual(basket["total"], Decimal("0.00"))
        self.assertEqual(basket["remaining"], Decimal("100.00"))
        self.assertFalse(basket["exceeds_budget"])

    def test_float_budget_input_handled_same_as_decimal(self):
        from decimal import Decimal
        from ai_commerce.services import build_validated_basket
        recs = [_FakeRecommendation(self.product_a)]
        basket = build_validated_basket(recs, budget=150.0)
        self.assertEqual(basket["budget"], Decimal("150.0"))
        self.assertFalse(basket["exceeds_budget"])


class ShoppingQueryBasketIntegrationTests(TestCase):
    def setUp(self):
        from products.models import Category, Product
        from ecommerce.models import OnlineCustomer
        from decimal import Decimal
        self.category = Category.objects.create(category_name="Rice & Grains")
        self.product = Product.objects.create(
            product_name="Local Rice 5kg", category=self.category,
            unit_price=Decimal("120.00"), online_price=Decimal("120.00"), quantity_in_stock=10,
            reorder_level=2, is_active=True, is_available_online=True,
        )
        self.customer = OnlineCustomer.objects.create(
            full_name="Test Customer", email="basket_test@example.com", phone="0000000000",
        )
        self.customer.set_password("testpass123")
        self.customer.save()

    def test_reply_includes_total_line(self):
        from ai_commerce.conversational import _handle_shopping_query
        reply_text, routed_to = _handle_shopping_query(
            customer=self.customer, message_text="I need rice", context_state={},
        )
        self.assertIn("Total: Le", reply_text)
        self.assertEqual(routed_to, "shopping_assistant")

    def test_reply_includes_budget_status_when_budget_given(self):
        from ai_commerce.conversational import _handle_shopping_query
        reply_text, routed_to = _handle_shopping_query(
            customer=self.customer, message_text="I need rice", context_state={"budget": 200.0},
        )
        self.assertTrue("of your Le" in reply_text or "over your stated budget" in reply_text)

    def test_reply_omits_budget_status_when_no_budget_given(self):
        from ai_commerce.conversational import _handle_shopping_query
        reply_text, routed_to = _handle_shopping_query(
            customer=self.customer, message_text="I need rice", context_state={},
        )
        self.assertNotIn("your stated budget", reply_text)


class BudgetSlotExtractionTests(TestCase):
    def test_bare_guest_count_not_misread_as_budget(self):
        from ai_commerce.conversational import _extract_slots
        result = _extract_slots("I'm expecting 250 guests this weekend", {})
        self.assertNotIn('budget', result)
        self.assertEqual(result.get('family_size'), 250)

    def test_le_prefixed_amount_still_detected(self):
        from ai_commerce.conversational import _extract_slots
        result = _extract_slots("I have Le 200 to spend", {})
        self.assertEqual(result.get('budget'), 200.0)

    def test_leones_suffixed_amount_still_detected(self):
        from ai_commerce.conversational import _extract_slots
        result = _extract_slots("My budget is 150 leones", {})
        self.assertEqual(result.get('budget'), 150.0)

    def test_le_amount_immediately_followed_by_guests_not_misread(self):
        from ai_commerce.conversational import _extract_slots
        # Edge case: "Le 200 guests" is nonsensical phrasing, but confirms
        # the negative lookahead actually blocks this specific false-positive
        # shape rather than just the bare-number case above.
        result = _extract_slots("Le 200 guests are coming", {})
        self.assertNotIn('budget', result)

    def test_no_budget_mentioned_leaves_slot_unset(self):
        from ai_commerce.conversational import _extract_slots
        result = _extract_slots("I need rice for dinner", {})
        self.assertNotIn('budget', result)


class PurchaseHistoryScoringTests(TestCase):
    def setUp(self):
        from products.models import Category, Product
        from ecommerce.models import OnlineCustomer, OnlineOrder, OnlineOrderItem
        from decimal import Decimal

        self.category = Category.objects.create(category_name="Rice & Grains")
        self.other_category = Category.objects.create(category_name="Beverages")

        self.previously_bought = Product.objects.create(
            product_name="Local Rice 5kg", category=self.category,
            unit_price=Decimal("120.00"), online_price=Decimal("120.00"),
            quantity_in_stock=10, reorder_level=2,
            is_active=True, is_available_online=True,
        )
        self.same_category_new = Product.objects.create(
            product_name="Imported Rice 10kg", category=self.category,
            unit_price=Decimal("200.00"), online_price=Decimal("200.00"),
            quantity_in_stock=10, reorder_level=2,
            is_active=True, is_available_online=True,
        )
        self.unrelated_product = Product.objects.create(
            product_name="Bottled Water", category=self.other_category,
            unit_price=Decimal("15.00"), online_price=Decimal("15.00"),
            quantity_in_stock=10, reorder_level=2,
            is_active=True, is_available_online=True,
        )

        self.customer = OnlineCustomer.objects.create(
            full_name="History Test Customer", email="history_test@example.com", phone="0000000001",
        )
        self.customer.set_password("testpass123")
        self.customer.save()

        order = OnlineOrder.objects.create(
            customer=self.customer, status='delivered',
        )
        OnlineOrderItem.objects.create(
            order=order, product=self.previously_bought,
            quantity=3, unit_price=self.previously_bought.online_price,
        )

        self.guest_customer = None  # represents no logged-in customer

    def test_previously_bought_product_gets_higher_score_than_unpurchased(self):
        from ai_commerce.services import _score_and_explain_one, _get_customer_purchase_signal
        from ai_commerce.models import ShoppingSession

        session = ShoppingSession.objects.create(
            customer=self.customer, mode='natural_language', raw_query="rice",
        )
        purchase_categories, product_order_counts = _get_customer_purchase_signal(self.customer)

        score_bought, reasoning_bought = _score_and_explain_one(
            session, self.previously_bought, categories=[], keywords=[],
            quality_preference=None, purchase_categories=purchase_categories,
            product_order_counts=product_order_counts,
        )
        score_new, reasoning_new = _score_and_explain_one(
            session, self.unrelated_product, categories=[], keywords=[],
            quality_preference=None, purchase_categories=purchase_categories,
            product_order_counts=product_order_counts,
        )
        self.assertGreater(score_bought, score_new)
        self.assertIn("you've ordered this before", reasoning_bought)

    def test_same_category_unpurchased_product_gets_smaller_bonus_than_exact_repurchase(self):
        from ai_commerce.services import _score_and_explain_one, _get_customer_purchase_signal
        from ai_commerce.models import ShoppingSession

        session = ShoppingSession.objects.create(
            customer=self.customer, mode='natural_language', raw_query="rice",
        )
        purchase_categories, product_order_counts = _get_customer_purchase_signal(self.customer)

        score_exact, _ = _score_and_explain_one(
            session, self.previously_bought, categories=[], keywords=[],
            quality_preference=None, purchase_categories=purchase_categories,
            product_order_counts=product_order_counts,
        )
        score_same_category, reasoning_same_category = _score_and_explain_one(
            session, self.same_category_new, categories=[], keywords=[],
            quality_preference=None, purchase_categories=purchase_categories,
            product_order_counts=product_order_counts,
        )
        self.assertGreater(score_exact, score_same_category)
        self.assertIn("you've purchased from Rice & Grains before", reasoning_same_category)

    def test_guest_customer_gets_no_purchase_bonus(self):
        from ai_commerce.services import _get_customer_purchase_signal
        purchase_categories, product_order_counts = _get_customer_purchase_signal(None)
        self.assertEqual(purchase_categories, set())
        self.assertEqual(product_order_counts, {})

    def test_customer_with_no_orders_gets_no_purchase_bonus(self):
        from ecommerce.models import OnlineCustomer
        from ai_commerce.services import _get_customer_purchase_signal

        new_customer = OnlineCustomer.objects.create(
            full_name="No History Customer", email="nohistory@example.com", phone="0000000002",
        )
        purchase_categories, product_order_counts = _get_customer_purchase_signal(new_customer)
        self.assertEqual(purchase_categories, set())
        self.assertEqual(product_order_counts, {})

class ShoppingPromptBudgetFactTests(TestCase):
    def setUp(self):
        from products.models import Category, Product
        from ecommerce.models import OnlineCustomer
        from decimal import Decimal

        self.category = Category.objects.create(category_name="Rice & Grains")
        self.product = Product.objects.create(
            product_name="Local Rice 5kg", category=self.category,
            unit_price=Decimal("120.00"), online_price=Decimal("120.00"),
            quantity_in_stock=10, reorder_level=2,
            is_active=True, is_available_online=True,
        )
        self.customer = OnlineCustomer.objects.create(
            full_name="Prompt Test Customer", email="prompt_test@example.com", phone="0000000003",
        )
        self.customer.set_password("testpass123")
        self.customer.save()

    def test_prompt_states_exceeds_budget_as_fact(self):
        from ai_commerce.llm_adapter import _build_shopping_prompt
        base_reply, routed_to, prompt = _build_shopping_prompt(
            self.customer, "I need rice", {"budget": 50.0},
        )
        self.assertIn("IMPORTANT FACT", prompt)
        self.assertIn("EXCEEDS", prompt)
        self.assertIn("already computed by the backend", prompt)
        self.assertEqual(routed_to, "shopping_assistant")

    def test_prompt_states_fits_budget_as_fact(self):
        from ai_commerce.llm_adapter import _build_shopping_prompt
        base_reply, routed_to, prompt = _build_shopping_prompt(
            self.customer, "I need rice", {"budget": 200.0},
        )
        self.assertIn("IMPORTANT FACT", prompt)
        self.assertIn("fits within", prompt)
        self.assertIn("remaining", prompt)

    def test_prompt_omits_budget_fact_when_no_budget_given(self):
        from ai_commerce.llm_adapter import _build_shopping_prompt
        base_reply, routed_to, prompt = _build_shopping_prompt(
            self.customer, "I need rice", {},
        )
        self.assertNotIn("IMPORTANT FACT", prompt)

    def test_prompt_never_asks_llm_to_judge_budget_itself(self):
        """Regression guard: the old 'if you believe your budget is exceeded,
        say so honestly' phrasing must never reappear in any budget state."""
        from ai_commerce.llm_adapter import _build_shopping_prompt
        for budget in (50.0, 200.0, None):
            context_state = {"budget": budget} if budget is not None else {}
            _, _, prompt = _build_shopping_prompt(self.customer, "I need rice", context_state)
            self.assertNotIn("if you believe", prompt.lower())

    def test_rephrased_response_used_when_provider_returns_text(self):
        from ai_commerce.llm_adapter import get_llm_response
        from django.conf import settings

        with mock.patch("ai_commerce.llm_adapter.ai_generate", return_value="Mocked rephrased reply"):
            reply_text, routed_to = get_llm_response("I need rice", {}, self.customer)

        self.assertEqual(reply_text, "Mocked rephrased reply")
        self.assertEqual(routed_to, f"shopping_assistant+{settings.AI_PROVIDER}")

    def test_falls_back_to_base_reply_when_provider_returns_none(self):
        from ai_commerce.llm_adapter import get_llm_response

        with mock.patch("ai_commerce.llm_adapter.ai_generate", return_value=None):
            reply_text, routed_to = get_llm_response("I need rice", {}, self.customer)

        self.assertIn("Here are a few options", reply_text)
        self.assertEqual(routed_to, "shopping_assistant")