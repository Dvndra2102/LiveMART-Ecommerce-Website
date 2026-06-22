from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User

class CustomUserAdmin(UserAdmin):
    """
    Configure the admin page for the custom User model.
    """
    model = User
    # Use the same fieldsets as UserAdmin, but replace 'username'
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("full_name", "pincode", "role")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    list_display = ("email", "full_name", "role", "pincode", "is_staff")
    search_fields = ("email", "full_name", "pincode")
    list_filter = ("role", "is_staff", "is_superuser")
    ordering = ("email",)
    
    # We don't have a username, so remove it from fields
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'full_name', 'role', 'pincode', 'password'),
        }),
    )


# Register the custom User model with its custom admin
admin.site.register(User, CustomUserAdmin)