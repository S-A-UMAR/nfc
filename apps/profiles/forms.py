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
            'skills_tags', 'languages',
            'stat_experience', 'stat_projects', 'stat_followers',
            'cta_banner_text',
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
            'skills_tags': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Design, Product, Tech'}),
            'languages': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. English, Spanish, French'}),
            'stat_experience': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 5+ Years'}),
            'stat_projects': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 50+ Projects'}),
            'stat_followers': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 10K+ Followers'}),
            'cta_banner_text': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "e.g. Let's build something great together."}),
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


class ContactExchangeForm(forms.ModelForm):
    """
    Form for visitors to submit contact details to a profile owner.
    Enforces server-side consent validation and minimum required contact information.
    """
    class Meta:
        from .models import ContactExchange
        model = ContactExchange
        fields = ['full_name', 'email', 'phone', 'business_name', 'notes', 'consent_given']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Full Name *', 'required': 'required'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email Address'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone Number (e.g. +234 ...)'}),
            'business_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company / Business (Optional)'}),
            'notes': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'Short note or context (Optional)'}),
            'consent_given': forms.CheckboxInput(attrs={'class': 'form-checkbox', 'required': 'required'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email', '').strip()
        phone = cleaned_data.get('phone', '').strip()
        consent = cleaned_data.get('consent_given')

        if not email and not phone:
            raise forms.ValidationError("Please provide at least an email address or phone number so the profile owner can get back to you.")
        
        if not consent:
            raise forms.ValidationError("You must consent to sharing your details with the profile owner.")

        return cleaned_data


class ProfileServiceForm(forms.ModelForm):
    class Meta:
        from .models import ProfileService
        model = ProfileService
        fields = ['title', 'description', 'icon', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Product Design'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. UI/UX, Brand & Product'}),
            'icon': forms.Select(attrs={'class': 'form-select'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'style': 'max-width: 100px;'}),
        }


class ProfileGalleryItemForm(forms.ModelForm):
    class Meta:
        from .models import ProfileGalleryItem
        model = ProfileGalleryItem
        fields = ['title', 'image', 'image_url', 'link_url', 'order']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Project or image title'}),
            'image_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://... (Optional fallback image URL)'}),
            'link_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://... (External project link)'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'style': 'max-width: 100px;'}),
        }

    def clean_image(self):
        from apps.core.validators import validate_image_upload
        image = self.cleaned_data.get('image')
        if image:
            validate_image_upload(image)
        return image

    def clean_link_url(self):
        from apps.core.validators import validate_safe_url
        url = self.cleaned_data.get('link_url')
        if url:
            return validate_safe_url(url, allow_relative=False)
        return url


class ProfileTestimonialForm(forms.ModelForm):
    class Meta:
        from .models import ProfileTestimonial
        model = ProfileTestimonial
        fields = ['client_name', 'client_title', 'content', 'rating', 'client_avatar', 'order']
        widgets = {
            'client_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Client Name'}),
            'client_title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Founder, ScaleUp'}),
            'content': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 3, 'placeholder': 'What the client said...'}),
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 5, 'style': 'max-width: 100px;'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'style': 'max-width: 100px;'}),
        }

    def clean_client_avatar(self):
        from apps.core.validators import validate_image_upload
        avatar = self.cleaned_data.get('client_avatar')
        if avatar:
            validate_image_upload(avatar)
        return avatar


