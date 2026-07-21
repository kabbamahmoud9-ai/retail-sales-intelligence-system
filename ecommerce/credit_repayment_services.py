"""
ecommerce/credit_repayment_services.py

Customer-facing online credit repayment. Isolated in its own module —
same "new concern, new file" pattern as customer_insights/capture.py —
so this never touches ecommerce/services.py, ecommerce/models.py, or
any part of the existing checkout/order flow.

Mirrors OnlineOrder.simulate_payment()'s architecture: a payment is
simulated first (stand-in for a real gateway), and ONLY on simulated
success does any real state change happen — CreditRepayment row,
credit_balance, blockchain ledger entry. Reuses the exact CreditRepayment
model and blockchain.services.create_ledger_entry() already built for
staff-side repayment — credit_balance remains the single source of
truth, never duplicated.

Staff-side repayment (staff_views.record_credit_repayment) intentionally
does NOT go through this module — a staff member directly attests a
manual/cash payment was received, with no payment step to simulate.
This module is specifically for the online/simulated-payment path.
"""
import uuid
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone

from .models import OnlineCustomer, CreditRepayment
from blockchain.services import create_ledger_entry


# Cash on delivery / credit itself don't make sense as repayment methods —
# repaying credit WITH credit is nonsensical, and there's no delivery leg
# for a repayment. Kept as its own list rather than reusing
# OnlineOrder.PAYMENT_CHOICES wholesale, since the valid set genuinely differs.
PAYMENT_METHOD_CHOICES_FOR_REPAYMENT = [
    ('orange_money', 'Orange Money'),
    ('afrimoney', 'Afrimoney'),
]


def simulate_repayment_payment(payment_method, amount):
    """
    Stand-in for a real payment gateway, mirroring
    OnlineOrder.simulate_payment()'s reference-generation style. Returns
    (success: bool, reference: str). Independent of OnlineOrder since a
    repayment has no associated order/cart — swapping in a real gateway
    later only requires changing this one function (isolated swap point,
    same discipline used throughout this project).
    """
    valid_methods = [m[0] for m in PAYMENT_METHOD_CHOICES_FOR_REPAYMENT]
    if payment_method not in valid_methods:
        return False, "Unsupported payment method for repayment."

    if payment_method == 'orange_money':
        return True, f"OM-REPAY-{uuid.uuid4().hex[:10].upper()}"
    elif payment_method == 'afrimoney':
        return True, f"AFM-REPAY-{uuid.uuid4().hex[:10].upper()}"

    return False, "Unknown payment method."


def process_credit_repayment(customer_id, payment_method, amount):
    """
    Single entry point for BOTH customer-facing repayment paths
    (standalone 'Repay Credit' page and optional checkout-time
    repayment). Wrapped in transaction.atomic() + select_for_update()
    so concurrent/duplicate submissions cannot double-deduct — balance
    is re-read and re-validated against its CURRENT value at write
    time, not a value read earlier in the request. Overpayment beyond
    the outstanding balance is rejected outright, since no business
    rule in this system currently supports it.

    Returns (success: bool, message: str, repayment: CreditRepayment|None).
    """
    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return False, "Invalid repayment amount.", None

    if amount <= 0:
        return False, "Repayment amount must be greater than zero.", None

    with transaction.atomic():
        customer = OnlineCustomer.objects.select_for_update().get(id=customer_id)

        if amount > customer.credit_balance:
            return False, (
                f"Repayment amount (Le {amount:,.2f}) exceeds your outstanding "
                f"balance (Le {customer.credit_balance:,.2f})."
            ), None

        success, payment_reference = simulate_repayment_payment(payment_method, amount)
        if not success:
            return False, f"Payment failed: {payment_reference}", None

        balance_before = customer.credit_balance
        balance_after = balance_before - amount

        customer.credit_balance = balance_after
        customer.save(update_fields=['credit_balance'])

        repayment = CreditRepayment.objects.create(
            customer=customer,
            amount=amount,
            recorded_by=None,  # None = customer self-service, distinguishes from staff-recorded repayments
            balance_before=balance_before,
            balance_after=balance_after,
        )

        ledger_entry = create_ledger_entry(
            record_type='credit_repayment',
            record_reference=f"CREDIT-{customer.id}-{repayment.id}",
            payload_snapshot={
                'customer_id': customer.id,
                'customer_name': customer.full_name,
                'amount': str(amount),
                'balance_before': str(balance_before),
                'balance_after': str(balance_after),
                'payment_method': payment_method,
                'payment_reference': payment_reference,
                'channel': 'customer_online',
                'recorded_at': timezone.now().isoformat(),
            },
        )
        repayment.transaction_hash = ledger_entry.current_hash
        repayment.save(update_fields=['transaction_hash'])

    return True, (
        f"Repayment of Le {amount:,.2f} successful. "
        f"New outstanding balance: Le {balance_after:,.2f}."
    ), repayment