# store/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse, HttpResponseBadRequest
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db.models import Q
from collections import Counter
from django.contrib import messages

from .models import Product, Category, CartItem
from django.conf import settings
from wholesale.models import WholesaleProduct, WholesaleCartItem, WholesaleOrder
from orders.models import OrderItem, OrderFeedback, Order
from django.urls import reverse
from .forms import ProductForm
from .utils import get_or_create_cart

def landing_page(request):
    """
    Renders the main landing page (f1.png, f2.png).
    """
    if request.user.is_authenticated:
        # If user is already logged in, send them to their dashboard
        return redirect("dashboard_redirect")
    return render(request, "landing_page.html")


@login_required
def retailer_dashboard(request):
    """
    Displays the Retailer's "My Products" page (f5.png, f8.png).
    Handles adding, editing, and deleting products.
    """
    if not request.user.is_retailer:
        return HttpResponseForbidden("You are not authorized to view this page.")

    # Get all products for the *current* logged-in retailer
    products = Product.objects.filter(retailer=request.user)
    categories = Category.objects.all()
    wholesale_products = WholesaleProduct.objects.filter(is_available=True, stock_quantity__gt=0).select_related("category", "wholesaler")

    # Section-specific searches
    search_my = (request.GET.get("q_my") or "").strip()
    search_wholesale = (request.GET.get("q_wholesale") or "").strip()
    if search_my:
        products = products.filter(Q(name__icontains=search_my))
    if search_wholesale:
        wholesale_products = wholesale_products.filter(Q(name__icontains=search_wholesale))

    # This view will also handle the POST request from the "Add New Product" modal
    if request.method == "POST":
        form_type = request.POST.get("form_type")

        if form_type == "add_product":
            form = ProductForm(request.POST)
            if form.is_valid():
                product = form.save(commit=False)
                product.retailer = request.user
                product.save()
                # We can add a success message here
                return redirect("store:retailer_dashboard")
            else:
                # Fall through and show form errors in context
                add_form = form

        elif form_type == "edit_product":
            product_id = request.POST.get("product_id")
            product = get_object_or_404(Product, id=product_id, retailer=request.user)
            form = ProductForm(request.POST, instance=product)
            if form.is_valid():
                form.save()
                return redirect("store:retailer_dashboard")
            else:
                # If edit fails, keep the add_form as a fresh one and include edit errors via JS/template
                add_form = ProductForm()
        else:
            add_form = ProductForm()
    else:
        add_form = ProductForm()

    # Pre-populate the forms for the modal
    # Map which wholesale products are already proxied by this retailer
    proxied_ids = set(Product.objects.filter(retailer=request.user, is_proxy=True, proxy_wholesale_product__isnull=False).values_list('proxy_wholesale_product_id', flat=True))

    context = {
        "products": products,
        "categories": categories,
        "wholesale_products": wholesale_products,
        "search_my": search_my,
        "search_wholesale": search_wholesale,
        "add_form": add_form,
        "proxied_ids": list(proxied_ids),
    }
    return render(request, "store/retailer_dashboard.html", context)


@login_required
def delete_product(request, product_id):
    """
    Handles the POST request to delete a product.
    """
    if not request.user.is_retailer:
        return HttpResponseForbidden()

    product = get_object_or_404(Product, id=product_id, retailer=request.user)
    if request.method == "POST":
        product.delete()
        return redirect("store:retailer_dashboard")

    # Should not be reached via GET
    return redirect("store:retailer_dashboard")


@login_required
def customer_product_list(request):
    """
    The main customer dashboard.
    A grid of all available products from all retailers.
    Includes the Pincode filter.
    """
    products = Product.objects.filter(is_available=True, stock_quantity__gt=0)

    pincode = request.GET.get("pincode")
    if pincode:
        products = products.filter(retailer__pincode=pincode)

    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        products = products.filter(
            Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )

    # Quantity filter
    min_qty_raw = (request.GET.get("quantity") or "").strip()
    min_qty = None
    try:
        if min_qty_raw:
            min_qty = int(min_qty_raw)
    except Exception:
        min_qty = None
    if min_qty is not None:
        products = products.filter(stock_quantity__gt=min_qty)

    # Base queryset for deriving filter categories (before category filters)
    base_qs = products

    # Category filter (selected from sidebar)
    selected_categories = []
    try:
        selected_categories = [int(cid) for cid in request.GET.getlist("category") if cid.isdigit()]
    except Exception:
        selected_categories = []
    if selected_categories:
        products = products.filter(category_id__in=selected_categories)

    # Sort filter
    sort = request.GET.get("sort")
    if sort == "price_asc":
        products = products.order_by("price")
    elif sort == "price_desc":
        products = products.order_by("-price")

    cart = get_or_create_cart(request)
    cart_items = list(cart.items.select_related("product", "product__category").all()) if getattr(cart, "pk", None) else []
    cart_product_ids = [i.product_id for i in cart_items if getattr(i, "product_id", None)]
    cart_category_ids = set([getattr(i.product, "category_id", None) for i in cart_items if getattr(i, "product", None)])

    past_items_qs = OrderItem.objects.filter(order__customer=request.user).select_related("product") if request.user.is_authenticated else OrderItem.objects.none()
    past_product_ids = [oi.product_id for oi in past_items_qs if getattr(oi, "product_id", None)]
    freq = Counter(past_product_ids)

    candidates = Product.objects.filter(is_available=True, stock_quantity__gt=0)
    if pincode:
        candidates = candidates.filter(retailer__pincode=pincode)
    if cart_category_ids or past_product_ids:
        candidates = candidates.filter(Q(id__in=past_product_ids) | Q(category_id__in=list(cart_category_ids)))
    if cart_product_ids:
        candidates = candidates.exclude(id__in=cart_product_ids)
    if min_qty is not None:
        candidates = candidates.filter(stock_quantity__gt=min_qty)
    candidates = list(candidates.select_related("category", "retailer"))

    def _score(p):
        return (
            int(freq.get(p.id, 0)),
            1 if p.category_id in cart_category_ids else 0,
            p.created_at,
        )

    candidates.sort(key=lambda p: _score(p), reverse=True)
    recommended_products = candidates[:8]

    prod_ids = list(products.values_list("id", flat=True))
    rec_ids = [p.id for p in recommended_products]
    all_ids = list(set(prod_ids + rec_ids))
    fb_map = {}
    if all_ids:
        for fb in OrderFeedback.objects.filter(product_id__in=all_ids).select_related("customer", "product"):
            fb_map.setdefault(fb.product_id, []).append(fb)
    products = list(products.select_related("category", "retailer"))
    for p in products:
        setattr(p, "feedbacks", fb_map.get(p.id, []))
    for p in recommended_products:
        setattr(p, "feedbacks", fb_map.get(p.id, []))

    # Available categories derived from current search results only
    category_ids = list(
        base_qs.values_list("category_id", flat=True).distinct()
    )
    available_categories = Category.objects.filter(id__in=category_ids)

    has_filters = bool(pincode or search_query or selected_categories or sort)

    from django.conf import settings as dj_settings
    from datetime import datetime, timedelta
    expected_days = getattr(dj_settings, "ORDER_ESTIMATED_DAYS", 5)
    expected_delivery = datetime.now() + timedelta(days=expected_days)

    context = {
        "products": products,
        "recommended_products": recommended_products,
        "search_pincode": pincode,
        "search_query": search_query,
        "available_categories": available_categories,
        "selected_categories": selected_categories,
        "sort": sort,
        "has_filters": has_filters,
        "expected_delivery": expected_delivery,
        "min_qty": min_qty,
    }
    return render(request, "store/customer_product_list.html", context)

@login_required
def alerts(request):
    from datetime import datetime
    from datetime import timezone as dt_tz
    now = datetime.now(dt_tz.utc if getattr(settings, 'USE_TZ', True) else None)

    alerts = []
    q = (request.GET.get("q") or "").strip()

    def make_alerts_for_order(order, is_wholesale=False):
        items = list(order.items.select_related("product").all())
        names = [getattr(getattr(i, "product", None), "name", None) for i in items]
        names = [n for n in names if n]
        names_unique = []
        for n in names:
            if n not in names_unique:
                names_unique.append(n)
        names_str = ", ".join(names_unique[:2]) if names_unique else "Items"

        # Pick a representative image
        img = None
        for it in items:
            p = getattr(it, "product", None)
            img = getattr(p, "image_url", None) or img
            if img:
                break

        # Determine seller name
        if is_wholesale:
            seller = getattr(order, "wholesaler", None)
        else:
            seller = None
            for it in items:
                prod = getattr(it, "product", None)
                seller = getattr(prod, "retailer", None)
                if seller:
                    break
        who = (
            getattr(seller, "full_name", None)
            or getattr(seller, "username", None)
            or getattr(seller, "email", None)
        )

        # Map progress stage to requested alert messages
        s = int(getattr(order, "progress_stage", 0) or 0)
        kind = None
        msg = None
        ts_event = getattr(order, "updated_at", None) or getattr(order, "created_at", None)
        if getattr(order, "status", None) == getattr(order, "OrderStatus", type("", (), {})).CANCELLED:
            kind = "cancelled"
            msg = f"Order #{order.id} - CANCELLED - {names_str}"
            ts_event = getattr(order, "updated_at", ts_event)
        elif s == 0:
            kind = "pending_confirmation"
            msg = f"Order #{order.id} - Confirmation is pending - {names_str}"
            ts_event = getattr(order, "created_at", ts_event)
        elif s == 1:
            kind = "confirmed"
            msg = f"Order #{order.id} - Confirmed - {names_str}"
        elif s == 2:
            kind = "dispatched"
            msg = f"Order #{order.id} - Dispatched - {names_str}"
        elif s == 3:
            kind = "facility"
            msg = f"Order #{order.id} - Arrived at Delivery Facility - {names_str}"
        elif s == 4:
            kind = "out_for_delivery"
            msg = f"Order #{order.id} - Out for Delivery - {names_str}"
        elif s >= 5:
            kind = "completed"
            msg = f"Order #{order.id} - COMPLETED - {names_str}"
            ts_event = getattr(order, "arrived_at", None) or ts_event
        else:
            return

        alerts.append({
            "kind": kind,
            "text": msg,
            "href": reverse("wholesale:order_detail", args=[order.id]) if is_wholesale else reverse("orders:order_detail", args=[order.id]),
            "image": img or "",
            "order_id": order.id,
            "ts": ts_event,
            "who": who,
        })

    # Customer orders
    for order in Order.objects.filter(customer=request.user).prefetch_related("items__product").order_by("-created_at"):
        make_alerts_for_order(order, is_wholesale=False)

    # Retailer wholesale orders
    if request.user.is_retailer:
        for order in WholesaleOrder.objects.filter(retailer=request.user).prefetch_related("items__product").order_by("-created_at"):
            make_alerts_for_order(order, is_wholesale=True)

    # Search filter by order number or product names
    if q:
        q_lower = q.lower()
        def matches(a):
            if q_lower.isdigit() and str(a.get("order_id", "")) == q_lower:
                return True
            return (q_lower in (a.get("text", "").lower()))
        alerts = [a for a in alerts if matches(a)]

    alerts.sort(key=lambda a: a.get("ts") or now, reverse=True)
    return render(request, "store/alerts.html", {"alerts": alerts, "search_query": q})


@login_required
def retailer_ordered_by(request):
    if not request.user.is_retailer:
        return HttpResponseForbidden("Only retailers can view orders received from customers.")

    from django.conf import settings
    from datetime import timedelta
    from decimal import Decimal
    days = getattr(settings, "ORDER_ESTIMATED_DAYS", 5)
    search_query = (request.GET.get("q") or "").strip()

    orders_qs = (
        Order.objects
        .filter(items__product__retailer=request.user)
        .order_by("-created_at")
        .prefetch_related("items__product", "customer")
        .distinct()
    )

    if search_query:
        orders_qs = orders_qs.filter(
            Q(customer__full_name__icontains=search_query) |
            Q(customer__email__icontains=search_query)
        ).distinct()

    orders_data = []
    for order in orders_qs:
        total = Decimal("0.00")
        qty_total = 0
        first_img = None
        first_item_name = None
        proxy_wholesalers = []
        for it in order.items.select_related("product").all():
            prod = getattr(it, "product", None)
            if getattr(prod, "retailer", None) == request.user:
                try:
                    price = Decimal(str(getattr(it, "price", 0) or 0))
                except Exception:
                    price = Decimal("0.00")
                try:
                    qty = int(getattr(it, "quantity", 0) or 0)
                except Exception:
                    qty = 0
                total += price * qty
                qty_total += qty
                if not first_img and prod is not None:
                    img = getattr(prod, "image_url", None)
                    if img:
                        first_img = img
                    first_item_name = getattr(prod, "name", None) or first_item_name
                if getattr(prod, "is_proxy", False):
                    pwp = getattr(prod, "proxy_wholesale_product", None)
                    wh = getattr(pwp, "wholesaler", None)
                    if wh is not None:
                        nm = getattr(wh, "full_name", None) or getattr(wh, "email", None) or str(wh)
                        if nm and nm not in proxy_wholesalers:
                            proxy_wholesalers.append(nm)

        customer = getattr(order, "customer", None)
        customer_name = None
        customer_email = None
        if customer is not None:
            customer_name = getattr(customer, "full_name", None) or getattr(customer, "username", None) or getattr(customer, "email", None)
            customer_email = getattr(customer, "email", None)


        # display status for list badge
        display_status = None
        if getattr(order, "status", None) == getattr(order, "OrderStatus", type("", (), {})).CANCELLED:
            if getattr(order, "payment_mode", "") == "Online" and getattr(order, "payment_status", "") == "PAID":
                display_status = "REFUND INITIATED"
            else:
                display_status = "CANCELLED"

        orders_data.append({
            "id": order.id,
            "created_at": order.created_at,
            "total": total,
            "payment_status": getattr(order, "payment_status", None),
            "display_payment_status": display_status or ("COMPLETED" if getattr(order, "progress_stage", 0) >= 5 else getattr(order, "payment_status", None)),
            "status": getattr(order, "status", None),
            "thumbnail": first_img,
            "first_item_name": first_item_name,
            "first_product_id": None,
            "item_count": qty_total,
            "retailer_name": customer_name,
            "customer_email": customer_email,
            "proxy_wholesalers": ", ".join(proxy_wholesalers) if proxy_wholesalers else None,
        })

    return render(
        request,
        "orders/order_history.html",
        {
            "orders": orders_data,
            "search_query": search_query,
            "order_history_action_url": reverse("store:ordered_by_retailer"),
            "order_detail_url_name": "store:retailer_order_detail",
            "page_title": "Ordered By",
            "ordered_by_mode": True,
            "search_placeholder": "Search by customer name",
        },
    )


@login_required
def retailer_order_detail(request, order_id):
    if not request.user.is_retailer:
        return HttpResponseForbidden("Only retailers can view this order.")

    order = get_object_or_404(Order, id=order_id)

    # Ensure the order contains items sold by this retailer
    has_items = order.items.filter(product__retailer=request.user).exists()
    if not has_items:
        return HttpResponseBadRequest("You are not allowed to view this order.")

    items_qs = order.items.select_related("product__category", "product__retailer").all()

    from decimal import Decimal
    from django.conf import settings
    from datetime import timedelta

    items = []
    order_total = Decimal("0.00")
    title_names = []
    customer_name = None
    customer_email = None
    proxy_wholesalers = []

    for it in items_qs:
        prod = getattr(it, "product", None)
        if getattr(prod, "retailer", None) != request.user:
            continue
        prod_name = getattr(prod, "name", "Unknown product")
        cat_name = None
        if prod is not None:
            cat = getattr(prod, "category", None)
            if cat is not None:
                cat_name = getattr(cat, "name", None) or getattr(cat, "title", None) or str(cat)

        try:
            price = Decimal(str(getattr(it, "price", 0) or 0))
        except Exception:
            price = Decimal("0.00")
        try:
            qty = int(getattr(it, "quantity", 0) or 0)
        except Exception:
            qty = 0

        subtotal = price * qty
        order_total += subtotal

        if getattr(prod, "name", None):
            title_names.append(str(getattr(prod, "name")))

        items.append({
            "image_url": getattr(prod, "image_url", None),
            "product_name": prod_name,
            "category_name": cat_name,
            "price": price,
            "quantity": qty,
            "subtotal": subtotal,
            "is_proxy": bool(getattr(prod, "is_proxy", False)),
            "proxy_wholesaler_name": (
                (getattr(getattr(prod, "proxy_wholesale_product", None), "wholesaler", None) and (
                    getattr(getattr(getattr(prod, "proxy_wholesale_product", None), "wholesaler", None), "full_name", None)
                    or getattr(getattr(getattr(prod, "proxy_wholesale_product", None), "wholesaler", None), "email", None)
                    or str(getattr(getattr(prod, "proxy_wholesale_product", None), "wholesaler", None))
                ))
            ) if getattr(prod, "is_proxy", False) else None,
            
        })

        if getattr(prod, "is_proxy", False):
            pwp = getattr(prod, "proxy_wholesale_product", None)
            wh = getattr(pwp, "wholesaler", None)
            if wh is not None:
                nm = getattr(wh, "full_name", None) or getattr(wh, "email", None) or str(wh)
                if nm and nm not in proxy_wholesalers:
                    proxy_wholesalers.append(nm)

    days = getattr(settings, "ORDER_ESTIMATED_DAYS", 5)
    # Remove expected delivery usage for order detail control; progress now driven by seller actions

    retailer_feedbacks_qs = OrderFeedback.objects.filter(order=order, product__retailer=request.user).select_related("product", "customer")

    cust = getattr(order, "customer", None)
    if cust is not None:
        customer_name = getattr(cust, "full_name", None) or getattr(cust, "username", None) or getattr(cust, "email", None)
        customer_email = getattr(cust, "email", None)

    if request.method == "POST":
        reply_text = (request.POST.get("retailer_reply_text") or "").strip()
        if reply_text:
            from datetime import datetime
            from django.conf import settings as dj_settings
            from datetime import timezone as dt_tz
            now = datetime.now(dt_tz.utc if getattr(dj_settings, 'USE_TZ', True) else None)
            for fb in retailer_feedbacks_qs:
                fb.reply_text = reply_text
                fb.reply_at = now
                fb.reply_by = request.user
                fb.save(update_fields=["reply_text", "reply_at", "reply_by"])
            return redirect("store:retailer_order_detail", order_id=order.id)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        next_stage = None
        stage_map = {
            "placed": 1,
            "dispatched": 2,
            "facility": 3,
            "out_for_delivery": 4,
        }
        if action in stage_map:
            next_stage = stage_map[action]
        if next_stage is not None and next_stage == getattr(order, "progress_stage", 0) + 1:
            order.progress_stage = next_stage
            if next_stage == 1:
                order.status = getattr(order.OrderStatus, "SHIPPED", order.status)
            order.save(update_fields=["progress_stage", "status"])
            return redirect("store:retailer_order_detail", order_id=order.id)
        if action == "cancel" and getattr(order, "progress_stage", 0) == 0:
            order.progress_stage = 0
            order.arrived_at = None
            order.status = getattr(order.OrderStatus, "CANCELLED", order.status)
            order.save(update_fields=["progress_stage", "arrived_at", "status"])
            return redirect("store:retailer_order_detail", order_id=order.id)

    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "items": items,
            "order_total": order_total,
            "order_title_names": ", ".join(list(dict.fromkeys(title_names))[:3]) + (", and more" if len(list(dict.fromkeys(title_names))) > 3 else ""),
            "retailer_feedbacks": list(retailer_feedbacks_qs),
            "retailer_reply_action_url": reverse("store:retailer_order_detail", args=[order.id]),
            "can_progress_control": True,
            "order_progress_action_url": reverse("store:retailer_order_detail", args=[order.id]),
            "customer_name": customer_name,
            "customer_email": customer_email,
            "proxy_wholesalers": ", ".join(proxy_wholesalers) if proxy_wholesalers else None,
            "order_display_payment_status": ("REFUND INITIATED" if (getattr(order, "status", None) == getattr(order, "OrderStatus", type("", (), {})).CANCELLED and getattr(order, "payment_mode", "") == "Online" and getattr(order, "payment_status", "") == "PAID") else ("CANCELLED" if getattr(order, "status", None) == getattr(order, "OrderStatus", type("", (), {})).CANCELLED else (getattr(order, "payment_status", None) or ""))),
        },
    )


# -------------------------------
# Cart-related views
# -------------------------------

@require_POST
def add_to_cart(request, product_id):
    """
    Add a product to the current cart (session or authenticated user).
    Returns JSON when called via AJAX with helpful snapshot data.
    """
    try:
        qty = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid quantity")

    if qty < 1:
        return HttpResponseBadRequest("Quantity must be >= 1")

    product = get_object_or_404(Product, id=product_id)

    if not getattr(product, "is_available", True):
        return HttpResponseBadRequest("Product is not available")

    cart = get_or_create_cart(request)

    # --- START: stock-safe add/update logic ---
    existing_qty = 0
    existing_item = CartItem.objects.filter(cart=cart, product=product).first()
    if existing_item:
        existing_qty = existing_item.quantity

    new_total = existing_qty + qty

    if new_total > product.stock_quantity:
        # Return an error describing available units
        return HttpResponseBadRequest(f"Only {product.stock_quantity} units available.")

    # Safe add/update
    item, created = CartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": qty})
    if not created:
        item.quantity = new_total
    item.save()
    # --- END: stock-safe add/update logic ---

    # compute a small snapshot to return
    try:
        # try to compute unit price & subtotal
        unit_price = float(getattr(item, "price", None) or getattr(item.product, "price", 0.0))
    except Exception:
        unit_price = 0.0
    subtotal = unit_price * int(getattr(item, "quantity", 0) or 0)

    # Cart-level totals: prefer attributes if available
    total_items = getattr(cart, "total_items", None)
    total_price = getattr(cart, "total_price", None)
    if total_items is None or total_price is None:
        # best-effort compute
        try:
            total_items = sum(int(getattr(i, "quantity", 0) or 0) for i in getattr(cart, "items").all())
            total_price = sum((float(getattr(i, "price", None) or getattr(i.product, "price", 0.0)) * int(getattr(i, "quantity", 0) or 0)) for i in getattr(cart, "items").all())
        except Exception:
            total_items = int(getattr(item, "quantity", 0) or 0)
            total_price = float(subtotal)

    # item snapshot to return
    item_snapshot = {
        "id": item.id,
        "product_id": getattr(item.product, "id", None),
        "title": getattr(item.product, "name", None) or getattr(item.product, "title", "") or "",
        "quantity": int(getattr(item, "quantity", 0) or 0),
        "unit_price": float(unit_price),
        "subtotal": float(subtotal),
        "image_url": getattr(getattr(item.product, "image", None), "url", "") or "",
    }

    # Return JSON for AJAX clients
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "created": bool(created),
            "item": item_snapshot,
            "total_items": int(total_items or 0),
            "total_price": float(total_price or 0.0),
        })

    # Non-AJAX: redirect back
    return redirect(request.POST.get("next") or request.META.get("HTTP_REFERER") or "/")


@require_POST
def update_cart_item(request, item_id):
    """
    Update a cart item's quantity (or remove if quantity <= 0).
    """
    cart = get_or_create_cart(request)
    # Support both regular and wholesale cart items
    item = CartItem.objects.filter(id=item_id, cart=cart).first()
    is_wholesale = False
    if not item:
        item = WholesaleCartItem.objects.filter(id=item_id, cart=cart).first()
        is_wholesale = bool(item)
    if not item:
        return HttpResponseBadRequest("Cart item not found")

    try:
        qty = int(request.POST.get("quantity", 0))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid quantity")

    if qty <= 0:
        item.delete()
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "ok": True,
                "total_items": sum(i.quantity for i in cart.items.all()) + sum(i.quantity for i in getattr(cart, "wholesale_items").all()),
                "total_price": float(sum((float(getattr(i, "price", None) or getattr(i.product, "price", 0.0)) * int(getattr(i, "quantity", 0) or 0)) for i in cart.items.all()) + sum((float(getattr(i.product, "price", 0.0)) * int(getattr(i, "quantity", 0) or 0)) for i in getattr(cart, "wholesale_items").all())),
            })
        return redirect("store:view_cart")

    # Stock validation: do not allow a cart item to exceed product stock
    stock = getattr(item.product, "stock_quantity", 0)
    if qty > stock:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return HttpResponseBadRequest(f"Only {stock} units available.")
        messages.warning(request, f"Only {stock} units available.")
        return redirect("store:view_cart")

    item.quantity = qty
    item.save()

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "total_items": sum(i.quantity for i in cart.items.all()) + sum(i.quantity for i in getattr(cart, "wholesale_items").all()),
            "total_price": float(sum((float(getattr(i, "price", None) or getattr(i.product, "price", 0.0)) * int(getattr(i, "quantity", 0) or 0)) for i in cart.items.all()) + sum((float(getattr(i.product, "price", 0.0)) * int(getattr(i, "quantity", 0) or 0)) for i in getattr(cart, "wholesale_items").all())),
        })

    return redirect("store:view_cart")


def view_cart(request):
    """
    Render the cart page and compute numeric totals for each item and the cart.
    Do NOT assign attributes on the Cart model if it defines read-only properties.
    """
    cart = get_or_create_cart(request)
    search_query = (request.GET.get("q") or "").strip()

    # Get items (safe list)
    items_qs = cart.items.select_related("product", "product__retailer").all() if getattr(cart, "pk", None) else []
    w_items_qs = cart.wholesale_items.select_related("product", "product__wholesaler").all() if getattr(cart, "pk", None) else []
    if search_query:
        try:
            items_qs = items_qs.filter(product__name__icontains=search_query)
        except Exception:
            pass
        try:
            w_items_qs = w_items_qs.filter(product__name__icontains=search_query)
        except Exception:
            pass
    items = list(items_qs)
    w_items = list(w_items_qs)

    # Compute numeric subtotal for each item and cart totals
    cart_total_items = 0
    cart_total_price = 0.0

    for item in items:
        # safe quantity
        try:
            qty = int(item.quantity)
        except Exception:
            qty = 0
        cart_total_items += qty

        # unit price: prefer item.price if stored on the cart item
        try:
            unit_price = float(getattr(item, "price", None) or getattr(item.product, "price", 0.0))
        except Exception:
            unit_price = 0.0

        subtotal = qty * unit_price

        # attach numeric fields to the item for template use (safe)
        item.unit_price = unit_price
        item.subtotal = subtotal

        cart_total_price += subtotal

    # Include wholesale items with computed fields
    for w in w_items:
        try:
            qty = int(getattr(w, "quantity", 0) or 0)
        except Exception:
            qty = 0
        cart_total_items += qty

        try:
            unit_price = float(getattr(w.product, "price", 0.0))
        except Exception:
            unit_price = 0.0
        subtotal = qty * unit_price

        # attach numeric fields to the item for template use (safe)
        w.unit_price = unit_price
        w.subtotal = subtotal

        cart_total_price += subtotal

    # Merge regular and wholesale items into single list for template
    combined_items = items + w_items

    context = {
        "cart": cart,
        "items": combined_items,
        "cart_total_items": cart_total_items,
        "cart_total_price": cart_total_price,
        "search_query": search_query,
    }
    return render(request, "store/cart.html", context)

@require_GET
def cart_summary_json(request):
    """
    Return a small JSON snapshot of the cart for client-side rendering.
    """
    snapshot = {"cart_total_items": 0, "cart_total_price": 0.0, "cart_items": []}

    try:
        cart = get_or_create_cart(request)
    except Exception:
        return JsonResponse(snapshot)

    # total items via property if available
    try:
        snapshot["cart_total_items"] = int(getattr(cart, "total_items", 0) or 0)
    except Exception:
        snapshot["cart_total_items"] = 0

    total_price = 0.0
    items_list = []
    try:
        items_qs = getattr(cart, "items", None)
        iterator = items_qs.all() if hasattr(items_qs, "all") else items_qs or []
        for item in iterator:
            try:
                qty = int(getattr(item, "quantity", 0) or 0)
            except Exception:
                qty = 0
            try:
                unit_price = float(getattr(item, "price", None) or getattr(item.product, "price", 0.0))
            except Exception:
                unit_price = 0.0
            subtotal = qty * unit_price
            total_price += subtotal

            image_url = ""
            try:
                prod = getattr(item, "product", None)
                if prod is not None:
                    image_field = getattr(prod, "image", None)
                    if image_field:
                        try:
                            image_url = image_field.url
                        except Exception:
                            image_url = str(image_field)
                    else:
                        try:
                            image_url = prod.image_url or ""
                        except Exception:
                            image_url = ""
            except Exception:
                image_url = ""

            title = ""
            try:
                title = getattr(item.product, "name", "") or getattr(item.product, "title", "") or ""
            except Exception:
                title = ""

            items_list.append({
                "id": getattr(item, "id", None),
                "product_id": getattr(item.product, "id", None) if getattr(item, "product", None) else None,
                "title": title,
                "quantity": qty,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "image_url": image_url,
            })
        # Include wholesale cart items
        w_items = getattr(cart, "wholesale_items", None)
        w_iter = w_items.all() if hasattr(w_items, "all") else w_items or []
        for w in w_iter:
            try:
                qty = int(getattr(w, "quantity", 0) or 0)
            except Exception:
                qty = 0
            try:
                unit_price = float(getattr(w.product, "price", 0.0))
            except Exception:
                unit_price = 0.0
            subtotal = qty * unit_price
            total_price += subtotal
            w_image = getattr(w.product, "image_url", "") or ""
            w_title = getattr(w.product, "name", "")
            items_list.append({
                "id": getattr(w, "id", None),
                "product_id": getattr(w.product, "id", None),
                "title": w_title,
                "quantity": qty,
                "unit_price": unit_price,
                "subtotal": subtotal,
                "image_url": w_image,
            })
    except Exception:
        items_list = []

    snapshot["cart_items"] = items_list
    snapshot["cart_total_price"] = float(total_price or 0.0)
    # If total_items was not set earlier, ensure consistent value
    if snapshot["cart_total_items"] == 0:
        snapshot["cart_total_items"] = sum(it["quantity"] for it in items_list) if items_list else 0

    return JsonResponse(snapshot)
def product_detail(request, product_id):
    """
    Minimal product detail page used by order-history thumbnails.
    Adjust the template to match your main product detail UI if you have one.
    """
    product = get_object_or_404(Product, id=product_id)
    # If you want to show related products or reviews, add to context here
    context = {
        "product": product,
    }
    return render(request, "store/product_detail.html", context)
    has_filters = bool(pincode or search_query or selected_categories or sort)
@login_required
@require_POST
def proxy_add(request, wprod_id):
    if not request.user.is_retailer:
        return HttpResponseForbidden("Only retailers can serve as proxy.")
    wp = get_object_or_404(WholesaleProduct, id=wprod_id)

    # Try find existing proxy product
    p = Product.objects.filter(retailer=request.user, proxy_wholesale_product=wp).first()
    if not p:
        p = Product(
            retailer=request.user,
            category=wp.category,
            name=wp.name,
            description=getattr(wp, 'description', '') or '',
            price=wp.price,
            stock_quantity=max(int(getattr(wp, 'stock_quantity', 0) or 0), 0),
            image_url=getattr(wp, 'image_url', None),
        )
    p.is_proxy = True
    p.proxy_wholesale_product = wp
    p.is_available = True
    p.save()

    # Back to dashboard
    return redirect("store:retailer_dashboard")


@login_required
@require_POST
def proxy_remove(request, wprod_id):
    if not request.user.is_retailer:
        return HttpResponseForbidden("Only retailers can manage proxy products.")
    wp = get_object_or_404(WholesaleProduct, id=wprod_id)
    p = Product.objects.filter(retailer=request.user, proxy_wholesale_product=wp).first()
    if p:
        p.delete()
    return redirect("store:retailer_dashboard")


@login_required
@require_POST
def proxy_remove_by_product(request, product_id):
    if not request.user.is_retailer:
        return HttpResponseForbidden("Only retailers can manage proxy products.")
    p = get_object_or_404(Product, id=product_id, retailer=request.user)
    if p.is_proxy:
        # remove proxy mapping; delete to keep list clean
        p.delete()
    return redirect("store:retailer_dashboard")
