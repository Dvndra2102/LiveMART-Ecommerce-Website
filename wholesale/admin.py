from django.contrib import admin
from .models import WholesaleProduct, WholesaleOrder, WholesaleOrderItem

@admin.register(WholesaleProduct)
class WholesaleProductAdmin(admin.ModelAdmin):
    list_display = ("name", "wholesaler", "category", "price", "stock_quantity", "is_available")
    list_filter = ("is_available", "category", "wholesaler")
    search_fields = ("name", "wholesaler__email", "wholesaler__full_name")
    list_editable = ("price", "stock_quantity", "is_available")
    autocomplete_fields = ("wholesaler", "category")

class WholesaleOrderItemInline(admin.TabularInline):
    model = WholesaleOrderItem
    raw_id_fields = ["product"]
    extra = 0

@admin.register(WholesaleOrder)
class WholesaleOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "retailer", "wholesaler", "status", "created_at")
    list_filter = ("status", "created_at", "wholesaler", "retailer")
    search_fields = ("id", "retailer__full_name", "wholesaler__full_name")
    inlines = [WholesaleOrderItemInline]
