from django.urls import path
from . import views

app_name = "wholesale"

urlpatterns = [
    # Wholesaler's own product management dashboard
    path("dashboard/", views.wholesaler_dashboard, name="wholesaler_dashboard"),
    
    # Handle product deletion
    path("product/delete/<int:product_id>/", views.delete_wholesale_product, name="delete_product"),
    
    # Retailers placing orders for wholesale products
    path("order/<int:product_id>/", views.order_product, name="order_product"),
    # Retailer add wholesale product to cart (AJAX)
    path("cart/add/<int:product_id>/", views.add_wholesale_to_cart, name="cart_add"),
    # Retailer checkout for wholesale items
    path("checkout/", views.retailer_checkout, name="checkout"),
    path("razorpay/verify/", views.wholesale_razorpay_verify, name="razorpay_verify"),
    path("success/<int:order_id>/", views.wholesale_order_success, name="order_success"),
    path("history/", views.wholesale_order_history, name="order_history"),
    path("details/<int:order_id>/", views.wholesale_order_detail, name="order_detail"),
    path("ordered-by/", views.ordered_by_list, name="ordered_by"),
    
    # We will add URLs for retailers to browse/order
]