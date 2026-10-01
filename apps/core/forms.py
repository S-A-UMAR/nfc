from django import forms
from .models import ContactMessage, BusinessInquiry


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['full_name', 'email', 'phone', 'subject', 'message']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your Full Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+234 800 000 0000 (Optional)'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'How can we help you?'}),
            'message': forms.Textarea(attrs={'class': 'form-textarea', 'rows': 5, 'placeholder': 'Tell us more about your inquiry or project...'}),
        }


class BusinessInquiryForm(forms.ModelForm):
    """
    Public-facing business inquiry form.
    Includes a hidden honeypot field (website_url_hp) — if filled by a bot, submission is silently rejected.
    """

    # Honeypot — hidden from real users via CSS, bots will fill it
    website_url_hp = forms.CharField(
        required=False,
        label='',
        widget=forms.TextInput(attrs={
            'tabindex': '-1',
            'autocomplete': 'off',
            'aria-hidden': 'true',
            'class': 'hp-field',  # hidden via CSS
        }),
    )

    class Meta:
        model = BusinessInquiry
        fields = [
            'full_name', 'company_name', 'email', 'phone',
            'service_type', 'estimated_card_quantity', 'needs_website', 'message',
        ]
        widgets = {
            'full_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Your Full Name',
                'autocomplete': 'name',
            }),
            'company_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Company or Organisation Name (optional)',
                'autocomplete': 'organization',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'you@company.com',
                'autocomplete': 'email',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+234 800 000 0000',
                'autocomplete': 'tel',
            }),
            'service_type': forms.Select(attrs={'class': 'form-control'}),
            'estimated_card_quantity': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 50, 100–200, 500+',
            }),
            'needs_website': forms.CheckboxInput(attrs={'class': 'form-checkbox'}),
            'message': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 5,
                'placeholder': 'Tell us about your project — requirements, timeline, anything else we should know.',
            }),
        }

    def clean_website_url_hp(self):
        """Silently reject honeypot-filled submissions."""
        value = self.cleaned_data.get('website_url_hp', '')
        if value:
            # Bot detected — raise validation error that will be caught in the view
            raise forms.ValidationError('honeypot')
        return value
