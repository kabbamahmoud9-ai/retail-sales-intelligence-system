"""
ai_commerce/views.py

Customer-facing views for the AI Shopping Assistant (3 modes) and the
Smart Credit & Loyalty Assistant.

Reuses ecommerce's session-based customer auth (get_current_customer,
customer_login_required) and cart helpers (get_cart, save_cart,
get_cart_count) directly rather than duplicating them — the cart stays
a single source of truth, same structure as ecommerce.views.add_to_cart.
"""

from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages

from ecommerce.views import (
    get_current_customer, customer_login_required,
    get_cart, save_cart, get_cart_count,
)

from .models import ShoppingSession, ShoppingRecommendation
from .services import (
    parse_natural_language_query,
    generate_shopping_recommendations,
    calculate_credit_recommendation,
    get_reorder_suggestions,
)


def _base_context(request, customer):
    cart = get_cart(request)
    return {
        'customer': customer,
        'cart_count': get_cart_count(cart),
    }


def _parse_decimal(value):
    try:
        return Decimal(value) if value else None
    except InvalidOperation:
        return None


def _parse_int(value):
    try:
        return int(value) if value else None
    except (ValueError, TypeError):
        return None


@customer_login_required
def assistant_home(request):
    customer = get_current_customer(request)
    return render(request, 'ai_commerce/assistant_home.html', _base_context(request, customer))


@customer_login_required
def natural_language_search(request):
    customer = get_current_customer(request)
    context = _base_context(request, customer)

    if request.method == 'POST':
        raw_query = request.POST.get('raw_query', '').strip()
        budget = _parse_decimal(request.POST.get('budget', '').strip())

        if not raw_query:
            messages.error(request, "Please describe what you're shopping for.")
            context['raw_query'] = raw_query
            return render(request, 'ai_commerce/natural_language_form.html', context)

        session = ShoppingSession.objects.create(
            customer=customer,
            mode='natural_language',
            raw_query=raw_query,
            budget=budget,
        )
        session.parsed_intent = parse_natural_language_query(raw_query)
        session.save()

        recommendations = generate_shopping_recommendations(session)

        context.update({'session': session, 'recommendations': recommendations})
        return render(request, 'ai_commerce/recommendations_results.html', context)

    return render(request, 'ai_commerce/natural_language_form.html', context)


@customer_login_required
def guided_planner(request):
    customer = get_current_customer(request)
    context = _base_context(request, customer)

    if request.method == 'POST':
        budget = _parse_decimal(request.POST.get('budget', '').strip())
        family_size = _parse_int(request.POST.get('family_size', '').strip())
        shopping_purpose = request.POST.get('shopping_purpose', '').strip()
        quality_preference = request.POST.get('quality_preference', 'standard')

        session = ShoppingSession.objects.create(
            customer=customer,
            mode='guided_planner',
            budget=budget,
            family_size=family_size,
            shopping_purpose=shopping_purpose,
            quality_preference=quality_preference,
        )

        recommendations = generate_shopping_recommendations(session)

        context.update({'session': session, 'recommendations': recommendations})
        return render(request, 'ai_commerce/recommendations_results.html', context)

    return render(request, 'ai_commerce/guided_planner_form.html', context)


@customer_login_required
def shop_by_goal(request):
    customer = get_current_customer(request)
    context = _base_context(request, customer)
    context['goal_choices'] = ShoppingSession.GOAL_CHOICES

    if request.method == 'POST':
        goal = request.POST.get('goal', '')
        valid_goals = [g[0] for g in ShoppingSession.GOAL_CHOICES]

        if goal not in valid_goals:
            messages.error(request, "Please select a valid goal.")
            return render(request, 'ai_commerce/goal_selector.html', context)

        session = ShoppingSession.objects.create(
            customer=customer,
            mode='shop_by_goal',
            goal=goal,
        )

        recommendations = generate_shopping_recommendations(session)

        context.update({'session': session, 'recommendations': recommendations})
        return render(request, 'ai_commerce/recommendations_results.html', context)

    return render(request, 'ai_commerce/goal_selector.html', context)


@customer_login_required
def add_all_to_cart_view(request, session_id):
    """
    Bulk-adds every recommendation in a session to the cart, respecting
    any per-item quantity submitted from recommendations_results.html.
    Writes directly into the same session cart dict structure used by
    ecommerce.views.add_to_cart, so the cart stays a single source of truth.
    """
    if request.method != 'POST':
        return redirect('ai_commerce:home')

    customer = get_current_customer(request)
    session = get_object_or_404(ShoppingSession, id=session_id, customer=customer)
    cart = get_cart(request)

    added_count = 0
    for rec in session.recommendations.select_related('product'):
        product = rec.product
        qty = _parse_int(request.POST.get(f'quantity_{product.id}', '1')) or 0

        if qty <= 0:
            continue

        key = str(product.id)
        if key in cart:
            new_qty = min(cart[key]['quantity'] + qty, product.quantity_in_stock)
            cart[key]['quantity'] = new_qty
        else:
            cart[key] = {
                'name': product.product_name,
                'price': str(product.online_price),
                'quantity': min(qty, product.quantity_in_stock),
                'image': product.product_image.url if product.product_image else '',
            }
        rec.added_to_cart = True
        rec.save(update_fields=['added_to_cart'])
        added_count += 1

    save_cart(request, cart)

    if added_count:
        messages.success(request, f"Added {added_count} item(s) to your cart.")
    else:
        messages.info(request, "No items were added — set a quantity of 1 or more.")

    return redirect('ecommerce:cart')


@customer_login_required
def recommendation_feedback(request, rec_id):
    """Captures a simple thumbs up/down on a single recommendation."""
    if request.method != 'POST':
        return redirect('ai_commerce:home')

    customer = get_current_customer(request)
    rec = get_object_or_404(
        ShoppingRecommendation, id=rec_id, session__customer=customer
    )
    rec.was_helpful = request.POST.get('helpful') == 'yes'
    rec.save(update_fields=['was_helpful'])

    messages.success(request, "Thanks for the feedback!")
    referer = request.META.get('HTTP_REFERER')
    return redirect(referer) if referer else redirect('ai_commerce:home')


@customer_login_required
def credit_loyalty_assistant(request):
    customer = get_current_customer(request)
    context = _base_context(request, customer)

    assessment = calculate_credit_recommendation(customer)
    reorder_suggestions = get_reorder_suggestions(customer)

    context.update({
        'assessment': assessment,
        'reorder_suggestions': reorder_suggestions,
    })
    return render(request, 'ai_commerce/credit_loyalty.html', context)