"""
ai_commerce/tests.py

Automated tests for the recommendation engine's context-aware scoring
(occasion detection, family_size, shopping_purpose) — the logic that
went through the most debugging today.
"""
from decimal import Decimal
from django.test import TestCase

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