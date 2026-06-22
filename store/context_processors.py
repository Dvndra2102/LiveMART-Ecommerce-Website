# store/context_processors.py
from typing import Dict, Any, List
from store.utils import get_or_create_cart

def _build_cart_snapshot(request) -> Dict[str, Any]:
    snapshot = {"cart_total_items": 0, "cart_total_price": 0.0, "cart_items": []}
    try:
        cart = get_or_create_cart(request)
    except Exception:
        return snapshot

    try:
        total = getattr(cart, "total_items", None)
        if total is None:
            items_qs = getattr(cart, "items", None)
            if items_qs is not None:
                try:
                    snapshot["cart_total_items"] = int(sum(int(getattr(i, "quantity", 0) or 0) for i in items_qs.all()))
                except Exception:
                    snapshot["cart_total_items"] = int(sum(int(getattr(i, "quantity", 0) or 0) for i in items_qs))
            else:
                snapshot["cart_total_items"] = 0
        else:
            snapshot["cart_total_items"] = int(total or 0)
    except Exception:
        snapshot["cart_total_items"] = 0

    total_price = 0.0
    items_list: List[Dict[str, Any]] = []
    try:
        items_qs = getattr(cart, "items", None)
        if items_qs is not None:
            try:
                iterator = items_qs.all()
            except Exception:
                iterator = items_qs
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
                                image_url = prod.get_image_url()
                            except Exception:
                                image_url = ""
                except Exception:
                    image_url = ""

                title = ""
                try:
                    title = str(
                        getattr(item.product, "name", None)
                        or getattr(item.product, "title", None)
                        or getattr(item, "name", "")
                        or ""
                    )
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
    except Exception:
        items_list = []

    snapshot["cart_items"] = items_list
    snapshot["cart_total_price"] = float(total_price or 0.0)
    return snapshot

def cart_counts(request) -> Dict[str, object]:
    snap = _build_cart_snapshot(request)
    return {
        "cart_total_items": snap.get("cart_total_items", 0),
        "cart_total_price": snap.get("cart_total_price", 0.0),
        "cart_items": snap.get("cart_items", []),
    }