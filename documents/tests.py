import shutil
import tempfile
import uuid
from unittest.mock import patch
from pathlib import Path
from zipfile import ZipFile

import fitz
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import DocumentForm
from .models import Document, QuizAttempt
from .utils import extract_text_from_docx, extract_text_from_pdf
from .ai import AIError


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

    @patch('documents.views.generate_quiz')
    def test_document_quiz_scores_selected_answers(self, mock_generate_quiz):
        mock_generate_quiz.return_value = '''
        1. Cfare eshte AI?
        A) Inteligjence artificiale
        B) Dokument
        C) PDF
        D) Laptop
        Pergjigjja e sakte: A
        '''
        user = User.objects.create_user(
            username='student',
            password='password123'
        )
        path = self.create_pdf(text='AI eshte inteligjence artificiale')
        document = Document.objects.create(
            title='Leksion',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='student', password='password123')

        response = self.client.get(reverse('document_quiz', args=[document.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Submit Quiz')
        self.assertContains(response, 'Cfare eshte AI?')

        response = self.client.post(
            reverse('document_quiz', args=[document.id]),
            {'action': 'submit', 'question_0': 'A'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1/1')
        self.assertContains(response, 'Ekselent')
        self.assertContains(response, 'E sakte')
        self.assertTrue(
            QuizAttempt.objects.filter(
                document=document,
                user=user,
                score=1,
                total=1,
                category='Ekselent'
            ).exists()
        )

    @patch('documents.views.generate_quiz')
    def test_document_quiz_marks_wrong_answer_and_shows_advice(self, mock_generate_quiz):
        mock_generate_quiz.return_value = '''
        1. Cfare eshte fotosinteza?
        A) Proces biologjik
        B) Formula matematike
        C) Lloj dokumenti
        D) Program kompjuteri
        Pergjigjja e sakte: A
        '''
        user = User.objects.create_user(
            username='student_wrong',
            password='password123'
        )
        path = self.create_pdf(text='Fotosinteza eshte proces biologjik')
        document = Document.objects.create(
            title='Biologji',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='student_wrong', password='password123')

        self.client.get(reverse('document_quiz', args=[document.id]))
        response = self.client.post(
            reverse('document_quiz', args=[document.id]),
            {'action': 'submit', 'question_0': 'B'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '0/1')
        self.assertContains(response, 'Dobet')
        self.assertContains(response, 'Gabim')
        self.assertContains(response, 'E sakte')
        self.assertContains(response, 'Sugjerime per perseritje')

    @patch('documents.views.generate_quiz')
    def test_document_quiz_shows_ai_error(self, mock_generate_quiz):
        mock_generate_quiz.side_effect = AIError('AI nuk u lidh dot me Ollama.')
        user = User.objects.create_user(
            username='student2',
            password='password123'
        )
        path = self.create_pdf(text='Fotosinteza eshte proces biologjik')
        document = Document.objects.create(
            title='Biologji',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='student2', password='password123')

        response = self.client.get(reverse('document_quiz', args=[document.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI nuk u lidh dot me Ollama.')

    def test_quiz_history_shows_saved_attempts(self):
        user = User.objects.create_user(
            username='student3',
            password='password123'
        )
        path = self.create_pdf(text='Material historie')
        document = Document.objects.create(
            title='Histori',
            file=path.name,
            uploaded_by=user
        )
        QuizAttempt.objects.create(
            document=document,
            user=user,
            score=8,
            total=10,
            category='Super',
            mistakes=[
                {
                    'number': 2,
                    'question': 'Cfare duhet perseritur?',
                    'selected': 'B'
                }
            ]
        )
        self.client.login(username='student3', password='password123')

        response = self.client.get(reverse('quiz_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Historiku i Quizeve')
        self.assertContains(response, '80%')
        self.assertContains(response, 'Super')
        self.assertContains(response, 'Cfare duhet perseritur?')
