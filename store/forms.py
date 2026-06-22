from django import forms
from .models import Product, Category

class ProductForm(forms.ModelForm):
    """
    Form for adding/editing a Product from the retailer dashboard.
    Matches f6.png.
    """
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        empty_label="Select category",
        widget=forms.Select(attrs={"class": "w-full border rounded-md p-2"})
    )
    
    class Meta:
        model = Product
        fields = ["name", "description", "price", "stock_quantity", "image_url", "is_available", "category"]
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Fresh Milk"}),
            "description": forms.Textarea(attrs={"rows": 4, "placeholder": "Product details..."}),
            "price": forms.NumberInput(attrs={"placeholder": "e.g. 12.00"}),
            "stock_quantity": forms.NumberInput(attrs={"placeholder": "e.g. 100"}),
            "image_url": forms.URLInput(attrs={"placeholder": "https://example.com/image.png"}),
            "is_available": forms.CheckboxInput(attrs={"class": "toggle-switch"}), # We will style this
        }
    
    # Rename 'name' to 'Product Name' for the label
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].label = "Product Name"
        self.fields['price'].label = "Price (₹)"
        self.fields['stock_quantity'].label = "Stock Quantity"
        self.fields['image_url'].label = "Image URL"
        self.fields['is_available'].label = "Available for sale"