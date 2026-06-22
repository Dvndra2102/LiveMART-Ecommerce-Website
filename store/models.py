from django.db import models
from django.conf import settings # To link to our custom User model

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name

class Product(models.Model):
    """
    A product sold by a Retailer.
    This model maps to the fields in f6.png.
    """
    retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="products",
        limit_choices_to={"role": "RETAILER"} # Ensure only retailers can be linked
    )
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="products")
    
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock_quantity = models.PositiveIntegerField()
    image_url = models.URLField(max_length=1024, blank=True, null=True)
    is_available = models.BooleanField(default=True, verbose_name="Available for sale")
    is_proxy = models.BooleanField(default=False)
    proxy_wholesale_product = models.ForeignKey(
        'wholesale.WholesaleProduct',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='proxied_products'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.name
    

class Cart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="carts")
    session_key = models.CharField(max_length=40, null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart #{self.pk} ({self.user or self.session_key})"

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def total_price(self):
        return sum(item.quantity * item.product.price for item in self.items.all())


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey('store.Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cart", "product")

    def __str__(self):
        return f"{self.quantity} × {self.product.name}"
