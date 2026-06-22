from django.contrib import admin
from .models import Category, Product

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",) # <-- ADD THIS LINE

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "retailer", "category", "price", "stock_quantity", "is_available")
    list_filter = ("is_available", "category", "retailer")
    search_fields = ("name", "retailer__email", "retailer__full_name")
    list_editable = ("price", "stock_quantity", "is_available")
    autocomplete_fields = ("retailer", "category") # Makes search easier