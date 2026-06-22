from pathlib import Path

from django import forms
from .models import CommunityMessage, Document, LibraryDocument


MAX_UPLOAD_SIZE = 20 * 1024 * 1024
MAX_LIBRARY_UPLOAD_SIZE = MAX_UPLOAD_SIZE
SUSPICIOUS_EXTENSIONS = {
    '.exe',
    '.bat',
    '.cmd',
    '.com',
    '.dll',
    '.js',
    '.php',
    '.msi',
    '.ps1',
    '.scr',
    '.sh',
    '.vbs',
    '.zip',
}
ALLOWED_DOCUMENT_EXTENSIONS = {
    '.pdf': {
        'label': 'PDF',
        'signatures': (b'%PDF',),
        'content_types': {
            'application/pdf',
            'application/x-pdf',
            'application/octet-stream',
            'binary/octet-stream',
        },
    },
    '.docx': {
        'label': 'DOCX',
        'signatures': (b'PK',),
        'content_types': {
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/zip',
            'application/x-zip-compressed',
            'application/octet-stream',
            'binary/octet-stream',
        },
    },
    '.pptx': {
        'label': 'PPTX',
        'signatures': (b'PK',),
        'content_types': {
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/zip',
            'application/x-zip-compressed',
            'application/octet-stream',
            'binary/octet-stream',
        },
    },
}


def validate_uploaded_study_file(file):
    file_name = file.name.lower()
    extension = Path(file_name).suffix

    if extension in SUSPICIOUS_EXTENSIONS:
        raise forms.ValidationError(
            'Ky format nuk lejohet per arsye sigurie.'
        )

    if extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise forms.ValidationError(
            'Ngarko vetem dokumente PDF, DOCX ose PPTX.'
        )

    if file.size > MAX_UPLOAD_SIZE:
        raise forms.ValidationError(
            'Dokumenti duhet te jete me pak se 20MB.'
        )

    content_type = getattr(file, 'content_type', '')
    allowed_content_types = ALLOWED_DOCUMENT_EXTENSIONS[extension]['content_types']

    if content_type and content_type not in allowed_content_types:
        raise forms.ValidationError(
            'Lloji i dokumentit nuk duket i sigurt per ngarkim.'
        )

    header = file.read(4)
    file.seek(0)

    signatures = ALLOWED_DOCUMENT_EXTENSIONS[extension]['signatures']
    if not any(header.startswith(signature) for signature in signatures):
        label = ALLOWED_DOCUMENT_EXTENSIONS[extension]['label']
        raise forms.ValidationError(
            f'Dokumenti {label} nuk kaloi kontrollin e sigurise.'
        )

    return file


class DocumentForm(forms.ModelForm):
    allowed_extensions = list(ALLOWED_DOCUMENT_EXTENSIONS.keys())

    def clean_file(self):
        file = self.cleaned_data['file']
        return validate_uploaded_study_file(file)

    class Meta:
        model = Document

        fields = [
            'title',
            'file'
        ]


class LibraryDocumentForm(forms.ModelForm):
    allowed_extensions = list(ALLOWED_DOCUMENT_EXTENSIONS.keys())

    safety_confirmation = forms.BooleanField(
        required=True,
        label='I confirm this file is study material and does not contain malware, copyrighted content I cannot share, or harmful content.'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            if field_name == 'safety_confirmation':
                field.widget.attrs.update({'class': 'form-check-input'})
            elif field_name == 'description':
                field.widget.attrs.update({
                    'class': 'form-control',
                    'rows': 4,
                })
            else:
                field.widget.attrs.update({'class': 'form-control'})

        for field_name in ['field', 'document_type']:
            self.fields[field_name].widget.attrs.update({'class': 'form-select'})

    def clean_file(self):
        file = self.cleaned_data['file']
        return validate_uploaded_study_file(file)

    class Meta:
        model = LibraryDocument
        fields = [
            'title',
            'field',
            'document_type',
            'course_name',
            'academic_year',
            'description',
            'file',
        ]


class CommunityMessageForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field_name, field in self.fields.items():
            if field_name == 'message':
                field.widget.attrs.update({
                    'class': 'form-control',
                    'rows': 5,
                })
            elif field_name in ['field', 'kind']:
                field.widget.attrs.update({'class': 'form-select'})
            else:
                field.widget.attrs.update({'class': 'form-control'})

    class Meta:
        model = CommunityMessage
        fields = [
            'field',
            'kind',
            'title',
            'message',
        ]
