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
            'show_hero', 'show_about', 'show_services', 'show_products',
            'show_gallery', 'show_social', 'show_contact', 'show_footer',
            'primary_color', 'secondary_color', 'button_style'
        ]
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control'}),
            'template_choice': forms.Select(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-control'}),
            'primary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'secondary_color': forms.TextInput(attrs={'class': 'form-control', 'type': 'color'}),
            'button_style': forms.Select(attrs={'class': 'form-control'}),
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
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. $99.00 or Contact for quote'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
        }


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ['name', 'description', 'price', 'image', 'is_active', 'display_order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'price': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. $19.99'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control'}),
        }
