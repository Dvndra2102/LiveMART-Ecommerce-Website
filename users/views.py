from django.shortcuts import redirect
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import User
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from .forms import ChangeCredentialsForm

class DashboardRedirectView(LoginRequiredMixin, View):
    """
    Redirects users to their appropriate dashboard based on their role.
    This is the view mapped to LOGIN_REDIRECT_URL.
    """
    def get(self, request, *args, **kwargs):
        user = request.user
        
        if user.is_retailer:
            return redirect("store:retailer_dashboard")
        elif user.is_wholesaler:
            return redirect("wholesale:wholesaler_dashboard")
        elif user.is_customer:
            return redirect("store:product_list")
        else:
            # Fallback for admins or other roles
            return redirect("admin:index")

# We don't need many other views here, as allauth and app-specific
# views will handle the rest.

@login_required
def queries_page(request):
    return render(request, "users/queries.html", {"email": "livemartstore@gmail.com"})


@login_required
@require_http_methods(["GET", "POST"])
def change_credentials(request):
    user = request.user
    if request.method == "POST":
        form = ChangeCredentialsForm(request.POST)
        if form.is_valid():
            user.full_name = form.cleaned_data["full_name"]
            user.pincode = form.cleaned_data.get("pincode") or None
            user.save()
            messages.success(request, "Credentials updated")
            return redirect("dashboard_redirect")
    else:
        form = ChangeCredentialsForm(initial={
            "full_name": user.full_name,
            "pincode": user.pincode or "",
        })
    return render(request, "users/change_credentials.html", {"form": form})
