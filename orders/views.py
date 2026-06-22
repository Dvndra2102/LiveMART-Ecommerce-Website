# orders/views.py
from decimal import Decimal
import json
from datetime import timedelta
import re

import razorpay
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.views.decorators.http import require_POST

from store.models import Product, CartItem
from store.utils import get_or_create_cart  # reuse existing cart logic
from .models import Order, OrderItem, OrderFeedback


@require_POST
@login_required
def add_to_cart(request, product_id):
    """
    (Optional) Separate add-to-cart for orders app – you can ignore this
    if you're using the store.add_to_cart view instead.
    """
    product = get_object_or_404(Product, id=product_id)
    # For simplicity, always add 1
    cart = get_or_create_cart(request)

    item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={"quantity": 1},
    )
    if not created:
        item.quantity += 1
        item.save()

    request.session["message"] = f"Added {product.name} to cart."
    return redirect("store:product_list")


@login_required
def view_cart(request):
    """
    You probably don't need this if you're using store:view_cart.
    Keeping it here for completeness.
    """
    cart = get_or_create_cart(request)
    items = list(
        cart.items.select_related("product", "product__retailer").all()
    ) if getattr(cart, "pk", None) else []

    cart_total_items = 0
    cart_total_price = 0.0

    for item in items:
        try:
            qty = int(item.quantity)
        except Exception:
            qty = 0
        cart_total_items += qty

        try:
            unit_price = float(getattr(item, "price", None) or getattr(item.product, "price", 0.0))
        except Exception:
            unit_price = 0.0

        subtotal = qty * unit_price
        item.unit_price = unit_price
        item.subtotal = subtotal
        cart_total_price += subtotal

    context = {
        "cart": cart,
        "items": items,
        "cart_total_items": cart_total_items,
        "cart_total_price": cart_total_price,
    }
    return render(request, "orders/cart_orders.html", context)


@login_required
@transaction.atomic
def checkout(request):
    """
    GET  -> Show checkout page with order summary + payment mode.
    POST -> 
        - If COD: create Order + OrderItems, reduce stock, clear cart, success page.
        - If Online: create pending Order + Razorpay order, show Razorpay payment page.
    """
    cart = get_or_create_cart(request)
    items_qs = cart.items.select_related("product", "product__retailer").all() if getattr(cart, "pk", None) else []
    items = list(items_qs)

    # Compute totals like in store.view_cart
    cart_total_items = 0
    cart_total_price = 0.0

    for item in items:
        try:
            qty = int(item.quantity)
        except Exception:
            qty = 0
        cart_total_items += qty

        try:
            unit_price = float(getattr(item, "price", None) or getattr(item.product, "price", 0.0))
        except Exception:
            unit_price = 0.0

        subtotal = qty * unit_price
        item.unit_price = unit_price
        item.subtotal = subtotal
        cart_total_price += subtotal

    # If cart is empty, redirect back to product list
    if not items:
        return redirect("store:product_list")

    # ---------- GET: show checkout page ----------
    if request.method == "GET":
        return render(
            request,
            "orders/checkout.html",
            {
                "items": items,
                "cart_total_items": cart_total_items,
                "cart_total_price": cart_total_price,
            },
        )

    # ---------- POST: place order / init payment ----------
    # Address fields
    addr_state = (request.POST.get("addr_state") or "").strip()
    addr_district = (request.POST.get("addr_district") or "").strip()
    addr_colony = (request.POST.get("addr_colony") or "").strip()
    addr_pincode = (request.POST.get("addr_pincode") or "").strip()
    addr_road_number = (request.POST.get("addr_road_number") or "").strip()
    addr_house_number = (request.POST.get("addr_house_number") or "").strip()

    payment_mode = request.POST.get("payment_mode")

    if payment_mode not in ["Online", "Cash on Delivery"]:
        return render(
            request,
            "orders/checkout.html",
            {
                "items": items,
                "cart_total_items": cart_total_items,
                "cart_total_price": cart_total_price,
                "error": "Please select a valid payment mode.",
                "addr_state": addr_state,
                "addr_district": addr_district,
                "addr_colony": addr_colony,
                "addr_pincode": addr_pincode,
                "addr_road_number": addr_road_number,
                "addr_house_number": addr_house_number,
            },
        )

    # Basic validation for address inputs
    if not all([addr_state, addr_district, addr_colony, addr_pincode, addr_house_number]):
        return render(
            request,
            "orders/checkout.html",
            {
                "items": items,
                "cart_total_items": cart_total_items,
                "cart_total_price": cart_total_price,
                "error": "Please fill out the shipment address completely.",
                "addr_state": addr_state,
                "addr_district": addr_district,
                "addr_colony": addr_colony,
                "addr_pincode": addr_pincode,
                "addr_road_number": addr_road_number,
                "addr_house_number": addr_house_number,
            },
        )

    customer = request.user

    grouped = {}
    for item in items:
        product = getattr(item, "product", None)
        if not product:
            continue
        seller = getattr(product, "retailer", None)
        grouped.setdefault(seller, []).append(item)

    created_orders = []
    for seller, seller_items in grouped.items():
        o = Order.objects.create(
            customer=customer,
            payment_mode=payment_mode,
            addr_state=addr_state,
            addr_district=addr_district,
            addr_colony=addr_colony,
            addr_pincode=addr_pincode,
            addr_road_number=addr_road_number,
            addr_house_number=addr_house_number,
        )
        for item in seller_items:
            product = getattr(item, "product", None)
            if not product:
                continue
            qty = int(getattr(item, "quantity", 0) or 0)
            OrderItem.objects.create(
                order=o,
                product=product,
                quantity=qty,
                price=item.unit_price,
            )
        created_orders.append(o)

    # ---------- If COD: fulfil immediately ----------
    if payment_mode == "Cash on Delivery":
        for o in created_orders:
            _fulfil_order_and_clear_cart(o, cart)
        return render(request, "orders/checkout_success.html", {"order": created_orders[0] if created_orders else None})

    # ---------- If Online: create Razorpay order & show payment page ----------
    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    except AttributeError:
        # Keys not configured properly
        return HttpResponseBadRequest("Razorpay keys not configured in settings.")

    razorpay_order = client.order.create({
        "amount": int(cart_total_price * 100),
        "currency": "INR",
        "payment_capture": 1,
        "notes": {
            "internal_order_ids": ",".join(str(o.id) for o in created_orders),
            "customer_email": customer.email or "",
        }
    })

    # Optional: store Razorpay order id on our Order model (requires field)
    # Make sure you added this field in models.py:
    # razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    for o in created_orders:
        if hasattr(o, "razorpay_order_id"):
            o.razorpay_order_id = razorpay_order.get("id")
            o.save()

    return render(
        request,
        "orders/payment_razorpay.html",
        {
            "order": created_orders[0] if created_orders else None,
            "items": items,
            "cart_total_price": cart_total_price,
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "razorpay_order_id": razorpay_order.get("id"),
            "amount": int(cart_total_price * 100),
            "currency": "INR",
            "verify_url": reverse("orders:razorpay_verify"),
            "back_to_checkout_url": reverse("orders:checkout"),
            "payer_email": customer.email or "",
        },
    )


def _fulfil_order_and_clear_cart(order, cart):
    """
    Deduct stock, clear cart, and update order status.
    Used for COD immediately and for Online AFTER successful payment.
    """
    products_to_update = []

    for item in order.items.select_related("product").all():
        product = item.product
        if not product:
            continue

        qty = item.quantity

        # Stock check
        if product.stock_quantity < qty:
            if product.stock_quantity <= 0:
                continue
            qty = product.stock_quantity
            item.quantity = qty
            item.save()

        product.stock_quantity -= qty
        products_to_update.append(product)

    if products_to_update:
        Product.objects.bulk_update(products_to_update, ["stock_quantity"])

    # Clear DB cart
    try:
        cart.items.all().delete()
    except Exception:
        pass

    # Optionally update statuses if you added fields
    if hasattr(order, "status"):
        order.status = Order.OrderStatus.PENDING  # or CONFIRMED if you add it
    if hasattr(order, "payment_status") and order.payment_mode == "Online":
        order.payment_status = getattr(Order.PaymentStatus, "PAID", None) or "PAID"
    order.save()


@csrf_exempt
@transaction.atomic
def razorpay_verify(request):
    """
    Endpoint hit from JS after Razorpay payment success.
    Verifies signature and then fulfils the order.
    """
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "Invalid method"}, status=405)

    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    order_id = data.get("order_id")
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_signature = data.get("razorpay_signature")

    if not all([order_id, razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return JsonResponse({"ok": False, "error": "Missing parameters"}, status=400)

    order = get_object_or_404(Order, id=order_id)

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        if hasattr(order, "payment_status"):
            order.payment_status = getattr(Order.PaymentStatus, "FAILED", None) or "FAILED"
            order.save()
        return JsonResponse({"ok": False, "error": "Signature verification failed"}, status=400)

    sibling_qs = Order.objects.filter(customer=request.user, razorpay_order_id=razorpay_order_id)
    siblings = list(sibling_qs) or [order]

    for o in siblings:
        if hasattr(o, "razorpay_payment_id"):
            o.razorpay_payment_id = razorpay_payment_id
        if hasattr(o, "razorpay_signature"):
            o.razorpay_signature = razorpay_signature
        if hasattr(o, "payment_status"):
            o.payment_status = getattr(Order.PaymentStatus, "PAID", None) or "PAID"
        o.save()

    cart = get_or_create_cart(request)
    for o in siblings:
        _fulfil_order_and_clear_cart(o, cart)

    first_id = getattr(siblings[0], "id", order.id)
    return JsonResponse({
        "ok": True,
        "redirect_url": f"/orders/success/{first_id}/"
    })


@login_required
def order_success(request, order_id):
    """
    Page shown after payment success.
    """
    order = get_object_or_404(Order, id=order_id)

    # Security: user can only view their own order
    if order.customer != request.user:
        return HttpResponseBadRequest("You are not allowed to view this order.")

    return render(request, "orders/checkout_success.html", {"order": order})


# helper regex to remove accidental template braces if present
_BRACE_RE = re.compile(r"\{\{\s*(.*?)\s*\}\}")

@login_required
def order_history(request):
    """
    Show a list of previous orders for the logged-in user.
    Defensive: ensures status and payment_status are plain strings (no {{ ... }} inside).
    """
    days = getattr(settings, "ORDER_ESTIMATED_DAYS", 5)
    search_query = (request.GET.get("q") or "").strip()

    orders_qs = (
        Order.objects
        .filter(customer=request.user)
        .order_by("-created_at")
        .prefetch_related("items__product", "items__product__category")
    )

    if search_query:
        orders_qs = orders_qs.filter(items__product__name__icontains=search_query).distinct()

    def _get_product_image(product):
        if not product:
            return None
        # safe ImageField .url
        try:
            img_field = getattr(product, "image", None)
            if img_field:
                url = getattr(img_field, "url", None)
                if url:
                    return url
        except Exception:
            pass
        # plain image_url string
        img_url = getattr(product, "image_url", None)
        if img_url:
            return img_url
        # helper method
        getter = getattr(product, "get_image_url", None)
        if callable(getter):
            try:
                val = getter()
                if val:
                    return val
            except Exception:
                pass
        return None

    def _clean_value(v):
        """Return a plain string and remove any accidental template-brace wrappers."""
        if v is None:
            return ""
        s = str(v)
        # If someone accidentally stored "{{ PAID }}" or "{{ o.payment_status }}" strip braces
        m = _BRACE_RE.search(s)
        if m:
            # prefer the inner content if it's just a simple token, else keep stripped
            inner = m.group(1).strip()
            # if inner equals the original stripped, return inner; otherwise return stripped string w/o braces
            return inner if inner else s.replace("{{", "").replace("}}", "").strip()
        return s

    orders_data = []
    for order in orders_qs:
        total = Decimal("0.00")
        first_img = None
        first_item_name = None
        first_product_id = None
        item_count = 0
        item_names = []
        retailer_name = None
        retailer_email = None

        for it in order.items.select_related("product").all():
            item_count += 1
            # safe price/qty
            try:
                price = Decimal(str(getattr(it, "price", 0) or 0))
            except Exception:
                price = Decimal("0.00")
            try:
                qty = int(getattr(it, "quantity", 0) or 0)
            except Exception:
                qty = 0

            total += price * qty

            prod = getattr(it, "product", None)
            if not first_img and prod is not None:
                img = _get_product_image(prod)
                if img:
                    first_img = img
                first_item_name = getattr(prod, "name", None) or first_item_name
                first_product_id = getattr(prod, "id", None) or first_product_id

            # Pull retailer info from the first item's seller
            if prod is not None and not retailer_name:
                seller = getattr(prod, "retailer", None)
                if seller is not None:
                    retailer_name = getattr(seller, "full_name", None) or getattr(seller, "email", None) or str(seller)
                    retailer_email = getattr(seller, "email", None)

            if not first_item_name and getattr(it, "product", None):
                first_item_name = getattr(it.product, "name", None) or first_item_name

            name_val = None
            if prod is not None:
                name_val = getattr(prod, "name", None)
            if name_val:
                item_names.append(str(name_val))


        raw_payment_status = getattr(order, "payment_status", None)
        display_payment_status = "COMPLETED" if getattr(order, "progress_stage", 0) >= 5 else (raw_payment_status or "")
        if getattr(order, "status", None) == getattr(order, "OrderStatus", type("", (), {})).CANCELLED:
            if getattr(order, "payment_mode", "") == "Online" and getattr(order, "payment_status", "") == "PAID":
                display_payment_status = "REFUND INITIATED"
            else:
                display_payment_status = "CANCELLED"
        raw_status = getattr(order, "status", None)

        # Build comma-separated names (unique, preserve original order)
        seen = set()
        ordered_unique_names = []
        for nm in item_names:
            if nm not in seen:
                seen.add(nm)
                ordered_unique_names.append(nm)
        if len(ordered_unique_names) > 3:
            item_names_str = ", ".join(ordered_unique_names[:3]) + ", and more"
        else:
            item_names_str = ", ".join(ordered_unique_names)

        orders_data.append({
            "id": order.id,
            "created_at": order.created_at,
            "total": total,
            "payment_status": _clean_value(raw_payment_status),
            "display_payment_status": _clean_value(display_payment_status),
            "status": _clean_value(raw_status),
            "thumbnail": first_img,
            "first_item_name": first_item_name,
            "first_product_id": first_product_id,
            "item_count": item_count,
            "item_names": item_names_str,
            "retailer_name": retailer_name,
        })

    return render(request, "orders/order_history.html", {"orders": orders_data, "search_query": search_query})



@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    # security
    if order.customer != request.user:
        return HttpResponseBadRequest("You are not allowed to view this order.")

    # Prefetch product and category for performance
    items_qs = order.items.select_related("product__category").all()

    items = []
    order_total = Decimal("0.00")
    title_names = []

    for it in items_qs:
        prod = getattr(it, "product", None)
        prod_name = getattr(prod, "name", "Unknown product")

        # Safely extract category name
        cat_name = None
        if prod is not None:
            cat = getattr(prod, "category", None)
            if cat is not None:
                cat_name = getattr(cat, "name", None) or getattr(cat, "title", None) or str(cat)

        # Price/qty/subtotal with Decimal safety
        try:
            price = Decimal(str(getattr(it, "price", 0) or 0))
        except Exception:
            price = Decimal("0.00")
        try:
            qty = int(getattr(it, "quantity", 0) or 0)
        except Exception:
            qty = 0

        subtotal = (price * qty)
        order_total += subtotal

        if getattr(prod, "name", None):
            title_names.append(str(getattr(prod, "name")))

        items.append({
            "id": it.id,
            "product_name": prod_name,
            "category_name": cat_name,
            "quantity": qty,
            "price": price,
            "subtotal": subtotal,
            "image_url": getattr(prod, "image_url", "") if prod else "",
            "product": prod,
        })

        # capture retailer info from first item (orders are split per retailer)
        if not locals().get("_retailer_name_set"):
            seller = getattr(prod, "retailer", None)
            if seller is not None:
                retailer_name = getattr(seller, "full_name", None) or getattr(seller, "email", None) or str(seller)
                retailer_email = getattr(seller, "email", None)
                _retailer_name_set = True

    display_status = None
    if getattr(order, "status", None) == getattr(Order, "OrderStatus", type("", (), {})).CANCELLED:
        if getattr(order, "payment_mode", "") == "Online" and getattr(order, "payment_status", "") == "PAID":
            display_status = "REFUND INITIATED"
        else:
            display_status = "CANCELLED"

    context = {
        "order": order,
        "items": items,
        "order_total": order_total,
        "order_title_names": ", ".join(list(dict.fromkeys(title_names))[:3]) + (", and more" if len(list(dict.fromkeys(title_names))) > 3 else ""),
        "retailer_name": locals().get("retailer_name"),
        "retailer_email": locals().get("retailer_email"),
        "order_display_payment_status": display_status or ("COMPLETED" if (getattr(order, "progress_stage", 0) >= 5) else (getattr(order, "payment_status", None) or "")),
        "retailer_replies": list(OrderFeedback.objects.filter(order=order, reply_text__isnull=False).select_related("reply_by", "product")),
        "can_progress_control": False,
        "can_buyer_mark_arrived": (request.user == getattr(order, "customer", None) and getattr(order, "progress_stage", 0) >= 4 and not getattr(order, "arrived_at", None)),
        "order_progress_action_url": request.path,
    }
    if request.method == "POST" and request.user == getattr(order, "customer", None):
        action = (request.POST.get("action") or "").strip()
        if action == "mark_arrived" and getattr(order, "progress_stage", 0) >= 4 and not getattr(order, "arrived_at", None):
            from datetime import datetime
            from django.conf import settings as dj_settings
            from datetime import timezone as dt_tz
            order.progress_stage = 5
            order.arrived_at = datetime.now(dt_tz.utc if getattr(dj_settings, 'USE_TZ', True) else None)
            order.status = getattr(order.OrderStatus, "DELIVERED", order.status)
            if hasattr(order, "payment_status"):
                order.payment_status = getattr(Order.PaymentStatus, "PAID", None) or "PAID"
            order.save(update_fields=["progress_stage", "arrived_at", "status"])
            return redirect(request.path)
        if action == "cancel" and getattr(order, "progress_stage", 0) >= 4 and not getattr(order, "arrived_at", None):
            order.progress_stage = 0
            order.arrived_at = None
            order.status = getattr(order.OrderStatus, "CANCELLED", order.status)
            order.save(update_fields=["progress_stage", "arrived_at", "status"])
            return redirect(request.path)
    return render(request, "orders/order_detail.html", context)


@login_required
def give_feedback(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.customer != request.user:
        return HttpResponseBadRequest("You are not allowed to review this order.")

    items_qs = order.items.select_related("product", "product__retailer").all()
    items = list(items_qs)

    if request.method == "POST":
        created = 0
        for it in items:
            key = f"feedback_{it.id}"
            text = (request.POST.get(key) or "").strip()
            if not text:
                continue
            OrderFeedback.objects.create(
                order=order,
                product=getattr(it, "product", None),
                customer=request.user,
                text=text,
            )
            created += 1
        if created:
            return redirect("orders:order_detail", order_id=order.id)

    return render(request, "orders/give_feedback.html", {"order": order, "items": items})
