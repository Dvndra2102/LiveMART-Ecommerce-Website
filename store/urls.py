from django.urls import path
from . import views

app_name = "store"

urlpatterns = [
    # Retailer Dashboard
    path("dashboard/", views.retailer_dashboard, name="retailer_dashboard"),
    path("ordered-by/", views.retailer_ordered_by, name="ordered_by_retailer"),
    path("ordered-by/details/<int:order_id>/", views.retailer_order_detail, name="retailer_order_detail"),
    
    # Handle product deletion
    path("product/delete/<int:product_id>/", views.delete_product, name="delete_product"),
    
    # Customer Dashboard (Product List)
    path("products/", views.customer_product_list, name="product_list"),
    path("products/<int:product_id>/", views.product_detail, name="product_detail"),
    path("cart/add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("cart/update/<int:item_id>/", views.update_cart_item, name="update_cart_item"),
    path("cart/", views.view_cart, name="view_cart"),
    path("cart/summary/", views.cart_summary_json, name="cart_summary"),
    path("alerts/", views.alerts, name="alerts"),
    # Proxy availability
    path("proxy/add/<int:wprod_id>/", views.proxy_add, name="proxy_add"),
    path("proxy/remove/<int:wprod_id>/", views.proxy_remove, name="proxy_remove"),
    path("proxy/remove/by-product/<int:product_id>/", views.proxy_remove_by_product, name="proxy_remove_by_product"),
]
