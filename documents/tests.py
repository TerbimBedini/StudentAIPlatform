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

from .forms import DocumentForm, LibraryDocumentForm
from .models import (
    Activity,
    CommunityMessage,
    Document,
    FlashcardAttempt,
    LibraryDocument,
    QuizAttempt,
)
from .utils import extract_text_from_docx, extract_text_from_pdf
from .ai import AIError, generate_fast_document_quiz, select_quiz_source_text
from .progress import analyze_student_strengths, get_next_study_action
from .views import evaluate_flashcard_answer, parse_exam_response, parse_quiz_response


TEST_MEDIA_ROOT = tempfile.mkdtemp()


@override_settings(
    MEDIA_ROOT=TEST_MEDIA_ROOT,
    STUDENTAI_SYNC_UPLOAD_PROCESSING=True
)
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

    @patch('documents.views.generate_summary')
    def test_upload_document_generates_summary_for_docx(self, mock_generate_summary):
        mock_generate_summary.return_value = 'Permbledhje DOCX.'
        user = User.objects.create_user(
            username='docx_summary_student',
            password='password123'
        )
        path = self.create_docx(text='Material DOCX per summary')
        self.client.login(username='docx_summary_student', password='password123')

        with open(path, 'rb') as file_handle:
            response = self.client.post(
                reverse('upload_document'),
                {
                    'title': 'DOCX Summary',
                    'file': SimpleUploadedFile(
                        path.name,
                        file_handle.read(),
                        content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                    )
                }
            )

        self.assertEqual(response.status_code, 302)
        document = Document.objects.get(title='DOCX Summary')
        self.assertEqual(document.summary, 'Permbledhje DOCX.')
        self.assertTrue(document.ai_processed)
        self.assertIn('Material DOCX per summary', mock_generate_summary.call_args.args[0])

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

    def test_document_form_accepts_safe_pptx_upload(self):
        form = DocumentForm(
            data={'title': 'Slides'},
            files={
                'file': SimpleUploadedFile(
                    'slides.pptx',
                    b'PK\x03\x04safe presentation content',
                    content_type='application/vnd.openxmlformats-officedocument.presentationml.presentation'
                )
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_document_form_accepts_zip_content_type_for_docx(self):
        form = DocumentForm(
            data={'title': 'DOCX from browser'},
            files={
                'file': SimpleUploadedFile(
                    'notes.docx',
                    b'PK\x03\x04safe document content',
                    content_type='application/zip'
                )
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_upload_pptx_creates_document_without_ai_processing(self):
        user = User.objects.create_user(
            username='pptx_upload_student',
            password='password123'
        )
        self.client.login(
            username='pptx_upload_student',
            password='password123'
        )

        response = self.client.post(
            reverse('upload_document'),
            {
                'title': 'Lecture Slides',
                'file': SimpleUploadedFile(
                    'lecture.pptx',
                    b'PK\x03\x04safe presentation content',
                    content_type='application/zip'
                )
            }
        )

        self.assertRedirects(response, reverse('dashboard'))
        document = Document.objects.get(title='Lecture Slides')
        self.assertEqual(document.uploaded_by, user)
        self.assertEqual(document.summary_status, Document.STATUS_PENDING)

    def test_analyze_student_strengths_recommends_quizzes_without_attempts(self):
        user = User.objects.create_user(
            username='diagnosis_empty',
            password='password123'
        )

        diagnosis = analyze_student_strengths(user)

        self.assertEqual(diagnosis['strong_areas'], [])
        self.assertEqual(diagnosis['weak_areas'], [])
        self.assertIn('Generate your first quiz', diagnosis['recommendation'])

    def test_analyze_student_strengths_groups_by_document_title(self):
        user = User.objects.create_user(
            username='diagnosis_student',
            password='password123'
        )
        strong_path = self.create_pdf(text='Strong topic material')
        weak_path = self.create_pdf(text='Weak topic material')
        strong_document = Document.objects.create(
            title='Algorithms',
            file=strong_path.name,
            uploaded_by=user
        )
        weak_document = Document.objects.create(
            title='Calculus',
            file=weak_path.name,
            uploaded_by=user
        )
        QuizAttempt.objects.create(
            document=strong_document,
            user=user,
            score=9,
            total=10
        )
        QuizAttempt.objects.create(
            document=weak_document,
            user=user,
            score=5,
            total=10
        )

        diagnosis = analyze_student_strengths(user)

        self.assertEqual(diagnosis['strong_areas'][0]['topic'], 'Algorithms')
        self.assertEqual(diagnosis['strong_areas'][0]['average_score'], 90)
        self.assertEqual(diagnosis['weak_areas'][0]['topic'], 'Calculus')
        self.assertEqual(diagnosis['weak_areas'][0]['average_score'], 50)
        self.assertIn('Calculus', diagnosis['recommendation'])

    def test_get_next_study_action_without_documents(self):
        user = User.objects.create_user(
            username='next_action_empty',
            password='password123'
        )

        action = get_next_study_action(user)

        self.assertEqual(
            action,
            'Upload your first document to start learning.'
        )

    def test_get_next_study_action_without_summaries(self):
        user = User.objects.create_user(
            username='next_action_no_summary',
            password='password123'
        )
        path = self.create_pdf(text='Material without summary')
        Document.objects.create(
            title='No Summary',
            file=path.name,
            uploaded_by=user
        )

        action = get_next_study_action(user)

        self.assertEqual(
            action,
            'Generate AI summaries for your uploaded materials.'
        )

    def test_get_next_study_action_without_quiz_attempts(self):
        user = User.objects.create_user(
            username='next_action_no_quiz',
            password='password123'
        )
        path = self.create_pdf(text='Material with summary')
        Document.objects.create(
            title='With Summary',
            file=path.name,
            uploaded_by=user,
            summary='AI summary'
        )

        action = get_next_study_action(user)

        self.assertEqual(
            action,
            'Take your first quiz to measure your understanding.'
        )

    def test_get_next_study_action_uses_average_quiz_score(self):
        user = User.objects.create_user(
            username='next_action_scores',
            password='password123'
        )
        path = self.create_pdf(text='Scored material')
        document = Document.objects.create(
            title='Scored Topic',
            file=path.name,
            uploaded_by=user,
            summary='AI summary'
        )

        QuizAttempt.objects.create(
            document=document,
            user=user,
            score=5,
            total=10
        )
        self.assertEqual(
            get_next_study_action(user),
            'Review your weak topics and practice with flashcards.'
        )

        QuizAttempt.objects.all().delete()
        QuizAttempt.objects.create(
            document=document,
            user=user,
            score=7,
            total=10
        )
        self.assertEqual(
            get_next_study_action(user),
            'Continue practicing quizzes to improve your knowledge score.'
        )

        QuizAttempt.objects.all().delete()
        QuizAttempt.objects.create(
            document=document,
            user=user,
            score=9,
            total=10
        )
        self.assertEqual(
            get_next_study_action(user),
            'Great progress! Try advanced quizzes or start a new study session.'
        )

    def test_library_upload_form_rejects_renamed_non_pdf(self):
        form = LibraryDocumentForm(
            data={
                'title': 'Unsafe',
                'field': LibraryDocument.FIELD_ENGINEERING,
                'document_type': LibraryDocument.TYPE_LECTURE,
                'course_name': 'Security',
                'academic_year': '2026',
                'description': 'Bad file',
                'safety_confirmation': 'on',
            },
            files={
                'file': SimpleUploadedFile(
                    'bad.pdf',
                    b'not actually a pdf',
                    content_type='application/pdf'
                )
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn('file', form.errors)

    def test_library_upload_form_accepts_pdf_for_review(self):
        form = LibraryDocumentForm(
            data={
                'title': 'Lecture',
                'field': LibraryDocument.FIELD_MEDICINE,
                'document_type': LibraryDocument.TYPE_LECTURE,
                'course_name': 'Anatomy',
                'academic_year': '2026',
                'description': 'Lecture notes',
                'safety_confirmation': 'on',
            },
            files={
                'file': SimpleUploadedFile(
                    'lecture.pdf',
                    b'%PDF-1.4 safe test content',
                    content_type='application/pdf'
                )
            }
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_library_home_lists_only_approved_public_documents(self):
        user = User.objects.create_user(
            username='library_student',
            password='password123'
        )
        other_user = User.objects.create_user(
            username='library_uploader',
            password='password123'
        )
        LibraryDocument.objects.create(
            title='Approved Algorithms',
            field=LibraryDocument.FIELD_COMPUTER_SCIENCE,
            document_type=LibraryDocument.TYPE_LECTURE,
            course_name='Algorithms',
            description='Sorting and graphs',
            file='library/approved.pdf',
            uploaded_by=other_user,
            moderation_status=LibraryDocument.STATUS_APPROVED,
            is_public=True
        )
        LibraryDocument.objects.create(
            title='Pending Anatomy',
            field=LibraryDocument.FIELD_MEDICINE,
            document_type=LibraryDocument.TYPE_LECTURE,
            course_name='Anatomy',
            file='library/pending.pdf',
            uploaded_by=other_user,
            moderation_status=LibraryDocument.STATUS_PENDING,
            is_public=False
        )
        self.client.login(username='library_student', password='password123')

        response = self.client.get(
            reverse('library_home'),
            {'field': LibraryDocument.FIELD_COMPUTER_SCIENCE, 'q': 'Algo'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Approved Algorithms')
        self.assertContains(response, 'Algorithms')
        self.assertNotContains(response, 'Pending Anatomy')

    def test_library_upload_creates_pending_private_submission(self):
        user = User.objects.create_user(
            username='library_submitter',
            password='password123'
        )
        self.client.login(username='library_submitter', password='password123')

        response = self.client.post(
            reverse('library_upload'),
            {
                'title': 'Shared Physics Notes',
                'field': LibraryDocument.FIELD_SCIENCE,
                'document_type': LibraryDocument.TYPE_NOTES,
                'course_name': 'Physics',
                'academic_year': '2026',
                'description': 'Kinematics notes',
                'safety_confirmation': 'on',
                'file': SimpleUploadedFile(
                    'physics.pdf',
                    b'%PDF-1.4 safe library content',
                    content_type='application/pdf'
                )
            }
        )

        self.assertRedirects(response, reverse('library_submissions'))
        submission = LibraryDocument.objects.get(title='Shared Physics Notes')
        self.assertEqual(submission.uploaded_by, user)
        self.assertEqual(submission.moderation_status, LibraryDocument.STATUS_PENDING)
        self.assertFalse(submission.is_public)
        self.assertIn('Waiting for staff moderation', submission.safety_scan_notes)

    def test_staff_can_approve_library_submission(self):
        student = User.objects.create_user(
            username='moderated_student',
            password='password123'
        )
        staff = User.objects.create_user(
            username='moderator',
            password='password123',
            is_staff=True
        )
        submission = LibraryDocument.objects.create(
            title='Calculus Exam',
            field=LibraryDocument.FIELD_ENGINEERING,
            document_type=LibraryDocument.TYPE_EXAM,
            course_name='Calculus',
            file='library/calculus.pdf',
            uploaded_by=student,
            moderation_status=LibraryDocument.STATUS_PENDING,
            is_public=False
        )
        self.client.login(username='moderator', password='password123')

        response = self.client.post(
            reverse('moderate_library_document', args=[submission.id, 'approve']),
            {'moderation_notes': 'Looks useful.'}
        )

        self.assertRedirects(response, reverse('library_moderation'))
        submission.refresh_from_db()
        self.assertEqual(submission.moderation_status, LibraryDocument.STATUS_APPROVED)
        self.assertTrue(submission.is_public)
        self.assertEqual(submission.reviewed_by, staff)
        self.assertEqual(submission.moderation_notes, 'Looks useful.')

    def test_community_chat_creates_and_filters_messages(self):
        user = User.objects.create_user(
            username='community_student',
            password='password123'
        )
        CommunityMessage.objects.create(
            user=user,
            field=LibraryDocument.FIELD_LAW,
            kind=CommunityMessage.KIND_REQUEST,
            title='Need law notes',
            message='Does anyone have constitutional law notes?'
        )
        self.client.login(username='community_student', password='password123')

        response = self.client.post(
            reverse('community_chat'),
            {
                'field': LibraryDocument.FIELD_ENGINEERING,
                'kind': CommunityMessage.KIND_OFFER,
                'title': 'Thermodynamics notes',
                'message': 'I can share chapter summaries.'
            }
        )

        self.assertRedirects(response, reverse('community_chat'))
        self.assertTrue(
            CommunityMessage.objects.filter(
                user=user,
                title='Thermodynamics notes',
                field=LibraryDocument.FIELD_ENGINEERING
            ).exists()
        )

        response = self.client.get(
            reverse('community_chat'),
            {'field': LibraryDocument.FIELD_ENGINEERING}
        )

        self.assertContains(response, 'Thermodynamics notes')
        self.assertNotContains(response, 'Need law notes')

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

        session = self.client.session
        questions = session[f'document_quiz_{document.id}']

        response = self.client.post(
            reverse('document_quiz', args=[document.id]),
            {'action': 'submit', 'question_0': questions[0]['answer']}
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
        session = self.client.session
        questions = session[f'document_quiz_{document.id}']
        wrong_answer = next(
            key
            for key in ['A', 'B', 'C', 'D']
            if key != questions[0]['answer']
        )
        response = self.client.post(
            reverse('document_quiz', args=[document.id]),
            {'action': 'submit', 'question_0': wrong_answer}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '0/1')
        self.assertContains(response, 'Dobet')
        self.assertContains(response, 'Gabim')
        self.assertContains(response, 'E sakte')
        self.assertContains(response, 'Sugjerime per perseritje')

    def test_parse_quiz_response_balances_correct_answer_letters(self):
        raw_quiz = '\n\n'.join(
            f'''
            {index}. Pyetja numer {index}?
            A) Pergjigjja e sakte numer {index}
            B) Alternativa gabim numer {index} nje
            C) Alternativa gabim numer {index} dy
            D) Alternativa gabim numer {index} tre
            Pergjigjja e sakte: A
            '''
            for index in range(1, 11)
        )

        questions = parse_quiz_response(raw_quiz)
        answer_counts = {
            key: [question['answer'] for question in questions].count(key)
            for key in ['A', 'B', 'C', 'D']
        }

        self.assertEqual(len(questions), 10)
        self.assertGreater(len(set(question['answer'] for question in questions)), 1)
        self.assertLessEqual(max(answer_counts.values()), 3)
        self.assertGreaterEqual(min(answer_counts.values()), 2)
        for question in questions:
            self.assertTrue(
                question['options'][question['answer']].startswith('Pergjigjja e sakte')
            )

    def test_parse_quiz_response_skips_visually_obvious_questions(self):
        raw_quiz = '''
        1. Cila eshte e sakte?
        A) Kjo pergjigje eshte shume me e gjate dhe jep shpjegim te plote me shume detaje te panevojshme per ta bere te dukshme.
        B) Fjale te shkurtra
        C) Fraze tjeter
        D) Mundesi tjeter
        Pergjigjja e sakte: A

        2. Cila ide lidhet me tekstin?
        A) Ideja lidhet me krahasimin mes dy koncepteve kryesore
        B) Ideja lidhet me nje krahasim tjeter te afert
        C) Ideja lidhet me nje pasoje te ngjashme
        D) Ideja lidhet me nje shembull tjeter
        Pergjigjja e sakte: A
        '''

        questions = parse_quiz_response(raw_quiz)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]['question'], 'Cila ide lidhet me tekstin?')

    @patch('documents.views.random.shuffle')
    def test_parse_quiz_response_shuffles_question_order(self, mock_shuffle):
        raw_quiz = '\n\n'.join(
            f'''
            {index}. Pyetja numer {index}?
            A) Pergjigjja e sakte numer {index}
            B) Alternativa gabim numer {index} nje
            C) Alternativa gabim numer {index} dy
            D) Alternativa gabim numer {index} tre
            Pergjigjja e sakte: A
            '''
            for index in range(1, 6)
        )

        def reverse_shuffle(items):
            items.reverse()

        mock_shuffle.side_effect = reverse_shuffle

        questions = parse_quiz_response(raw_quiz)

        self.assertEqual(questions[0]['question'], 'Pyetja numer 5?')

    def test_parse_exam_response_keeps_answer_explanations(self):
        raw_exam = '''
        1. Cfare mat dokumenti?
        A) Njohuri
        B) Ngjyra
        C) Zhurma
        D) Ikona
        Pergjigjja e sakte: A
        Shpjegim: Dokumenti flet per matjen e njohurive.
        '''

        questions = parse_exam_response(raw_exam)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]['answer'], 'A')
        self.assertIn('matjen e njohurive', questions[0]['explanation'])

    @patch('documents.views.generate_exam')
    def test_exam_simulator_generates_exam_for_owned_document(self, mock_generate_exam):
        mock_generate_exam.return_value = '''
        1. Cfare permendet ne material?
        A) Koncepti kryesor
        B) Nje teme tjeter
        C) Nje pergjigje e gabuar
        D) Nje detaj i palidhur
        Pergjigjja e sakte: A
        Shpjegim: Koncepti kryesor permendet ne dokument.
        '''
        user = User.objects.create_user(
            username='exam_student',
            password='password123'
        )
        path = self.create_pdf(text='Koncepti kryesor permendet ne material.')
        document = Document.objects.create(
            title='Exam Source',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='exam_student', password='password123')

        response = self.client.get(reverse('exam_simulator', args=[document.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Exam Simulator')
        self.assertContains(response, 'Exam Source')
        self.assertContains(response, 'Cfare permendet ne material?')
        self.assertContains(response, 'Answer Key')
        self.assertContains(response, 'Koncepti kryesor permendet ne dokument.')

    def test_exam_simulator_blocks_other_users_document(self):
        owner = User.objects.create_user(
            username='exam_owner',
            password='password123'
        )
        user = User.objects.create_user(
            username='exam_intruder',
            password='password123'
        )
        path = self.create_pdf(text='Private exam material.')
        document = Document.objects.create(
            title='Private Source',
            file=path.name,
            uploaded_by=owner
        )
        self.client.login(username='exam_intruder', password='password123')

        response = self.client.get(reverse('exam_simulator', args=[document.id]))

        self.assertEqual(response.status_code, 404)

    @patch('documents.ai.random.sample')
    @patch('documents.ai.random.shuffle')
    def test_fast_quiz_uses_different_sentence_rows_for_short_documents(self, mock_shuffle, mock_sample):
        text = (
            'Fjalia e pare ka material te mjaftueshem per nje pyetje prove. '
            'Fjalia e dyte ka material te mjaftueshem per nje pyetje prove. '
            'Fjalia e trete ka material te mjaftueshem per nje pyetje prove.'
        )

        def reverse_shuffle(items):
            items.reverse()

        mock_shuffle.side_effect = reverse_shuffle

        quiz = generate_fast_document_quiz(text, max_questions=3)

        self.assertIn('1. Cfare thuhet', quiz)
        self.assertLess(
            quiz.index('Fjalia e trete'),
            quiz.index('Fjalia e pare')
        )
        mock_sample.assert_not_called()

    @patch('documents.ai.random.shuffle')
    def test_quiz_source_text_samples_different_windows_for_large_documents(self, mock_shuffle):
        document_text = '\n'.join(
            f'Seksioni {index} ka tekst te gjate per testim dhe shembuj te ndryshem.'
            for index in range(1, 90)
        )

        def reverse_shuffle(items):
            items.reverse()

        mock_shuffle.side_effect = reverse_shuffle

        selected_text = select_quiz_source_text(
            document_text,
            target_chars=700,
            window_chars=350
        )

        self.assertIn('Seksioni 80', selected_text)
        self.assertNotIn('Seksioni 1 ka tekst', selected_text)

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

    @patch('documents.views.generate_flashcards')
    def test_document_flashcards_shows_generated_flashcards(self, mock_generate_flashcards):
        mock_generate_flashcards.return_value = '''
        1. Pyetje: Cfare eshte AI?
           Pergjigje: Inteligjence artificiale.
        '''
        user = User.objects.create_user(
            username='flashcard_student',
            password='password123'
        )
        path = self.create_pdf(text='AI eshte inteligjence artificiale')
        document = Document.objects.create(
            title='Leksion',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='flashcard_student', password='password123')

        response = self.client.get(reverse('document_flashcards', args=[document.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Flashcards AI')
        self.assertContains(response, 'Cfare eshte AI?')

        response = self.client.post(
            reverse('document_flashcards', args=[document.id]),
            {
                'action': 'submit',
                'answer_0': 'AI eshte inteligjence artificiale'
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Vleresimi i pergjithshem')
        self.assertContains(response, 'Shume mire')
        self.assertTrue(
            FlashcardAttempt.objects.filter(
                document=document,
                user=user,
                average_score__gte=70
            ).exists()
        )

    def test_flashcard_history_shows_saved_attempts(self):
        user = User.objects.create_user(
            username='flash_history',
            password='password123'
        )
        path = self.create_pdf(text='Material flashcards')
        document = Document.objects.create(
            title='Flash Leksion',
            file=path.name,
            uploaded_by=user
        )
        FlashcardAttempt.objects.create(
            document=document,
            user=user,
            average_score=82,
            category='Shume mire',
            cards=[
                {
                    'question': 'Cfare duhet perseritur?',
                    'evaluation': {'score': 35}
                }
            ]
        )
        self.client.login(username='flash_history', password='password123')

        response = self.client.get(reverse('flashcard_history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Historiku i Flashcards')
        self.assertContains(response, '82%')
        self.assertContains(response, 'Grafiku i progresit')
        self.assertContains(response, 'Cfare duhet perseritur?')

    def test_flashcard_evaluation_accepts_short_keyword_answer(self):
        result = evaluate_flashcard_answer(
            'Permbledhja ruhet ne databaze dhe shfaqet ne dashboard.',
            'ne databaze'
        )

        self.assertGreaterEqual(result['score'], 70)
        self.assertEqual(result['label'], 'Shume mire')

    def test_flashcard_evaluation_rejects_generic_weak_answer(self):
        result = evaluate_flashcard_answer(
            'Permbledhja shfaqet ne dashboard.',
            'Shfaqet ne menyre shume te permbledhur'
        )

        self.assertLess(result['score'], 40)
        self.assertEqual(result['label'], 'Duhet perseritur')

    @patch('documents.views.ask_document_ai')
    def test_multi_document_study_chat_uses_selected_documents(self, mock_ask_document_ai):
        mock_ask_document_ai.return_value = 'Pergjigje nga disa materiale.'
        user = User.objects.create_user(
            username='multi_student',
            password='password123'
        )
        first_path = self.create_pdf(text='Materiali i pare per AI')
        second_path = self.create_pdf(text='Materiali i dyte per provim')
        first_document = Document.objects.create(
            title='Materiali 1',
            file=first_path.name,
            uploaded_by=user
        )
        second_document = Document.objects.create(
            title='Materiali 2',
            file=second_path.name,
            uploaded_by=user
        )
        self.client.login(username='multi_student', password='password123')

        response = self.client.post(
            reverse('multi_document_study'),
            {
                'documents': [first_document.id, second_document.id],
                'action': 'chat',
                'question': 'Cfare duhet te perseris?'
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pergjigje nga disa materiale.')
        prompt_text = mock_ask_document_ai.call_args.args[0]
        self.assertIn('Materiali i pare per AI', prompt_text)
        self.assertIn('Materiali i dyte per provim', prompt_text)

    @patch('documents.views.generate_quiz')
    def test_multi_document_study_generates_quiz_from_selected_documents(self, mock_generate_quiz):
        mock_generate_quiz.return_value = '''
        1. Cfare perseritet nga materialet?
        A) Konceptet kryesore
        B) Vetem titulli
        C) Asgje
        D) Ngjyrat
        Pergjigjja e sakte: A
        '''
        user = User.objects.create_user(
            username='multi_quiz_student',
            password='password123'
        )
        first_path = self.create_pdf(text='Materiali i pare ka koncepte kryesore')
        second_path = self.create_pdf(text='Materiali i dyte ka tema provimi')
        first_document = Document.objects.create(
            title='Kapitulli 1',
            file=first_path.name,
            uploaded_by=user
        )
        second_document = Document.objects.create(
            title='Kapitulli 2',
            file=second_path.name,
            uploaded_by=user
        )
        self.client.login(username='multi_quiz_student', password='password123')

        response = self.client.post(
            reverse('multi_document_study'),
            {
                'documents': [first_document.id, second_document.id],
                'action': 'quiz'
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cfare perseritet nga materialet?')
        self.assertContains(response, 'Submit Quiz')
        prompt_text = mock_generate_quiz.call_args.args[0]
        self.assertIn('Materiali i pare ka koncepte kryesore', prompt_text)
        self.assertIn('Materiali i dyte ka tema provimi', prompt_text)

    @patch('documents.views.ask_document_ai')
    def test_chat_records_activity_and_dashboard_score(self, mock_ask_document_ai):
        mock_ask_document_ai.return_value = 'Pergjigje AI.'
        user = User.objects.create_user(
            username='activity_student',
            password='password123'
        )
        path = self.create_pdf(text='Material per aktivitet')
        document = Document.objects.create(
            title='Aktivitet',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='activity_student', password='password123')

        response = self.client.post(
            reverse('document_chat', args=[document.id]),
            {'question': 'Cfare ka materiali?'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            Activity.objects.filter(
                user=user,
                activity_type='chat',
                document_title='Aktivitet',
                points=2
            ).exists()
        )

        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'Student Score')
        self.assertContains(response, '+2')

    @patch('documents.views.ask_document_ai')
    def test_document_chat_ask_returns_json_answer(self, mock_ask_document_ai):
        mock_ask_document_ai.return_value = 'Pergjigje pa reload.'
        user = User.objects.create_user(
            username='ajax_student',
            password='password123'
        )
        path = self.create_pdf(text='Material per ajax chat')
        document = Document.objects.create(
            title='Ajax Chat',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='ajax_student', password='password123')

        response = self.client.post(
            reverse('document_chat_ask', args=[document.id]),
            {'question': 'Cfare ka dokumenti?'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['answer'], 'Pergjigje pa reload.')
        self.assertTrue(
            Activity.objects.filter(
                user=user,
                activity_type='chat',
                document_title='Ajax Chat'
            ).exists()
        )

    def test_document_study_shows_single_document_workspace(self):
        user = User.objects.create_user(
            username='study_student',
            password='password123'
        )
        path = self.create_pdf(text='Material per studio')
        document = Document.objects.create(
            title='Studio Leksion',
            file=path.name,
            uploaded_by=user,
            summary='Permbledhje e shkurter.'
        )
        self.client.login(username='study_student', password='password123')

        response = self.client.get(reverse('document_study', args=[document.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Study Workspace')
        self.assertContains(response, 'Dokumenti')
        self.assertContains(response, 'Summary')
        self.assertContains(response, 'Quiz')
        self.assertContains(response, 'Flashcards')
        self.assertContains(response, 'Chat AI')
        self.assertContains(response, reverse('document_file', args=[document.id]))

    @patch('documents.views.generate_quiz')
    def test_document_study_generates_quiz_inside_workspace(self, mock_generate_quiz):
        mock_generate_quiz.return_value = '''
        1. Cfare eshte databaza?
        A) Vend ku ruhen te dhenat
        B) Buton
        C) PDF
        D) Ngjyre
        Pergjigjja e sakte: A
        '''
        user = User.objects.create_user(
            username='study_quiz_student',
            password='password123'
        )
        path = self.create_pdf(text='Databaza ruan te dhenat')
        document = Document.objects.create(
            title='Databaza',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='study_quiz_student', password='password123')

        response = self.client.post(
            reverse('document_study', args=[document.id]),
            {
                'active_tab': 'quiz',
                'action': 'generate_quiz'
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cfare eshte databaza?')
        self.assertContains(response, 'Submit Quiz')
        self.assertTrue(
            Activity.objects.filter(
                user=user,
                activity_type='quiz',
                document_title='Databaza'
            ).exists()
        )

    @patch('documents.views.generate_flashcards')
    def test_document_study_flashcards_show_results_after_submit(self, mock_generate_flashcards):
        mock_generate_flashcards.return_value = '''
        1. Pyetje: Ku ruhen te dhenat?
           Pergjigje: Te dhenat ruhen ne databaze.
        '''
        user = User.objects.create_user(
            username='study_flash_student',
            password='password123'
        )
        path = self.create_pdf(text='Te dhenat ruhen ne databaze')
        document = Document.objects.create(
            title='Flash Studio',
            file=path.name,
            uploaded_by=user
        )
        self.client.login(username='study_flash_student', password='password123')

        self.client.post(
            reverse('document_study', args=[document.id]),
            {
                'active_tab': 'flashcards',
                'action': 'generate_flashcards'
            }
        )
        response = self.client.post(
            reverse('document_study', args=[document.id]),
            {
                'active_tab': 'flashcards',
                'action': 'submit_flashcards',
                'answer_0': 'Ne databaze'
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Pergjigjja jote')
        self.assertContains(response, 'Pergjigjja model')
        self.assertContains(response, 'Ne databaze')
        self.assertNotContains(response, 'Shkruaj pergjigjen tende...')

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
        self.assertContains(response, 'Grafiku i progresit')
        self.assertContains(response, 'Cfare duhet perseritur?')
