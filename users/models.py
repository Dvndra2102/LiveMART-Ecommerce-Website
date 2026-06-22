from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models

class UserManager(BaseUserManager):
    """
    Custom user manager where email is the unique identifier
    instead of usernames.
    """
    def create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("The Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save()
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", User.Role.ADMIN) # Superusers are Admins

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """
    Custom User Model based on the requirements.
    """
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        RETAILER = "RETAILER", "Retailer"
        WHOLESALER = "WHOLESALER", "Wholesaler"
        ADMIN = "ADMIN", "Admin" # For superusers

    # We don't need a username
    username = None
    
    # We use full_name as seen in f4.png
    full_name = models.CharField(max_length=255)
    email = models.EmailField("email address", unique=True)
    
    role = models.CharField(max_length=50, choices=Role.choices)
    pincode = models.CharField(max_length=10, blank=True, null=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"] # Required for createsuperuser

    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_retailer(self):
        return self.role == self.Role.RETAILER

    @property
    def is_wholesaler(self):
        return self.role == self.Role.WHOLESALER