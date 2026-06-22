from django.contrib import admin
from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    """
    Allows viewing and editing OrderItems from within the Order admin page.
    """
    model = OrderItem
    raw_id_fields = ["product"] # Use a search widget for products
    extra = 0 # Don't show extra blank forms

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("id", "customer__email", "customer__full_name")
    inlines = [OrderItemInline] # Add the inline items