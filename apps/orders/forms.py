from django import forms
from .models import Order, OrderRequirement

class CheckoutForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ['shipping_name', 'shipping_phone', 'shipping_address', 'shipping_city', 'shipping_state', 'customer_notes']
        widgets = {
            'shipping_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Recipient Full Name'}),
            'shipping_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 800 000 0000'}),
            'shipping_address': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'Delivery Street Address / Suite / Office'}),
            'shipping_city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City (e.g. Ikeja, Abuja, Port Harcourt)'}),
            'shipping_state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State (e.g. Lagos, FCT)'}),
            'customer_notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 2, 'placeholder': 'Any custom engraving instructions or delivery notes...'}),
        }


class OrderRequirementForm(forms.ModelForm):
    PAGES_CHOICES = (
        ('home', 'Home'),
        ('about', 'About Us / Bio'),
        ('services', 'Services'),
        ('products', 'Product Showcase / Catalog'),
        ('gallery', 'Gallery / Portfolio'),
        ('contact', 'Contact Page & WhatsApp Integration'),
        ('pricing', 'Pricing Table'),
    )

    class Meta:
        model = OrderRequirement
        fields = [
            'full_name', 'title', 'bio',
            'business_name', 'business_category', 'business_description',
            'phone', 'whatsapp', 'email', 'address',
            'social_instagram', 'social_linkedin', 'social_x', 'social_tiktok', 'social_facebook', 'website_url',
            'website_type', 'pages_needed', 'design_notes'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name for Card/Website'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Chief Executive Officer'}),
            'bio': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Your bio or statement'}),
            'business_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company or Brand Name'}),
            'business_category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Textile, Tech, Real Estate, Fashion'}),
            'business_description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Detailed business description'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 800 000 0000'}),
            'whatsapp': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 800 000 0000 (WhatsApp)'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'official@business.com'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Physical Business Address'}),
            'social_instagram': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Instagram link or @handle'}),
            'social_linkedin': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'LinkedIn profile link'}),
            'social_x': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'X (Twitter) handle'}),
            'social_tiktok': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'TikTok link'}),
            'social_facebook': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Facebook Page link'}),
            'website_url': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Existing website (if any)'}),
            'website_type': forms.Select(choices=[('personal', 'Personal Website'), ('business', 'Business Website'), ('none', 'Card Only (No Website)')], attrs={'class': 'form-select'}),
            'pages_needed': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Home, About, Services, Products, Contact'}),
            'design_notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Specific branding colors, font preferences, or references...'}),
        }
