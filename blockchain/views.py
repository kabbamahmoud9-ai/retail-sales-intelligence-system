"""
blockchain/views.py

Staff-facing verification view. Thin — only calls
blockchain.services.verify_chain() and renders the result.
No business logic beyond formatting lives here.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils import timezone

from .services import verify_chain


@login_required
def verify_ledger(request):
    """
    Runs chain verification every time this page loads. This single
    behavior covers both requirements: automatic verification on load,
    and the "Run Verification Again" button — which is just a link back
    to this same view, so clicking it re-runs the check naturally.
    """
    result = verify_chain()

    context = {
        'is_valid': result['is_valid'],
        'total_entries': result['total_entries'],
        'broken_entries': result['broken_entries'],
        'verified_at': timezone.now(),
    }
    return render(request, 'blockchain/verify_ledger.html', context)