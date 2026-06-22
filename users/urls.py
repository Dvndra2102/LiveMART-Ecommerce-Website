from django.urls import path
from . import views

app_name = "users"

urlpatterns = [
    path("queries/", views.queries_page, name="queries"),
    path("change-credentials/", views.change_credentials, name="change_credentials"),
]
