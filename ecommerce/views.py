"""
ecommerce/views.py

All views for the customer-facing online store.

Auth strategy:
  - Customer session stored in request.session['online_customer_id']
  - Separate from Django's staff auth (request.user)
  - customer_login_required decorator protects checkout + order views

Cart strategy:
  - Stored entirely in Django session as a dict:
    { product_id (str): { 'quantity': int, 'name': str, 'price': str } }
  - No database writes until checkout — fast and works without login
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from products.models import Product, Category
from delivery.models import DeliveryZone
from .models import OnlineCustomer, OnlineOrder, OnlineOrderItem


# ---------------------------------------------------------------------------
# Helper — customer session auth
# ---------------------------------------------------------------------------

def get_current_customer(request):
    """Return the logged-in OnlineCustomer or None."""
    customer_id = request.session.get('online_customer_id')
    if customer_id:
        try:
            return OnlineCustomer.objects.get(id=customer_id, is_active=True)
        except OnlineCustomer.DoesNotExist:
            # Stale session — clear it
            del request.session['online_customer_id']
    return None


def customer_login_required(view_func):
    """
    Decorator for views that need a logged-in OnlineCustomer.
    Redirects to store login (not staff login) if not authenticated.
    """
    def wrapper(request, *args, **kwargs):
        if not get_current_customer(request):
            messages.warning(request, "Please log in to continue.")
            return redirect('ecommerce:login')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ---------------------------------------------------------------------------
# Cart helpers — cart lives in session, not database
# ---------------------------------------------------------------------------

def get_cart(request):
    """Return the cart dict from session, initialising if missing."""
    return request.session.get('cart', {})


def save_cart(request, cart):
    """Persist the cart dict back to session."""
    request.session['cart'] = cart
    request.session.modified = True


def get_cart_total(cart):
    """Sum all line totals in the cart dict."""
    return sum(
        float(item['price']) * item['quantity']
        for item in cart.values()
    )


def get_cart_count(cart):
    """Total number of individual items across all lines."""
    return sum(item['quantity'] for item in cart.values())


# ---------------------------------------------------------------------------
# Customer auth views
# ---------------------------------------------------------------------------

def customer_register(request):
    """Register a new OnlineCustomer account."""
    # Already logged in? Send to store
    if get_current_customer(request):
        return redirect('ecommerce:store_home')

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        email     = request.POST.get('email', '').strip().lower()
        phone     = request.POST.get('phone', '').strip()
        address   = request.POST.get('address', '').strip()
        password  = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')

        # Basic validation
        if not all([full_name, email, password]):
            messages.error(request, "Full name, email, and password are required.")
            return render(request, 'ecommerce/register.html')

        if password != password2:
            messages.error(request, "Passwords do not match.")
            return render(request, 'ecommerce/register.html')

        if len(password) < 6:
            messages.error(request, "Password must be at least 6 characters.")
            return render(request, 'ecommerce/register.html')

        if OnlineCustomer.objects.filter(email=email).exists():
            messages.error(request, "An account with this email already exists.")
            return render(request, 'ecommerce/register.html')

        # Create customer
        customer = OnlineCustomer(
            full_name=full_name,
            email=email,
            phone=phone,
            address=address,
        )
        customer.set_password(password)
        customer.save()

        # Auto-login after registration
        request.session['online_customer_id'] = customer.id
        messages.success(request, f"Welcome, {customer.full_name}! Your account has been created.")
        return redirect('ecommerce:store_home')

    return render(request, 'ecommerce/register.html')


def customer_login(request):
    """Log in an existing OnlineCustomer."""
    if get_current_customer(request):
        return redirect('ecommerce:store_home')

    if request.method == 'POST':
        email    = request.POST.get('email', '').strip().lower()
        password = request.POST.get('password', '')

        try:
            customer = OnlineCustomer.objects.get(email=email, is_active=True)
        except OnlineCustomer.DoesNotExist:
            messages.error(request, "Invalid email or password.")
            return render(request, 'ecommerce/login.html')

        if customer.check_password(password):
            request.session['online_customer_id'] = customer.id
            messages.success(request, f"Welcome back, {customer.full_name}!")
            # Respect ?next= param so post-login redirect works
            next_url = request.GET.get('next', 'ecommerce:store_home')
            return redirect(next_url)
        else:
            messages.error(request, "Invalid email or password.")

    return render(request, 'ecommerce/login.html')


def customer_logout(request):
    """Log out the current OnlineCustomer (keeps cart intact)."""
    if 'online_customer_id' in request.session:
        del request.session['online_customer_id']
    messages.success(request, "You have been logged out.")
    return redirect('ecommerce:store_home')


# ---------------------------------------------------------------------------
# Store front
# ---------------------------------------------------------------------------

def store_home(request):
    """
    Product catalogue. Supports search by name and filter by category.
    Only shows products marked is_available_online=True with stock > 0.
    """
    customer   = get_current_customer(request)
    cart       = get_cart(request)
    cart_count = get_cart_count(cart)

    products   = Product.objects.filter(
        is_available_online=True,
        quantity_in_stock__gt=0
    ).select_related('category')

    categories = Category.objects.all()

    # Search
    query = request.GET.get('q', '').strip()
    if query:
        products = products.filter(product_name__icontains=query)

    # Category filter
    cat_id = request.GET.get('category', '')
    if cat_id:
        products = products.filter(category_id=cat_id)

    context = {
        'products':    products,
        'categories':  categories,
        'customer':    customer,
        'cart_count':  cart_count,
        'query':       query,
        'selected_cat': cat_id,
    }
    return render(request, 'ecommerce/store_home.html', context)


def product_detail(request, product_id):
    """Single product page with Add to Cart button."""
    customer  = get_current_customer(request)
    cart      = get_cart(request)
    cart_count = get_cart_count(cart)

    product = get_object_or_404(
        Product,
        id=product_id,
        is_available_online=True
    )

    context = {
        'product':    product,
        'customer':   customer,
        'cart_count': cart_count,
    }
    return render(request, 'ecommerce/product_detail.html', context)


# ---------------------------------------------------------------------------
# Cart views
# ---------------------------------------------------------------------------

def add_to_cart(request, product_id):
    """Add a product to the session cart. POST only."""
    if request.method != 'POST':
        return redirect('ecommerce:store_home')

    product = get_object_or_404(Product, id=product_id, is_available_online=True)
    cart    = get_cart(request)

    try:
        qty = int(request.POST.get('quantity', 1))
        if qty < 1:
            qty = 1
    except (ValueError, TypeError):
        qty = 1

    key = str(product_id)

    if key in cart:
        # Already in cart — increment quantity
        new_qty = cart[key]['quantity'] + qty
        # Don't exceed available stock
        new_qty = min(new_qty, product.quantity_in_stock)
        cart[key]['quantity'] = new_qty
    else:
        cart[key] = {
            'name':     product.product_name,
            'price':    str(product.online_price),
            'quantity': min(qty, product.quantity_in_stock),
            'image':    product.product_image.url if product.product_image else '',
        }

    save_cart(request, cart)
    messages.success(request, f"'{product.product_name}' added to your cart.")
    return redirect('ecommerce:cart')


def cart_view(request):
    """Display the current cart with line totals and grand total."""
    customer   = get_current_customer(request)
    cart       = get_cart(request)
    cart_count = get_cart_count(cart)

    # Build a list of enriched cart lines for the template
    cart_lines = []
    for pid, item in cart.items():
        subtotal = float(item['price']) * item['quantity']
        cart_lines.append({
            'product_id': int(pid),
            'name':       item['name'],
            'price':      float(item['price']),
            'quantity':   item['quantity'],
            'image':      item.get('image', ''),
            'subtotal':   subtotal,
        })

    grand_total = get_cart_total(cart)

    context = {
        'cart_lines':  cart_lines,
        'grand_total': grand_total,
        'customer':    customer,
        'cart_count':  cart_count,
    }
    return render(request, 'ecommerce/cart.html', context)


def update_cart(request, product_id):
    """Update quantity for a cart line. POST only."""
    if request.method != 'POST':
        return redirect('ecommerce:cart')

    cart = get_cart(request)
    key  = str(product_id)

    if key in cart:
        try:
            qty = int(request.POST.get('quantity', 1))
        except (ValueError, TypeError):
            qty = 1

        if qty < 1:
            # Treat qty=0 as remove
            del cart[key]
            messages.info(request, "Item removed from cart.")
        else:
            product = get_object_or_404(Product, id=product_id)
            cart[key]['quantity'] = min(qty, product.quantity_in_stock)
            messages.success(request, "Cart updated.")

    save_cart(request, cart)
    return redirect('ecommerce:cart')


def remove_from_cart(request, product_id):
    """Remove a single line from the cart."""
    cart = get_cart(request)
    key  = str(product_id)

    if key in cart:
        removed_name = cart[key]['name']
        del cart[key]
        save_cart(request, cart)
        messages.success(request, f"'{removed_name}' removed from cart.")

    return redirect('ecommerce:cart')


# ---------------------------------------------------------------------------
# Checkout & order flow
# ---------------------------------------------------------------------------

@customer_login_required
def checkout(request):
    """
    Show checkout form. On POST, create the OnlineOrder + OnlineOrderItems,
    then redirect to payment simulation.
    Order is created with status='pending' — not confirmed yet.
    """
    customer   = get_current_customer(request)
    cart       = get_cart(request)
    cart_count = get_cart_count(cart)
    zones      = DeliveryZone.objects.filter(is_active=True)

    if not cart:
        messages.warning(request, "Your cart is empty.")
        return redirect('ecommerce:store_home')

    # Build cart lines with live stock check
    cart_lines  = []
    grand_total = 0
    stock_error = False

    for pid, item in cart.items():
        try:
            product  = Product.objects.get(id=int(pid), is_available_online=True)
        except Product.DoesNotExist:
            continue

        if product.quantity_in_stock < item['quantity']:
            messages.error(
                request,
                f"'{product.product_name}' only has {product.quantity_in_stock} units available. "
                f"Please update your cart."
            )
            stock_error = True
            continue

        subtotal     = float(item['price']) * item['quantity']
        grand_total += subtotal
        cart_lines.append({
            'product':  product,
            'quantity': item['quantity'],
            'price':    float(item['price']),
            'subtotal': subtotal,
        })

    if stock_error:
        return redirect('ecommerce:cart')

    if request.method == 'POST':
        delivery_address = request.POST.get('delivery_address', '').strip()
        payment_method   = request.POST.get('payment_method', '')
        zone_id          = request.POST.get('delivery_zone', '')

        # Re-usable context builder so every early-return below stays
        # consistent with what the template needs.
        def error_context():
            return {
                'cart_lines': cart_lines, 'grand_total': grand_total,
                'customer': customer, 'cart_count': cart_count,
                'zones': zones, 'payment_choices': OnlineOrder.PAYMENT_CHOICES,
            }

        if not delivery_address:
            messages.error(request, "Please enter a delivery address.")
            return render(request, 'ecommerce/checkout.html', error_context())

        valid_methods = [m[0] for m in OnlineOrder.PAYMENT_CHOICES]
        if payment_method not in valid_methods:
            messages.error(request, "Please select a valid payment method.")
            return render(request, 'ecommerce/checkout.html', error_context())

        # Delivery zone is required — this is the Step 11 checkout change
        try:
            zone = zones.get(id=int(zone_id))
        except (ValueError, TypeError, DeliveryZone.DoesNotExist):
            messages.error(request, "Please select a valid delivery zone.")
            return render(request, 'ecommerce/checkout.html', error_context())

        delivery_fee = zone.calculate_fee()
        order_total  = grand_total + float(delivery_fee)

        # Credit check upfront — now includes the delivery fee, since the
        # customer's outstanding balance should reflect the full amount owed.
        if payment_method == 'credit':
            if not customer.can_afford_credit(order_total):
                messages.error(
                    request,
                    f"Insufficient credit. Your available credit is "
                    f"Le {customer.available_credit:,.2f} but your order total "
                    f"(including delivery) is Le {order_total:,.2f}."
                )
                return render(request, 'ecommerce/checkout.html', error_context())

        # Create the pending order
        order = OnlineOrder.objects.create(
            customer=customer,
            delivery_address=delivery_address,
            payment_method=payment_method,
            total_amount=order_total,
            delivery_zone=zone,
            delivery_fee=delivery_fee,
            delivery_distance_km=zone.average_distance_km,
            status='pending',
        )

        # Create order items (snapshot prices)
        for line in cart_lines:
            OnlineOrderItem.objects.create(
                order=order,
                product=line['product'],
                quantity=line['quantity'],
                unit_price=line['price'],
            )

        return redirect('ecommerce:payment', order_id=order.id)

    context = {
        'cart_lines':  cart_lines,
        'grand_total': grand_total,
        'customer':    customer,
        'cart_count':  cart_count,
        'zones':       zones,
        'payment_choices': OnlineOrder.PAYMENT_CHOICES,
    }
    return render(request, 'ecommerce/checkout.html', context)


@customer_login_required
def payment_simulation(request, order_id):
    """
    Simulated payment page. Shows order summary and a 'Pay Now' button.
    On POST, calls order.simulate_payment() then order.confirm_order().
    """
    customer = get_current_customer(request)
    order    = get_object_or_404(OnlineOrder, id=order_id, customer=customer, status='pending')
    cart_count = get_cart_count(get_cart(request))

    if request.method == 'POST':
        # Simulate payment
        success, reference = order.simulate_payment()

        if not success:
            messages.error(request, f"Payment failed: {reference}")
            return redirect('ecommerce:payment', order_id=order.id)

        # Confirm payment + record it on the audit ledger (Step 14a)
        order.record_payment_confirmation(reference)

        # Confirm order — creates Sale, deducts stock, atomic
        try:
            with transaction.atomic():
                order.confirm_order()

            # Clear the cart on success
            request.session['cart'] = {}
            request.session.modified = True

            messages.success(request, "Order confirmed! Payment successful.")
            return redirect('ecommerce:confirm_order', order_id=order.id)

        except ValueError as e:
            # Stock validation failure from confirm_order()
            messages.error(request, str(e))
            return redirect('ecommerce:cart')

    context = {
        'order':      order,
        'customer':   customer,
        'cart_count': cart_count,
        'items':      order.items.select_related('product'),
    }
    return render(request, 'ecommerce/payment.html', context)


@customer_login_required
def confirm_order(request, order_id):
    """Order success / thank you page."""
    customer = get_current_customer(request)
    order    = get_object_or_404(OnlineOrder, id=order_id, customer=customer)
    cart_count = get_cart_count(get_cart(request))

    context = {
        'order':      order,
        'customer':   customer,
        'cart_count': cart_count,
        'items':      order.items.select_related('product'),
    }
    return render(request, 'ecommerce/order_confirm.html', context)


@customer_login_required
def order_history(request):
    """List all orders for the logged-in customer."""
    customer   = get_current_customer(request)
    orders     = OnlineOrder.objects.filter(customer=customer).order_by('-order_date')
    cart_count = get_cart_count(get_cart(request))

    context = {
        'orders':     orders,
        'customer':   customer,
        'cart_count': cart_count,
    }
    return render(request, 'ecommerce/order_history.html', context)


@customer_login_required
def order_detail(request, order_id):
    """Detail view for a single customer order."""
    customer   = get_current_customer(request)
    order      = get_object_or_404(OnlineOrder, id=order_id, customer=customer)
    cart_count = get_cart_count(get_cart(request))

    context = {
        'order':      order,
        'customer':   customer,
        'cart_count': cart_count,
        'items':      order.items.select_related('product'),
    }
    return render(request, 'ecommerce/order_detail.html', context)