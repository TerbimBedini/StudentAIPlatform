from django import forms
from .models import Document


class DocumentForm(forms.ModelForm):
    allowed_extensions = ['.pdf', '.docx']

    def clean_file(self):
        file = self.cleaned_data['file']
        file_name = file.name.lower()

        if not any(file_name.endswith(ext) for ext in self.allowed_extensions):
            raise forms.ValidationError(
                'Ngarko vetem dokumente PDF ose DOCX.'
            )

        return file

    class Meta:
        model = Document

        fields = [
            'title',
            'file'
        ]
