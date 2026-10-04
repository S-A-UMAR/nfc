from django import forms
from .models import WebsiteChangeRequest

class WebsiteChangeRequestForm(forms.ModelForm):
    class Meta:
        model = WebsiteChangeRequest
        fields = ['subject', 'message']
        widgets = {
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Update pricing table, Add new product images'}),
            'message': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 4, 'placeholder': 'Provide exact details of what text or media should be updated on your website...'}),
        }

from .models import Website, Service, Product

class WebsiteBuilderForm(forms.ModelForm):
    class Meta:
        model = Website
        fields = [
            'title', 'slug', 'template_choice', 'status',
            'primary_color', 'secondary_color', 'button_style',
            'headline', 'tagline', 'cta_button_text', 'cta_button_url', 'secondary_cta_text', 'secondary_cta_url',
            'about_heading', 'about_text',
            'contact_email', 'contact_phone', 'contact_whatsapp', 'contact_address',
            'show_hero', 'show_about', 'show_services', 'show_products',
            'show_gallery', 'show_social', 'show_contact', 'show_footer',
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Khadija Luxury Store'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. khadija'}),
            'template_choice': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control font-mono', 'placeholder': '#000000'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control font-mono', 'placeholder': '#FFFFFF'}),
            'button_style': forms.Select(attrs={'class': 'form-control'}),
            'headline': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Bespoke Tailoring & Luxury Fashion'}),
            'tagline': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Short elevator pitch or value proposition'}),
            'cta_button_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Order on WhatsApp'}),
            'cta_button_url': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank to use WhatsApp automatically'}),
            'secondary_cta_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Explore Catalog'}),
            'secondary_cta_url': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. #products or https://...'}),
            'about_heading': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Our Story'}),
            'about_text': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Tell your customers what makes your business unique...'}),
            'contact_email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'e.g. contact@khadija.com'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. +234 800 000 0000'}),
            'contact_whatsapp': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. +234 812 345 6789'}),
            'contact_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Victoria Island, Lagos, Nigeria'}),
            'show_hero': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_about': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_services': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_products': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_gallery': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_social': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_contact': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'show_footer': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['name', 'description', 'price', 'image', 'is_active', 'display_order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Custom Corporate Branding'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe what is included in this service...'}),
            'price': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. ₦50,000 or Contact for quote'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price', 'image', 'is_active', 'display_order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Premium Silk Scarf'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Product specifications, materials, sizing...'}),
            'price': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. ₦25,000'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }
