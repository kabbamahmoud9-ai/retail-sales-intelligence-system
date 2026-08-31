"""
blockchain/views.py

Staff-facing verification view. Thin — only calls
blockchain.services.verify_chain() and renders the result.
No business logic beyond formatting lives here.
"""

from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import owner_required
from .services import verify_chain


@owner_required
def verify_ledger(request):
    result = verify_chain()

    context = {
        'is_valid': result['is_valid'],
        'total_entries': result['total_entries'],
        'broken_entries': result['broken_entries'],
        'verified_at': timezone.now(),
    }
    return render(request, 'blockchain/verify_ledger.html', context)
