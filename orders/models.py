from django.db import models
from django.conf import settings
from store.models import Product


class Order(models.Model):
    """
    A customer's order containing one or multiple items.
    """

    # Order progress status
    class OrderStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SHIPPED = "SHIPPED", "Shipped"
        DELIVERED = "DELIVERED", "Delivered"
        CANCELLED = "CANCELLED", "Cancelled"

    # Progress tracking (0: Pending, 1: Placed, 2: Dispatched, 3: Facility, 4: Out for delivery, 5: Arrived)
    progress_stage = models.IntegerField(default=0)
    arrived_at = models.DateTimeField(null=True, blank=True)

    # Payment method chosen at checkout
    class PaymentMode(models.TextChoices):
        ONLINE = "Online", "Online"
        CASH_ON_DELIVERY = "Cash on Delivery", "Cash on Delivery"

    # Payment result
    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        FAILED = "FAILED", "Failed"

    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="orders",
        limit_choices_to={"role": "CUSTOMER"},
    )

    status = models.CharField(
        max_length=20,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
    )

    payment_mode = models.CharField(
        max_length=20,
        choices=PaymentMode.choices,
        default=PaymentMode.CASH_ON_DELIVERY,
    )

    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )

    # Shipment address (captured at checkout)
    addr_state = models.CharField(max_length=100, blank=True, null=True)
    addr_district = models.CharField(max_length=100, blank=True, null=True)
    addr_colony = models.CharField(max_length=150, blank=True, null=True)
    addr_pincode = models.CharField(max_length=12, blank=True, null=True)
    addr_road_number = models.CharField(max_length=50, blank=True, null=True)
    addr_house_number = models.CharField(max_length=50, blank=True, null=True)

    # Razorpay identifiers (optional but recommended for tracking)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        customer_email = self.customer.email if self.customer else "unknown"
        return f"Order {self.id} by {customer_email}"


class OrderItem(models.Model):
    """
    Individual product entry within an Order.
    """

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items"
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.SET_NULL,
        null=True
    )
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Price at time of purchase"
    )

    def __str__(self):
        product_name = self.product.name if self.product else "Unknown product"
        return f"{self.quantity} x {product_name}"


class OrderFeedback(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="feedbacks")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    text = models.TextField()
    reply_text = models.TextField(blank=True, null=True)
    reply_at = models.DateTimeField(blank=True, null=True)
    reply_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="retailer_replies")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Feedback by {getattr(self.customer, 'email', 'unknown')} on {getattr(self.product, 'id', '-') }"
