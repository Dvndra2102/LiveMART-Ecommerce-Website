"""
URL configuration for livemart project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from users.views import DashboardRedirectView # Our custom router
from store.views import landing_page # Our landing page

urlpatterns = [
    path("admin/", admin.site.urls),

    # 1. Allauth URLs for login, logout, password reset, and Google OAuth
    path("accounts/", include("allauth.urls")),

    # 2. Our custom landing page
    path("", landing_page, name="landing_page"),

    # 3. Our custom dashboard redirector
    # This view will check the user's role and send them to the right place
    path("dashboard/", DashboardRedirectView.as_view(), name="dashboard_redirect"),

    # 4. Include app-specific URLs
    path("users/", include("users.urls")),
    path("store/", include("store.urls")),
    path("orders/", include("orders.urls")),
    path("wholesale/", include("wholesale.urls")),
]