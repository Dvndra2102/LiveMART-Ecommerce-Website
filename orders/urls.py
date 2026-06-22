from django.urls import path
from . import views

app_name = "orders"

urlpatterns = [
    path("cart/", views.view_cart, name="view_cart"),
    path("add/<int:product_id>/", views.add_to_cart, name="add_to_cart"),
    path("checkout/", views.checkout, name="checkout"),
    path("razorpay/verify/", views.razorpay_verify, name="razorpay_verify"),
    path("success/<int:order_id>/", views.order_success, name="order_success"),
    path("history/", views.order_history, name="order_history"),
    path("details/<int:order_id>/", views.order_detail, name="order_detail"),
    path("feedback/<int:order_id>/", views.give_feedback, name="give_feedback"),
]
