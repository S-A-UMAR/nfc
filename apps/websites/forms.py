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
