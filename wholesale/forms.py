from django import forms
from .models import WholesaleProduct
from store.models import Category # Reuse Category model

class WholesaleProductForm(forms.ModelForm):
    """
    Form for adding/editing a WholesaleProduct from the dashboard.
    """
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        empty_label="Select category",
        widget=forms.Select(attrs={"class": "w-full border rounded-md p-2"})
    )
    
    class Meta:
        model = WholesaleProduct
        fields = ["name", "description", "price", "stock_quantity", "image_url", "is_available", "category"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Bulk Milk Crates"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Product details..."}),
            "price": forms.NumberInput(attrs={"placeholder": "e.g. 500.00"}),
            "stock_quantity": forms.NumberInput(attrs={"placeholder": "e.g. 50"}),
            "image_url": forms.URLInput(attrs={"placeholder": "https://example.com/image.png"}),
            "is_available": forms.CheckboxInput(attrs={"class": "toggle-switch"}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].label = "Product Name"
        self.fields['price'].label = "Price (₹ per case/unit)"
        self.fields['stock_quantity'].label = "Stock Quantity (cases/units)"
        self.fields['image_url'].label = "Image URL"
        self.fields['is_available'].label = "Available for sale"