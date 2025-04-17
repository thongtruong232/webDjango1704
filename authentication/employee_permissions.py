from django import forms
from .employee_models import EMAIL_STATUS_CHOICES, EMAIL_SUPPLIER_CHOICES

class DynamicEmailForm(forms.Form):
    bulk_input = forms.CharField(
        label='Danh sách email (email|pass|refreshtoken|client_id)',
        widget=forms.Textarea(attrs={'rows': 10, 'placeholder': 'email|pass|refreshtoken|client_id\n...'}),
        help_text='Mỗi dòng là một email, cách nhau bởi dấu |',
        required=False
    )
    import_file = forms.FileField(
            label='Hoặc import từ file (.txt)',
            required=False,
            help_text='Mỗi dòng trong file phải có định dạng email|pass|refreshtoken|client_id'
    )
    status = forms.ChoiceField(
        label='Trạng thái',
        choices=[(key, key.capitalize()) for key in EMAIL_STATUS_CHOICES.keys()]
    )
    sub_status = forms.ChoiceField(
        label='Sub-status',
        required=False,
        choices=[]
    )
    supplier = forms.ChoiceField(
        label='Nhà cung cấp',
        choices=[(key, key.capitalize()) for key in EMAIL_SUPPLIER_CHOICES.keys()]
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        status_value = self.data.get('status') or self.initial.get('status')
        if status_value in EMAIL_STATUS_CHOICES:
            self.fields['sub_status'].choices = [(sub, sub) for sub in EMAIL_STATUS_CHOICES[status_value]]
        else:
            self.fields['sub_status'].choices = []