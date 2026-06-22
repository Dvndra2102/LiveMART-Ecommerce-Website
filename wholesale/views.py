from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, HttpResponseBadRequest, JsonResponse
from django.views.decorators.http import require_POST
from django.utils.text import slugify
from django.db.models import Q
from django.conf import settings
from decimal import Decimal
import json
import razorpay
from .models import WholesaleProduct
from .models import WholesaleOrder, WholesaleOrderItem, WholesaleCartItem
from store.models import Category
from store.models import Cart
from store.utils import get_or_create_cart
from .forms import WholesaleProductForm
from django.views.decorators.http import require_POST
from django.db import transaction
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from datetime import timedelta
import re

@login_required
def wholesaler_dashboard(request):
    """
    Displays the Wholesaler's "My Products" page.
    Handles adding, editing, and deleting products.
    """
    if not request.user.is_wholesaler:
        return HttpResponseForbidden("You are not authorized to view this page.")

    products = WholesaleProduct.objects.filter(wholesaler=request.user)
    categories = Category.objects.all()
    search_query = (request.GET.get("q") or "").strip()
    if search_query:
        products = products.filter(Q(name__icontains=search_query) | Q(description__icontains=search_query))
    
    if request.method == "POST":
        form_type = request.POST.get("form_type")
        
        if form_type == "add_product":
            form = WholesaleProductForm(request.POST)
            if form.is_valid():
                product = form.save(commit=False)
                product.wholesaler = request.user
                product.save()
                return redirect("wholesale:wholesaler_dashboard")
        
        elif form_type == "edit_product":
            product_id = request.POST.get("product_id")
            product = get_object_or_404(WholesaleProduct, id=product_id, wholesaler=request.user)
            form = WholesaleProductForm(request.POST, instance=product)
            if form.is_valid():
                form.save()
                return redirect("wholesale:wholesaler_dashboard")
    
    add_form = WholesaleProductForm()
    
    context = {
        "products": products,
        "categories": categories,
        "search_query": search_query,
        "add_form": add_form,
    }
    return render(request, "wholesale/wholesaler_dashboard.html", context)

@login_required
def delete_wholesale_product(request, product_id):
    """
    Handles the POST request to delete a wholesale product.
    """
    if not request.user.is_wholesaler:
        return HttpResponseForbidden()
        
    product = get_object_or_404(WholesaleProduct, id=product_id, wholesaler=request.user)
    if request.method == "POST":
        product.delete()
        return redirect("wholesale:wholesaler_dashboard")
    
    return redirect("wholesale:wholesaler_dashboard")

@login_required
def order_product(request, product_id):
    """
    Allow a RETAILER to place a simple purchase order for a wholesale product.
    """
    if not request.user.is_retailer:
        return HttpResponseForbidden("Only retailers can place wholesale orders.")

    product = get_object_or_404(WholesaleProduct, id=product_id, is_available=True, stock_quantity__gt=0)

    if request.method == "POST":
        try:
            qty = int(request.POST.get("quantity") or 1)
        except Exception:
            qty = 1
        qty = max(1, qty)

        order = WholesaleOrder.objects.create(
            retailer=request.user,
            wholesaler=product.wholesaler,
            status=WholesaleOrder.OrderStatus.PENDING,
        )
        WholesaleOrderItem.objects.create(
            order=order,
            product=product,
            quantity=qty,
            price=product.price,
        )
        return redirect("wholesale:wholesaler_dashboard")

    return HttpResponseForbidden("Invalid method")

@require_POST
@login_required
def add_wholesale_to_cart(request, product_id):
    """
    Add a wholesale product to the user's cart (used by retailer interface).
    Returns JSON compatible with customer add-to-cart handler.
    """
    try:
        qty = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Invalid quantity")

    if qty < 1:
        return HttpResponseBadRequest("Quantity must be >= 1")

    product = get_object_or_404(WholesaleProduct, id=product_id)
    if not getattr(product, "is_available", True):
        return HttpResponseBadRequest("Product is not available")

    # get or create cart (same concept as store)
    cart = get_or_create_cart(request)

    existing_item = WholesaleCartItem.objects.filter(cart=cart, product=product).first()
    existing_qty = existing_item.quantity if existing_item else 0
    new_total = existing_qty + qty

    if new_total > product.stock_quantity:
        return HttpResponseBadRequest(f"Only {product.stock_quantity} units available.")

    item, created = WholesaleCartItem.objects.get_or_create(cart=cart, product=product, defaults={"quantity": qty})
    if not created:
        item.quantity = new_total
        item.save()

    # Snapshot for client
    try:
        unit_price = float(getattr(product, "price", 0.0))
    except Exception:
        unit_price = 0.0
    subtotal = unit_price * int(getattr(item, "quantity", 0) or 0)

    # Cart totals (best effort)
    try:
        total_items = sum(int(getattr(i, "quantity", 0) or 0) for i in getattr(cart, "items").all())
        total_items += sum(int(getattr(i, "quantity", 0) or 0) for i in getattr(cart, "wholesale_items").all())
    except Exception:
        total_items = int(getattr(item, "quantity", 0) or 0)

    try:
        total_price = sum((float(getattr(i, "price", None) or getattr(i.product, "price", 0.0)) * int(getattr(i, "quantity", 0) or 0)) for i in getattr(cart, "items").all())
        total_price += sum((float(getattr(i.product, "price", 0.0)) * int(getattr(i, "quantity", 0) or 0)) for i in getattr(cart, "wholesale_items").all())
    except Exception:
        total_price = float(subtotal)

    item_snapshot = {
        "id": item.id,
        "product_id": product.id,
        "title": getattr(product, "name", ""),
        "quantity": int(getattr(item, "quantity", 0) or 0),
        "unit_price": float(unit_price),
        "subtotal": float(subtotal),
        "image_url": getattr(product, "image_url", "") or "",
    }

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "ok": True,
            "created": bool(created),
            "item": item_snapshot,
            "total_items": int(total_items or 0),
            "total_price": float(total_price or 0.0),
        })

    return redirect(request.POST.get("next") or request.META.get("HTTP_REFERER") or "/")

@login_required
@transaction.atomic
def retailer_checkout(request):
    """
    Checkout page for retailers purchasing wholesale items.
    Mirrors the customer checkout UI but uses WholesaleOrder and WholesaleOrderItem.
    Groups items per wholesaler into separate orders on POST.
    """
    if not request.user.is_retailer:
        return HttpResponseForbidden("Only retailers can checkout wholesale items.")

    cart = get_or_create_cart(request)
    w_items_qs = cart.wholesale_items.select_related("product", "product__wholesaler").all() if getattr(cart, "pk", None) else []
    w_items = list(w_items_qs)

    cart_total_items = 0
    cart_total_price = 0.0
    for it in w_items:
        try:
            qty = int(getattr(it, "quantity", 0) or 0)
        except Exception:
            qty = 0
        cart_total_items += qty
        try:
            unit_price = float(getattr(it.product, "price", 0.0))
        except Exception:
            unit_price = 0.0
        subtotal = unit_price * qty
        it.unit_price = unit_price
        it.subtotal = subtotal
        cart_total_price += subtotal

    if not w_items:
        return redirect("store:product_list")

    if request.method == "GET":
        return render(
            request,
            "orders/checkout.html",
            {
                "items": w_items,
                "cart_total_items": cart_total_items,
                "cart_total_price": cart_total_price,
                "checkout_action_url": reverse("wholesale:checkout"),
            },
        )

    # POST: capture address and payment
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
                "items": w_items,
                "cart_total_items": cart_total_items,
                "cart_total_price": cart_total_price,
                "error": "Please select a valid payment mode.",
                "addr_state": addr_state,
                "addr_district": addr_district,
                "addr_colony": addr_colony,
                "addr_pincode": addr_pincode,
                "addr_road_number": addr_road_number,
                "addr_house_number": addr_house_number,
                "checkout_action_url": reverse("wholesale:checkout"),
            },
        )

    if not all([addr_state, addr_district, addr_colony, addr_pincode, addr_house_number]):
        return render(
            request,
            "orders/checkout.html",
            {
                "items": w_items,
                "cart_total_items": cart_total_items,
                "cart_total_price": cart_total_price,
                "error": "Please fill out the shipment address completely.",
                "addr_state": addr_state,
                "addr_district": addr_district,
                "addr_colony": addr_colony,
                "addr_pincode": addr_pincode,
                "addr_road_number": addr_road_number,
                "addr_house_number": addr_house_number,
                "checkout_action_url": reverse("wholesale:checkout"),
            },
        )

    # Group items by wholesaler and create orders
    grouped = {}
    for it in w_items:
        wholesaler = getattr(it.product, "wholesaler", None)
        if not wholesaler:
            wholesaler = None
        grouped.setdefault(wholesaler, []).append(it)

    created_orders = []
    for wholesaler, items_list in grouped.items():
        order = WholesaleOrder.objects.create(
            retailer=request.user,
            wholesaler=wholesaler,
            status=WholesaleOrder.OrderStatus.PENDING,
            payment_mode=(WholesaleOrder.PaymentMode.ONLINE if payment_mode == "Online" else WholesaleOrder.PaymentMode.CASH_ON_DELIVERY),
            payment_status=WholesaleOrder.PaymentStatus.PENDING,
            addr_state=addr_state or None,
            addr_district=addr_district or None,
            addr_colony=addr_colony or None,
            addr_pincode=addr_pincode or None,
            addr_road_number=addr_road_number or None,
            addr_house_number=addr_house_number or None,
        )
        for it in items_list:
            WholesaleOrderItem.objects.create(
                order=order,
                product=it.product,
                quantity=int(getattr(it, "quantity", 0) or 0),
                price=Decimal(str(getattr(it.product, "price", 0.0) or 0.0)),
            )
        created_orders.append(order)

    if payment_mode == "Cash on Delivery":
        _fulfil_wholesale_and_clear_cart(created_orders, request)
        return render(request, "orders/checkout_success.html", {"order": created_orders[0] if created_orders else None})

    try:
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    except AttributeError:
        return HttpResponseBadRequest("Razorpay keys not configured in settings.")

    razorpay_order = client.order.create({
        "amount": int(cart_total_price * 100),
        "currency": "INR",
        "payment_capture": 1,
        "notes": {
            "retailer_email": request.user.email or "",
            "wholesale_orders": ",".join(str(o.id) for o in created_orders),
        }
    })

    for o in created_orders:
        o.razorpay_order_id = razorpay_order.get("id")
        o.save(update_fields=["razorpay_order_id"])

    return render(
        request,
        "orders/payment_razorpay.html",
        {
            "order": created_orders[0] if created_orders else None,
            "items": w_items,
            "cart_total_price": cart_total_price,
            "razorpay_key_id": settings.RAZORPAY_KEY_ID,
            "razorpay_order_id": razorpay_order.get("id"),
            "amount": int(cart_total_price * 100),
            "currency": "INR",
            "verify_url": reverse("wholesale:razorpay_verify"),
            "back_to_checkout_url": reverse("wholesale:checkout"),
            "payer_email": request.user.email or "",
        },
    )

@transaction.atomic
def _fulfil_wholesale_and_clear_cart(orders, request):
    cart = get_or_create_cart(request)
    try:
        for order in orders:
            items = WholesaleOrderItem.objects.filter(order=order).select_related("product").all()
            for it in items:
                prod = getattr(it, "product", None)
                if not prod:
                    continue
                qty = int(getattr(it, "quantity", 0) or 0)
                if prod.stock_quantity < qty:
                    qty = prod.stock_quantity
                prod.stock_quantity = max(0, prod.stock_quantity - qty)
                prod.save(update_fields=["stock_quantity"])
        cart.wholesale_items.all().delete()
    except Exception:
        pass

@csrf_exempt
@transaction.atomic
def wholesale_razorpay_verify(request):
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

    base_order = get_object_or_404(WholesaleOrder, id=order_id)

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        qs = WholesaleOrder.objects.filter(razorpay_order_id=razorpay_order_id, retailer=base_order.retailer)
        for o in qs:
            o.payment_status = WholesaleOrder.PaymentStatus.FAILED
            o.save(update_fields=["payment_status"])
        return JsonResponse({"ok": False, "error": "Signature verification failed"}, status=400)

    related_orders = list(WholesaleOrder.objects.filter(razorpay_order_id=razorpay_order_id, retailer=base_order.retailer))
    for o in related_orders:
        o.razorpay_payment_id = razorpay_payment_id
        o.razorpay_signature = razorpay_signature
        o.payment_status = WholesaleOrder.PaymentStatus.PAID
        o.save(update_fields=["razorpay_payment_id", "razorpay_signature", "payment_status"])

    _fulfil_wholesale_and_clear_cart(related_orders, request)

    return JsonResponse({
        "ok": True,
        "redirect_url": reverse("wholesale:order_success", args=[base_order.id]),
    })

@login_required
def wholesale_order_success(request, order_id):
    order = get_object_or_404(WholesaleOrder, id=order_id)
    if not (request.user == getattr(order, "retailer", None) or request.user == getattr(order, "wholesaler", None)):
        return HttpResponseBadRequest("You are not allowed to view this order.")
    return render(request, "orders/checkout_success.html", {"order": order})


@login_required
def wholesale_order_history(request):
    if not request.user.is_retailer:
        return HttpResponseForbidden("Only retailers can view wholesale orders.")

    days = getattr(settings, "ORDER_ESTIMATED_DAYS", 5)

    search_query = (request.GET.get("q") or "").strip()

    orders_qs = (
        WholesaleOrder.objects
        .filter(retailer=request.user)
        .order_by("-created_at")
        .prefetch_related("items__product", "items__product__category")
    )

    if search_query:
        orders_qs = orders_qs.filter(items__product__name__icontains=search_query).distinct()

    orders_data = []
    for order in orders_qs:
        total = Decimal("0.00")
        first_img = None
        first_item_name = None
        item_count = 0
        item_names = []

        for it in order.items.select_related("product").all():
            item_count += 1
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
                img_url = getattr(prod, "image_url", None)
                if img_url:
                    first_img = img_url
                first_item_name = getattr(prod, "name", None) or first_item_name

            if not first_item_name and getattr(it, "product", None):
                first_item_name = getattr(it.product, "name", None) or first_item_name

            name_val = None
            if prod is not None:
                name_val = getattr(prod, "name", None)
            if name_val:
                item_names.append(str(name_val))


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
            "display_payment_status": display_status or ("COMPLETED" if getattr(order, "status", None) == getattr(order, "OrderStatus", type("", (), {})).COMPLETED else getattr(order, "payment_status", None)),
            "status": getattr(order, "status", None),
            "thumbnail": first_img,
            "first_item_name": first_item_name,
            "first_product_id": None,
            "item_count": item_count,
            "item_names": item_names_str,
        })

    return render(
        request,
        "orders/order_history.html",
        {
            "orders": orders_data,
            "search_query": search_query,
            "order_history_action_url": reverse("wholesale:order_history"),
            "order_detail_url_name": "wholesale:order_detail",
        },
    )


@login_required
def wholesale_order_detail(request, order_id):
    order = get_object_or_404(WholesaleOrder, id=order_id)
    if not (request.user == getattr(order, "retailer", None) or request.user == getattr(order, "wholesaler", None)):
        return HttpResponseBadRequest("You are not allowed to view this order.")

    days = getattr(settings, "ORDER_ESTIMATED_DAYS", 5)
    items_qs = order.items.select_related("product__category").all()

    items = []
    order_total = Decimal("0.00")
    title_names = []

    for it in items_qs:
        prod = getattr(it, "product", None)
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

        include_item = False
        if prod is not None:
            prod_wh = getattr(prod, "wholesaler", None)
            if prod_wh == request.user or prod_wh == getattr(order, "wholesaler", None):
                include_item = True

        if include_item:
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
            })

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        next_stage = None
        stage_map = {
            "placed": 1,
            "dispatched": 2,
            "facility": 3,
            "out_for_delivery": 4,
            "mark_arrived": 5,
        }
        if action in stage_map:
            next_stage = stage_map[action]
        # seller controls
        if request.user.is_wholesaler and order.wholesaler == request.user and next_stage in [1,2,3,4] and next_stage == getattr(order, "progress_stage", 0) + 1:
            order.progress_stage = next_stage
            order.save(update_fields=["progress_stage"])
            return redirect("wholesale:order_detail", order.id)
        if request.user.is_wholesaler and order.wholesaler == request.user and action == "cancel" and getattr(order, "progress_stage", 0) == 0:
            order.progress_stage = 0
            order.arrived_at = None
            order.status = getattr(order.OrderStatus, "CANCELLED", order.status)
            order.save(update_fields=["progress_stage", "arrived_at", "status"])
            return redirect("wholesale:order_detail", order.id)
        # buyer arrival
        if request.user.is_retailer and order.retailer == request.user and next_stage == 5 and getattr(order, "progress_stage", 0) >= 4 and not getattr(order, "arrived_at", None):
            from datetime import datetime
            from django.conf import settings as dj_settings
            from datetime import timezone as dt_tz
            order.progress_stage = 5
            order.arrived_at = datetime.now(dt_tz.utc if getattr(dj_settings, 'USE_TZ', True) else None)
            order.status = getattr(order.OrderStatus, "COMPLETED", order.status)
            if hasattr(order, "payment_status"):
                order.payment_status = getattr(order.PaymentStatus, "PAID", None) or "PAID"
            order.save(update_fields=["progress_stage", "arrived_at", "status", "payment_status"])
            return redirect("wholesale:order_detail", order.id)
        if request.user.is_retailer and order.retailer == request.user and action == "cancel" and getattr(order, "progress_stage", 0) >= 4 and not getattr(order, "arrived_at", None):
            order.progress_stage = 0
            order.arrived_at = None
            order.status = getattr(order.OrderStatus, "CANCELLED", order.status)
            order.save(update_fields=["progress_stage", "arrived_at", "status"])
            return redirect("wholesale:order_detail", order.id)

    return render(
        request,
        "orders/order_detail.html",
        {
            "order": order,
            "items": items,
            "order_total": order_total,
            "order_title_names": ", ".join(list(dict.fromkeys(title_names))[:3]) + (", and more" if len(list(dict.fromkeys(title_names))) > 3 else ""),
            "hide_global_search": True,
            "can_progress_control": request.user.is_wholesaler and order.wholesaler == request.user,
            "can_buyer_mark_arrived": request.user.is_retailer and order.retailer == request.user and getattr(order, "progress_stage", 0) >= 4 and not getattr(order, "arrived_at", None),
            "order_progress_action_url": request.path,
            "order_display_payment_status": ("REFUND INITIATED" if (getattr(order, "status", None) == getattr(order, "OrderStatus", type("", (), {})).CANCELLED and getattr(order, "payment_mode", "") == "Online" and getattr(order, "payment_status", "") == "PAID") else ("CANCELLED" if getattr(order, "status", None) == getattr(order, "OrderStatus", type("", (), {})).CANCELLED else (getattr(order, "payment_status", None) or ""))),
        },
    )


@login_required
def ordered_by_list(request):
    if not request.user.is_wholesaler:
        return HttpResponseForbidden("Only wholesalers can view orders received.")

    days = getattr(settings, "ORDER_ESTIMATED_DAYS", 5)
    raw_q = (request.GET.get("q") or "")
    search_query = re.sub(r"[()\[\]{}]", "", raw_q).strip()

    orders_qs = (
        WholesaleOrder.objects
        .filter(wholesaler=request.user)
        .order_by("-created_at")
        .prefetch_related("items__product", "retailer")
    )

    if search_query:
        orders_qs = orders_qs.filter(
            Q(retailer__full_name__icontains=search_query) |
            Q(retailer__email__icontains=search_query)
        ).order_by("-created_at").distinct()

    orders_data = []
    for order in orders_qs:
        total = Decimal("0.00")
        qty_total = 0
        first_img = None
        first_item_name = None
        item_names = []
        for it in order.items.select_related("product").all():
            try:
                price = Decimal(str(getattr(it, "price", 0) or 0))
            except Exception:
                price = Decimal("0.00")
            try:
                qty = int(getattr(it, "quantity", 0) or 0)
            except Exception:
                qty = 0
            prod = getattr(it, "product", None)
            prod_wh = getattr(prod, "wholesaler", None)
            if prod_wh == request.user:
                total += price * qty
                qty_total += qty
                if prod is not None:
                    nm = getattr(prod, "name", None)
                    if nm:
                        item_names.append(str(nm))
                    if not first_img:
                        img_url = getattr(prod, "image_url", None)
                        if img_url:
                            first_img = img_url
                            first_item_name = nm

        retailer = getattr(order, "retailer", None)
        retailer_name = None
        if retailer is not None:
            retailer_name = getattr(retailer, "full_name", None) or getattr(retailer, "get_full_name", lambda: None)() or getattr(retailer, "username", None) or getattr(retailer, "email", None)

        orders_data.append({
            "id": order.id,
            "created_at": order.created_at,
            "total": total,
            "payment_status": getattr(order, "payment_status", None),
            "display_payment_status": ("COMPLETED" if getattr(order, "status", None) == getattr(order, "OrderStatus", type("", (), {})).COMPLETED else getattr(order, "payment_status", None)),
            "status": getattr(order, "status", None),
            "thumbnail": first_img,
            "first_item_name": first_item_name,
            "first_product_id": None,
            "item_count": qty_total,
            "retailer_name": retailer_name,
            "item_names": ", ".join(list(dict.fromkeys(item_names))[:3]) + (", and more" if len(list(dict.fromkeys(item_names))) > 3 else "") if item_names else None,
        })

    return render(
        request,
        "orders/order_history.html",
        {
            "orders": orders_data,
            "search_query": search_query,
            "order_history_action_url": reverse("wholesale:ordered_by"),
            "order_detail_url_name": "wholesale:order_detail",
            "page_title": "Ordered By",
            "ordered_by_mode": True,
            "search_placeholder": "Search by retailer name",
            "hide_global_search": True,
            "empty_message": "No orders received yet.",
        },
    )
