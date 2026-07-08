"""
blockchain/services.py

Service-oriented interface for the audit ledger. Other apps should only
ever call create_ledger_entry() to record an event, and verify_chain()
to check integrity — never construct or hash LedgerEntry rows themselves.
All hashing and chain-validation logic lives here, in one place.
"""

import hashlib
import json

from .models import LedgerEntry

# Fixed previous_hash value for the very first entry in the chain.
GENESIS_HASH = "0" * 64


def _compute_hash(sequence_number, payload_snapshot, previous_hash):
    """
    SHA-256 hash of sequence_number + payload_snapshot + previous_hash.

    payload_snapshot is serialized with sort_keys=True so the hash is
    deterministic regardless of dict insertion order.
    """
    payload_str = json.dumps(payload_snapshot, sort_keys=True, default=str)
    raw = f"{sequence_number}|{payload_str}|{previous_hash}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def create_ledger_entry(record_type, record_reference, payload_snapshot):
    """
    Create and return a new, correctly-chained LedgerEntry.

    This is the ONLY supported way to create a LedgerEntry. Callers
    (OnlineOrder.confirm_order(), OnlineOrder.record_payment_confirmation(),
    and any future business-event hook) pass in what happened; this
    function handles sequence_number, previous_hash, and current_hash.

    Args:
        record_type: one of LedgerEntry.RECORD_TYPE_CHOICES values
        record_reference: human-readable reference to the source record
        payload_snapshot: JSON-serializable dict of critical fields to snapshot

    Returns:
        The newly created LedgerEntry.
    """
    last_entry = LedgerEntry.objects.order_by('-sequence_number').first()

    if last_entry:
        sequence_number = last_entry.sequence_number + 1
        previous_hash = last_entry.current_hash
    else:
        sequence_number = 1
        previous_hash = GENESIS_HASH

    current_hash = _compute_hash(sequence_number, payload_snapshot, previous_hash)

    return LedgerEntry.objects.create(
        sequence_number=sequence_number,
        record_type=record_type,
        record_reference=record_reference,
        payload_snapshot=payload_snapshot,
        previous_hash=previous_hash,
        current_hash=current_hash,
    )


def verify_chain():
    """
    Walk the entire ledger in sequence order, recomputing each hash and
    checking chain linkage. Detects both tampered payloads (hash mismatch)
    and deleted/reordered entries (broken previous_hash link).

    Returns:
        {
            'is_valid': bool,
            'total_entries': int,
            'broken_entries': [
                {'sequence_number': int, 'entry_id': int, 'reason': str},
                ...
            ],
        }
        reason is either 'hash_mismatch' or 'broken_link'.
    """
    entries = list(LedgerEntry.objects.order_by('sequence_number'))
    broken_entries = []
    expected_previous_hash = GENESIS_HASH

    for entry in entries:
        recomputed_hash = _compute_hash(
            entry.sequence_number, entry.payload_snapshot, entry.previous_hash
        )

        if entry.previous_hash != expected_previous_hash:
            broken_entries.append({
                'sequence_number': entry.sequence_number,
                'entry_id': entry.id,
                'reason': 'broken_link',
            })
        elif recomputed_hash != entry.current_hash:
            broken_entries.append({
                'sequence_number': entry.sequence_number,
                'entry_id': entry.id,
                'reason': 'hash_mismatch',
            })

        expected_previous_hash = entry.current_hash

    return {
        'is_valid': len(broken_entries) == 0,
        'total_entries': len(entries),
        'broken_entries': broken_entries,
    }