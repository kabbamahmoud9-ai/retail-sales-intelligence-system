from django.shortcuts import render
from ecommerce.views import get_current_customer, get_cart, get_cart_count
from .services import find_similar_products, MODEL_VERSION
from .models import VisualSearchQuery


def visual_search_results(request):
    """
    GET: shows the upload form (no results yet).
    POST: runs the CLIP similarity search against the uploaded image,
    logs a VisualSearchQuery, and renders the matched products.
    """
    customer   = get_current_customer(request)
    cart_count = get_cart_count(get_cart(request))

    if request.method == 'POST' and request.FILES.get('query_image'):
        uploaded_image = request.FILES['query_image']

        matches = find_similar_products(uploaded_image, top_n=10)

        matched_products_snapshot = [
            {'product_id': m['product'].pk, 'similarity_score': round(m['similarity_score'], 4)}
            for m in matches
        ]
        top_confidence = matched_products_snapshot[0]['similarity_score'] if matched_products_snapshot else None

        query_log = VisualSearchQuery.objects.create(
            customer=customer,
            query_image=uploaded_image,
            matched_products=matched_products_snapshot,
            top_match_confidence=top_confidence,
            model_version=MODEL_VERSION,
        )

        context = {
            'matches':    matches,
            'query_log':  query_log,
            'has_results': True,
            'customer':   customer,
            'cart_count': cart_count,
        }
        return render(request, 'visual_search/results.html', context)

    context = {
        'has_results': False,
        'customer':    customer,
        'cart_count':  cart_count,
    }
    return render(request, 'visual_search/results.html', context)