"""
blockchain/models.py

LedgerEntry: an append-only, hash-chained audit record for
business-critical events (Step 14a: online order confirmation,
payment confirmation).

This is a locally simulated hash-chain — not a public blockchain —
chosen deliberately for dissertation reproducibility (no wallet, gas,
or external network dependency). Each entry's current_hash is derived
from its own payload plus the previous entry's hash, so any after-the-
fact edit, deletion, or reordering breaks the chain and is detectable
via blockchain.services.verify_chain().

Deliberately decoupled from ecommerce/other business apps: no foreign
keys to OnlineOrder or any other business model. Linkage back to the
source record is via record_type + record_reference (a human-readable
string) only, so this app never depends on the models of the apps that
use it.

Other apps must never construct LedgerEntry directly — always go
through blockchain.services.create_ledger_entry(), which computes
sequence_number/previous_hash/current_hash consistently.
"""

from django.db import models
from django.utils import timezone


class LedgerEntry(models.Model):

    RECORD_TYPE_CHOICES = [
        ('online_order_confirmation', 'Online Order Confirmation'),
        ('payment_confirmation', 'Payment Confirmation'),
        ('credit_repayment', 'Credit Repayment'),
        # Future record types (inventory movements, delivery completion,
        # credit approvals, supplier transactions, etc.) can be appended
        # here without changing the model, hashing, or verification logic.
    ]

    sequence_number = models.PositiveIntegerField(
        unique=True,
        editable=False,
        help_text="Defines chain order. Assigned automatically in services.create_ledger_entry()."
    )
    record_type = models.CharField(max_length=50, choices=RECORD_TYPE_CHOICES)
    record_reference = models.CharField(
        max_length=100,
        help_text="Human-readable reference to the source record, e.g. an OnlineOrder.order_reference"
    )
    payload_snapshot = models.JSONField(
        help_text="JSON snapshot of the critical fields being verified at the time of the event"
    )
    previous_hash = models.CharField(max_length=64)
    current_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['sequence_number']
        verbose_name = "Ledger Entry"
        verbose_name_plural = "Ledger Entries"

    def __str__(self):
        return f"#{self.sequence_number} {self.get_record_type_display()} — {self.record_reference}"