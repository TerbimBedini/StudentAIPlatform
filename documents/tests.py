import shutil
import tempfile
import uuid
from pathlib import Path
from zipfile import ZipFile

import fitz
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import DocumentForm
from .models import Document
from .utils import extract_text_from_docx, extract_text_from_pdf


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TEST_MEDIA_ROOT)
class DocumentTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA_ROOT, ignore_errors=True)

    def create_pdf(self, name='test.pdf', text='Pershendetje nga PDF'):
        if name == 'test.pdf':
            name = f'{uuid.uuid4().hex}.pdf'
        path = Path(TEST_MEDIA_ROOT) / name
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), text)
        pdf.save(path)
        pdf.close()
        return path

    def create_docx(self, name='test.docx', text='Pershendetje nga DOCX'):
        if name == 'test.docx':
            name = f'{uuid.uuid4().hex}.docx'
        path = Path(TEST_MEDIA_ROOT) / name
        document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
    <w:body>
        <w:p>
            <w:r>
                <w:t>{text}</w:t>
            </w:r>
        </w:p>
    </w:body>
</w:document>'''

        with ZipFile(path, 'w') as docx:
            docx.writestr('word/document.xml', document_xml)

        return path

    def test_extract_text_from_pdf(self):
        path = self.create_pdf(text='Tekst prove')

        text = extract_text_from_pdf(path)

        self.assertIn('Tekst prove', text)

    def test_extract_text_from_docx(self):
        path = self.create_docx(text='Tekst DOCX prove')

        text = extract_text_from_docx(path)

        self.assertIn('Tekst DOCX prove', text)

    def test_document_form_rejects_unsupported_file_type(self):
        form = DocumentForm(
            data={'title': 'Test'},
            files={
                'file': SimpleUploadedFile(
                    'notes.txt',
                    b'test',
                    content_type='text/plain'
                )
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('file', form.errors)

    def test_document_detail_shows_original_pdf_by_default(self):
        user = User.objects.create_user(
            username='student',
            password='password123'
        )
        path = self.create_pdf(text='Material leksioni')
        document = Document.objects.create(
            title='Leksion',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='student', password='password123')

        response = self.client.get(
            reverse('document_detail', args=[document.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<iframe', html=False)
        self.assertContains(response, 'Hap origjinalin')
        self.assertContains(
            response,
            reverse('document_file', args=[document.id])
        )
        self.assertNotContains(response, 'Material leksioni')
        self.assertTrue(path.exists())

    def test_document_file_serves_original_pdf(self):
        user = User.objects.create_user(
            username='student',
            password='password123'
        )
        path = self.create_pdf(text='Material leksioni')
        document = Document.objects.create(
            title='Leksion',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='student', password='password123')

        response = self.client.get(
            reverse('document_file', args=[document.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    def test_document_detail_can_show_extracted_text_when_requested(self):
        user = User.objects.create_user(
            username='student',
            password='password123'
        )
        path = self.create_pdf(text='Material leksioni')
        document = Document.objects.create(
            title='Leksion',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='student', password='password123')

        response = self.client.get(
            f"{reverse('document_detail', args=[document.id])}?view=text"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Material leksioni')
        self.assertContains(response, 'Shfaq origjinalin')
        self.assertTrue(path.exists())
