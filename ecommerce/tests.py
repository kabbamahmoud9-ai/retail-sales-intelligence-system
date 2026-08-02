"""
ecommerce/tests.py

Automated tests for the highest-risk business paths: checkout/credit
integrity and blockchain audit trail correctness. Uses Django's test
framework — runs against a fresh, isolated test database, never touches
real dev/demo data.
"""
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone

from products.models import Product, Category
from ecommerce.models import OnlineCustomer, OnlineOrder, OnlineOrderItem
from blockchain.services import verify_chain
from blockchain.models import LedgerEntry


class CreditWorkflowTests(TestCase):
    """
    Covers the credit approval/purchase/repayment lifecycle fixed
    earlier — the exact bug where AI recommendations never reached
    OnlineCustomer.credit_limit.
    """

    def setUp(self):
        self.category = Category.objects.create(category_name='Test Category')
        self.product = Product.objects.create(
            product_name='Test Product', category=self.category,
            unit_price=Decimal('10.00'), online_price=Decimal('10.00'),
            quantity_in_stock=100, is_active=True, is_available_online=True,
        )
        self.customer = OnlineCustomer(full_name='Test Customer', email='test@example.com')
        self.customer.set_password('testpass123')
        self.customer.save()

    def test_new_customer_has_zero_credit_limit_by_default(self):
        """Confirms the original bug's starting condition."""
        self.assertEqual(self.customer.credit_limit, Decimal('0.00'))

    def test_credit_purchase_rejected_with_zero_limit(self):
        self.assertFalse(self.customer.can_afford_credit(Decimal('5.00')))

    def test_approving_credit_limit_enables_purchase(self):
        """The actual fix: staff-approved limit must enable credit purchases."""
        self.customer.credit_limit = Decimal('100.00')
        self.customer.save()
        self.assertTrue(self.customer.can_afford_credit(Decimal('50.00')))
        self.assertFalse(self.customer.can_afford_credit(Decimal('150.00')))

    def test_credit_repayment_reduces_balance_correctly(self):
        from ecommerce.credit_repayment_services import process_credit_repayment

        self.customer.credit_limit = Decimal('500.00')
        self.customer.credit_balance = Decimal('200.00')
        self.customer.save()

        success, message, repayment = process_credit_repayment(
            customer_id=self.customer.id, payment_method='orange_money', amount=Decimal('50.00')
        )
        self.customer.refresh_from_db()

        self.assertTrue(success)
        self.assertEqual(self.customer.credit_balance, Decimal('150.00'))
        self.assertIsNotNone(repayment)
        self.assertTrue(repayment.transaction_hash)

    def test_credit_repayment_rejects_overpayment(self):
        from ecommerce.credit_repayment_services import process_credit_repayment

        self.customer.credit_limit = Decimal('500.00')
        self.customer.credit_balance = Decimal('50.00')
        self.customer.save()

        success, message, repayment = process_credit_repayment(
            customer_id=self.customer.id, payment_method='orange_money', amount=Decimal('100.00')
        )

        self.assertFalse(success)
        self.assertIsNone(repayment)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.credit_balance, Decimal('50.00'))  # unchanged


class OrderConfirmationTests(TestCase):
    """Covers stock validation and the core order->sale integration."""

    def setUp(self):
        self.category = Category.objects.create(category_name='Test Category')
        self.product = Product.objects.create(
            product_name='Test Product', category=self.category,
            unit_price=Decimal('10.00'), online_price=Decimal('10.00'),
            quantity_in_stock=5, is_active=True, is_available_online=True,
        )
        self.customer = OnlineCustomer(full_name='Test Customer', email='test2@example.com')
        self.customer.set_password('testpass123')
        self.customer.save()

    def test_confirm_order_rejects_insufficient_stock(self):
        order = OnlineOrder.objects.create(
            customer=self.customer, delivery_address='Test Address',
            payment_method='cash_on_delivery', total_amount=Decimal('100.00'),
        )
        OnlineOrderItem.objects.create(order=order, product=self.product, quantity=10, unit_price=Decimal('10.00'))

        with self.assertRaises(ValueError):
            order.confirm_order()

    def test_confirm_order_deducts_stock_and_creates_ledger_entry(self):
        order = OnlineOrder.objects.create(
            customer=self.customer, delivery_address='Test Address',
            payment_method='cash_on_delivery', total_amount=Decimal('20.00'),
        )
        OnlineOrderItem.objects.create(order=order, product=self.product, quantity=2, unit_price=Decimal('10.00'))

        order.confirm_order()
        self.product.refresh_from_db()

        self.assertEqual(self.product.quantity_in_stock, 3)
        self.assertEqual(order.status, 'confirmed')
        self.assertTrue(order.transaction_hash)


class BlockchainIntegrityTests(TestCase):
    """Covers the core dissertation trust claim: tamper-evidence via hash-chaining."""

    def test_verify_chain_passes_on_untampered_entries(self):
        from blockchain.services import create_ledger_entry
        create_ledger_entry(
            record_type='payment_confirmation', record_reference='TEST-001',
            payload_snapshot={'amount': '100.00'},
        )
        create_ledger_entry(
            record_type='payment_confirmation', record_reference='TEST-002',
            payload_snapshot={'amount': '50.00'},
        )
        result = verify_chain()
        self.assertTrue(result['is_valid'])
        self.assertEqual(len(result['broken_entries']), 0)

    def test_verify_chain_detects_tampering(self):
        """
        THE core tamper-detection demonstration, automated. Directly
        modifies a LedgerEntry's payload after creation (bypassing the
        service layer, simulating an attacker/DB-level edit) and
        confirms verify_chain() correctly flags it as broken.
        """
        from blockchain.services import create_ledger_entry
        entry = create_ledger_entry(
            record_type='payment_confirmation', record_reference='TEST-003',
            payload_snapshot={'amount': '100.00'},
        )

        # Simulate tampering: directly edit the payload without going
        # through create_ledger_entry() (which is the only supported path)
        entry.payload_snapshot = {'amount': '999999.00'}
        entry.save()

        result = verify_chain()
        self.assertFalse(result['is_valid'])
        self.assertTrue(len(result['broken_entries']) > 0)