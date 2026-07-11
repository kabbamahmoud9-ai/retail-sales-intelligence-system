"""
customer_insights/capture.py

Thin write-only seam for logging CustomerEvent rows from existing
ecommerce views. Contains zero business logic — just creates append-only
event records. Intelligence (segmentation, ML) lives in services.py /
ml_services.py and only ever reads these events, never writes them.
"""
from .models import CustomerEvent


def _get_session_key(request):
    """Ensure the session has a key, creating one if needed."""
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key


def log_product_view(request, customer, product):
    CustomerEvent.objects.create(
        customer=customer,
        session_key=_get_session_key(request),
        event_type='product_view',
        product=product,
    )


def log_category_view(request, customer, category):
    CustomerEvent.objects.create(
        customer=customer,
        session_key=_get_session_key(request),
        event_type='category_view',
        category=category,
    )


def log_search_query(request, customer, search_term):
    CustomerEvent.objects.create(
        customer=customer,
        session_key=_get_session_key(request),
        event_type='search_query',
        search_term=search_term,
    )