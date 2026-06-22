from django.db import models
from django.conf import settings
from store.models import Category, Cart

class WholesaleProduct(models.Model):
    """
    A product sold by a Wholesaler to a Retailer.
    """
    wholesaler = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wholesale_products",
        limit_choices_to={"role": "WHOLESALER"}
    )
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name="wholesale_products")
    
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price per unit/case")
    stock_quantity = models.PositiveIntegerField(help_text="Available units/cases")
    is_available = models.BooleanField(default=True)
    image_url = models.URLField(max_length=1024, blank=True, null=True)

    def __str__(self):
        return f"{self.name} (Wholesaler: {self.wholesaler.full_name})"

class WholesaleOrder(models.Model):
    """
    An order placed by a Retailer to a Wholesaler.
    """
    class OrderStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        SHIPPED = "SHIPPED", "Shipped"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"

    # Progress tracking (0: Pending, 1: Placed, 2: Dispatched, 3: Facility, 4: Out for delivery, 5: Arrived)
    progress_stage = models.IntegerField(default=0)
    arrived_at = models.DateTimeField(null=True, blank=True)

    class PaymentMode(models.TextChoices):
        ONLINE = "Online", "Online"
        CASH_ON_DELIVERY = "Cash on Delivery", "Cash on Delivery"

    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"

    retailer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="wholesale_orders_placed",
        limit_choices_to={"role": "RETAILER"}
    )
    wholesaler = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="wholesale_orders_received",
        limit_choices_to={"role": "WHOLESALER"}
    )
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Payment and shipment address
    payment_mode = models.CharField(max_length=20, choices=PaymentMode.choices, default=PaymentMode.CASH_ON_DELIVERY)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)

    addr_state = models.CharField(max_length=100, blank=True, null=True)
    addr_district = models.CharField(max_length=100, blank=True, null=True)
    addr_colony = models.CharField(max_length=150, blank=True, null=True)
    addr_pincode = models.CharField(max_length=12, blank=True, null=True)
    addr_road_number = models.CharField(max_length=50, blank=True, null=True)
    addr_house_number = models.CharField(max_length=50, blank=True, null=True)

    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    
    def __str__(self):
        return f"Order {self.id} from {self.retailer} to {self.wholesaler}"

    def save(self, *args, **kwargs):
        if self.status == self.OrderStatus.COMPLETED:
            try:
                if self.payment_status != self.PaymentStatus.PAID:
                    self.payment_status = self.PaymentStatus.PAID
            except Exception:
                self.payment_status = "PAID"
        super().save(*args, **kwargs)

class WholesaleOrderItem(models.Model):
    order = models.ForeignKey(WholesaleOrder, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(WholesaleProduct, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2, help_text="Price at time of order")

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

class WholesaleCartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="wholesale_items")
    product = models.ForeignKey(WholesaleProduct, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("cart", "product")

    def __str__(self):
        return f"{self.quantity} × {self.product.name} (Wholesale)"
