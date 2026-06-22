from django import forms
from allauth.account.forms import SignupForm, LoginForm
from django.contrib.auth import authenticate
from .models import User
import re

INPUT_CLASS = (
    "mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm "
    "placeholder-gray-400 focus:outline-none focus:ring-cyan-500 focus:border-cyan-500 sm:text-sm"
)

class CustomSignupForm(SignupForm):
    # explicitly add password fields
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput,
        required=True,
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput,
        required=True,
    )

    full_name = forms.CharField(label="Full name", max_length=255, required=True)

    role = forms.ChoiceField(
        choices=[
            (User.Role.CUSTOMER, "I am a Customer"),
            (User.Role.RETAILER, "I am a Retailer"),
            (User.Role.WHOLESALER, "I am a Wholesaler"),
        ],
        widget=forms.RadioSelect,
        label="I am a",
        required=True,
    )

    pincode = forms.CharField(
        label="Pincode",
        required=False,
        help_text="Required if you are a Retailer or Wholesaler.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Add classes/placeholder to all input fields
        for name, field in self.fields.items():
            widget = field.widget
            if not isinstance(widget, forms.RadioSelect):
                widget.attrs["class"] = INPUT_CLASS

            if name == "email":
                widget.attrs.setdefault("placeholder", "Email address")
            if name == "full_name":
                widget.attrs.setdefault("placeholder", "Full name")
            if name == "pincode":
                widget.attrs.setdefault("placeholder", "Pincode (if applicable)")
            if name == "password1":
                widget.attrs.setdefault("placeholder", "Password")
            if name == "password2":
                widget.attrs.setdefault("placeholder", "Confirm password")

    def clean(self):
        cleaned = super().clean()

        # Check password match
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")

        # Check pincode requirement
        role = cleaned.get("role")
        pincode = cleaned.get("pincode")
        if role in (User.Role.RETAILER, User.Role.WHOLESALER) and not pincode:
            self.add_error("pincode", "Pincode is required for Retailers and Wholesalers.")

        return cleaned

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email:
            return email
        e = str(email).strip().lower()
        allowed = (
            e.endswith("@gmail.com") or e.endswith("@yahoo.com") or e.endswith("@outlook.com")
        )
        if not allowed:
            raise forms.ValidationError("Use a valid email ID")
        if e.endswith("@gmail.com"):
            local = e.split("@", 1)[0]
            if local.startswith(".") or local.endswith(".") or ".." in local:
                raise forms.ValidationError("Use a valid email ID")
            if not re.fullmatch(r"[a-z0-9][a-z0-9._+\-]{0,62}[a-z0-9]", local):
                raise forms.ValidationError("Use a valid email ID")
        return email

    def signup(self, request, user):
        user.full_name = self.cleaned_data.get("full_name")
        user.role = self.cleaned_data.get("role")
        user.pincode = self.cleaned_data.get("pincode")
        user.save()
        return user

class CustomLoginForm(LoginForm):
    def clean(self):
        cleaned_data = super().clean()
        login = cleaned_data.get("login")
        password = self.data.get("password")
        
        if login:
            lv = str(login).strip().lower()
            allowed = (
                lv.endswith("@gmail.com") or lv.endswith("@yahoo.com") or lv.endswith("@outlook.com")
            )
            if not allowed:
                self.add_error("login", "Invalid EMail ID entered.")
                return cleaned_data

        if login and password:
            print(f"DEBUG: CustomLoginForm checking user: {login}")
            # Explicitly authenticate to verify password
            user = authenticate(self.request, email=login, password=password)
            print(f"DEBUG: authenticate returned: {user}")
            if not user:
                print("DEBUG: Authentication failed")
                raise forms.ValidationError("Wrong Password or EMail ID")
        return cleaned_data


class ChangeCredentialsForm(forms.Form):
    full_name = forms.CharField(label="Username", max_length=255, required=True)
    pincode = forms.CharField(label="Pincode", max_length=10, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            widget.attrs.setdefault("class", INPUT_CLASS)
            if name == "full_name":
                widget.attrs.setdefault("placeholder", "Username")
            if name == "pincode":
                widget.attrs.setdefault("placeholder", "Pincode")

    def clean_pincode(self):
        p = self.cleaned_data.get("pincode")
        if not p:
            return p
        s = str(p).strip()
        if not re.fullmatch(r"[0-9]{4,10}", s):
            raise forms.ValidationError("Enter a valid pincode")
        return s
