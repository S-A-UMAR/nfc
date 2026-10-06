from django import forms
from .models import Profile, SocialLink, CustomLink

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = [
            'full_name', 'title', 'bio',
            'profile_image', 'cover_image',
            'phone', 'whatsapp', 'email', 'website_url', 'location', 'address',
            'business_name', 'business_category', 'business_description', 'business_logo',
            'is_search_indexed'
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Full Name'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Founder | Software Engineer'}),
            'bio': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Tell visitors about what you do...'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 800 000 0000'}),
            'whatsapp': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 800 000 0000 (WhatsApp)'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'contact@example.com'}),
            'website_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://yoursite.com'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Lagos, Nigeria'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Office / Store physical address'}),
            'business_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Business or Brand Name'}),
            'business_category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Technology, Fashion, Real Estate'}),
            'business_description': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Short business overview...'}),
        }

    def clean_profile_image(self):
        from apps.core.validators import validate_image_upload
        image = self.cleaned_data.get('profile_image')
        if image:
            validate_image_upload(image)
        return image

    def clean_cover_image(self):
        from apps.core.validators import validate_image_upload
        image = self.cleaned_data.get('cover_image')
        if image:
            validate_image_upload(image)
        return image

    def clean_business_logo(self):
        from apps.core.validators import validate_image_upload
        logo = self.cleaned_data.get('business_logo')
        if logo:
            validate_image_upload(logo)
        return logo

    def clean_website_url(self):
        from apps.core.validators import validate_safe_url
        url = self.cleaned_data.get('website_url')
        if url:
            return validate_safe_url(url, allow_relative=False)
        return url


class SocialLinkForm(forms.ModelForm):
    class Meta:
        model = SocialLink
        fields = ['platform', 'url', 'display_label']
        widgets = {
            'platform': forms.Select(attrs={'class': 'form-select'}),
            'url': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'https://instagram.com/username or @handle'}),
            'display_label': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional custom label'}),
        }

    def clean_url(self):
        from apps.core.validators import validate_safe_url
        url = self.cleaned_data.get('url', '').strip()
        if url:
            # If user provided a URL scheme, enforce http/https and reject javascript/data
            if '://' in url or url.lower().startswith(('javascript:', 'data:', 'vbscript:', 'file:')):
                validate_safe_url(url, allow_relative=False)
        return url


class CustomLinkForm(forms.ModelForm):
    class Meta:
        model = CustomLink
        fields = ['title', 'url', 'icon']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Book Consultation, View Portfolio'}),
            'url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://calendly.com/... or https://...'}),
            'icon': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'link, globe, briefcase, star, download'}),
        }

    def clean_url(self):
        from apps.core.validators import validate_safe_url
        url = self.cleaned_data.get('url', '').strip()
        if url:
            validate_safe_url(url, allow_relative=True)
        return url


class ProfileAppearanceForm(forms.ModelForm):
    """
    Dedicated form for the /dashboard/appearance/ endpoint.
    Only saves profile_type, theme, and profile_layout — nothing else.
    This prevents accidental mass-assignment of other profile fields through
    the appearance endpoint.
    """
    class Meta:
        model = Profile
        fields = ['profile_type', 'theme', 'profile_layout']
        widgets = {
            'profile_type': forms.HiddenInput(),
            'theme': forms.HiddenInput(),
            'profile_layout': forms.HiddenInput(),
        }
