from django import forms

from .models import IncomeSource


class IncomeSourceForm(forms.ModelForm):
    class Meta:
        model = IncomeSource
        fields = ['name', 'source_type', 'notes']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Shop sales, Salary, House rent', 'maxlength': 100, 'autofocus': True}),
            'source_type': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Optional note'}),
        }

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.owner = owner

    def clean_name(self):
        name = ' '.join((self.cleaned_data.get('name') or '').split())
        if not name:
            raise forms.ValidationError('Please enter a name.')
        # Wahi naam (chhote / bade harf ka farq nahi) dobara nahi
        if self.owner is not None and IncomeSource.objects.filter(owner=self.owner, name__iexact=name).exists():
            raise forms.ValidationError('You already have an income source with this name.')
        return name
