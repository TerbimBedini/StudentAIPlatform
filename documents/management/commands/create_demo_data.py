from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from documents.models import (
    Achievement,
    Activity,
    CommunityMessage,
    Document,
    FlashcardAttempt,
    LibraryDocument,
    Notification,
    QuizAttempt,
    StudySession,
)


DEMO_USERNAME = 'demo'
DEMO_PASSWORD = 'demo12345'


class Command(BaseCommand):
    help = 'Create realistic local demo data for StudentAI v1.0 without requiring Ollama.'

    def handle(self, *args, **options):
        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={
                'email': 'demo@studentai.local',
                'first_name': 'Demo',
                'last_name': 'Student',
            },
        )
        user.set_password(DEMO_PASSWORD)
        user.email = 'demo@studentai.local'
        user.first_name = 'Demo'
        user.last_name = 'Student'
        user.save()

        documents = self._create_documents(user)
        self._create_quiz_attempts(user, documents)
        self._create_flashcard_attempts(user, documents)
        self._create_study_sessions(user, documents)
        self._create_achievements(user)
        self._create_activity(user, documents)
        self._create_notifications(user)
        self._create_community(user)
        self._create_library(user)

        status = 'created' if created else 'updated'
        self.stdout.write(
            self.style.SUCCESS(
                f'Demo data {status}. Login with username "{DEMO_USERNAME}" and password "{DEMO_PASSWORD}".'
            )
        )

    def _create_documents(self, user):
        samples = [
            {
                'title': 'Demo - Machine Learning Basics',
                'file': 'documents/demo_machine_learning_basics.pdf',
                'summary': (
                    'Machine learning uses data to train models that identify patterns, '
                    'make predictions, and improve through evaluation.'
                ),
                'extracted_text': (
                    'Machine learning is a field of artificial intelligence focused on learning '
                    'patterns from data. Supervised learning uses labeled examples, while '
                    'unsupervised learning finds hidden structure. Common evaluation metrics '
                    'include accuracy, precision, recall, and F1 score. Overfitting happens when '
                    'a model memorizes training data and performs poorly on new examples.'
                ),
            },
            {
                'title': 'Demo - Probability and Statistics',
                'file': 'documents/demo_probability_statistics.pdf',
                'summary': (
                    'Probability measures uncertainty, while statistics uses data to estimate, '
                    'compare, and reason about real-world outcomes.'
                ),
                'extracted_text': (
                    'Probability describes how likely events are. Conditional probability measures '
                    'the chance of an event when another event is known. Bayes theorem updates '
                    'beliefs using evidence. Statistics summarizes samples with mean, median, '
                    'variance, and standard deviation. Confidence intervals express uncertainty '
                    'around an estimate.'
                ),
            },
            {
                'title': 'Demo - Database Systems',
                'file': 'documents/demo_database_systems.pdf',
                'summary': (
                    'Databases store structured data and use queries, keys, relationships, and '
                    'normalization to keep information organized.'
                ),
                'extracted_text': (
                    'A relational database stores data in tables. Primary keys identify rows, '
                    'foreign keys connect related tables, and SQL is used to query data. '
                    'Normalization reduces duplication and improves consistency. Indexes can '
                    'speed up reads, but may slow down writes. Transactions protect data using '
                    'atomicity, consistency, isolation, and durability.'
                ),
            },
        ]

        documents = []
        for sample in samples:
            document, _ = Document.objects.update_or_create(
                uploaded_by=user,
                title=sample['title'],
                defaults={
                    'file': sample['file'],
                    'summary': sample['summary'],
                    'extracted_text': sample['extracted_text'],
                    'summary_status': Document.STATUS_COMPLETED,
                    'quiz_status': Document.STATUS_COMPLETED,
                    'flashcards_status': Document.STATUS_COMPLETED,
                    'ai_processed': True,
                    'processing_error': '',
                },
            )
            documents.append(document)

        return documents

    def _create_quiz_attempts(self, user, documents):
        attempts = [
            (documents[0], 5, 5, 'Excellent', []),
            (documents[1], 2, 5, 'Needs Review', [
                {
                    'number': 2,
                    'question': 'What does conditional probability measure?',
                    'selected': 'A',
                    'answer': 'C',
                }
            ]),
            (documents[2], 4, 5, 'Strong', []),
        ]

        for document, score, total, category, mistakes in attempts:
            QuizAttempt.objects.update_or_create(
                user=user,
                document=document,
                category=f'Demo {category}',
                defaults={
                    'score': score,
                    'total': total,
                    'mistakes': mistakes,
                },
            )

    def _create_flashcard_attempts(self, user, documents):
        attempts = [
            (documents[0], 92.0, 'Shume mire'),
            (documents[1], 58.5, 'Duhet perseritur'),
            (documents[2], 84.0, 'Shume mire'),
        ]

        for document, average_score, category in attempts:
            FlashcardAttempt.objects.update_or_create(
                user=user,
                document=document,
                category=f'Demo {category}',
                defaults={
                    'average_score': average_score,
                    'cards': [
                        {
                            'question': f'What is the key idea in {document.title}?',
                            'answer': document.summary or 'Review the summary.',
                            'user_answer': 'Demo answer',
                        }
                    ],
                },
            )

    def _create_study_sessions(self, user, documents):
        now = timezone.now()
        for index, document in enumerate(documents):
            StudySession.objects.update_or_create(
                user=user,
                document=document,
                status=StudySession.STATUS_COMPLETED,
                defaults={
                    'completed_at': now - timedelta(days=index),
                    'quiz_score': 4 if index != 1 else 2,
                    'total_questions': 5,
                    'session_score': 88 if index != 1 else 62,
                },
            )

    def _create_achievements(self, user):
        achievements = [
            (
                Achievement.BADGE_FIRST_UPLOAD,
                'First Upload',
                'Uploaded the first study document.',
            ),
            (
                Achievement.BADGE_FIRST_QUIZ,
                'First Quiz',
                'Completed the first quiz attempt.',
            ),
            (
                Achievement.BADGE_QUIZ_MASTER,
                'Quiz Master',
                'Scored perfectly on a demo quiz.',
            ),
        ]

        for badge_type, title, description in achievements:
            Achievement.objects.update_or_create(
                user=user,
                badge_type=badge_type,
                defaults={
                    'title': title,
                    'description': description,
                },
            )

    def _create_activity(self, user, documents):
        for activity_type, document in [
            ('summary', documents[0]),
            ('chat', documents[0]),
            ('quiz', documents[1]),
            ('flashcards', documents[2]),
        ]:
            Activity.objects.update_or_create(
                user=user,
                activity_type=activity_type,
                document_title=document.title,
                defaults={},
            )

    def _create_notifications(self, user):
        notifications = [
            (
                'Welcome to StudentAI',
                'Your AI study coach is ready for the demo.',
                Notification.TYPE_SUCCESS,
                False,
            ),
            (
                'Weak topic detected',
                'Probability needs more practice. Review flashcards and try another quiz.',
                Notification.TYPE_AI_RECOMMENDATION,
                False,
            ),
            (
                'Exam simulator ready',
                'You have enough activity to try a mock exam.',
                Notification.TYPE_REMINDER,
                True,
            ),
        ]

        for title, message, notification_type, is_read in notifications:
            Notification.objects.update_or_create(
                user=user,
                title=title,
                defaults={
                    'message': message,
                    'notification_type': notification_type,
                    'is_read': is_read,
                },
            )

    def _create_community(self, user):
        messages = [
            (
                LibraryDocument.FIELD_COMPUTER_SCIENCE,
                CommunityMessage.KIND_DISCUSSION,
                'Tips for database normalization',
                'I am reviewing keys, relationships, and normalization examples before the exam.',
            ),
            (
                LibraryDocument.FIELD_SCIENCE,
                CommunityMessage.KIND_REQUEST,
                'Probability practice questions',
                'Does anyone have extra probability exercises with conditional probability?',
            ),
        ]

        for field, kind, title, message in messages:
            CommunityMessage.objects.update_or_create(
                user=user,
                title=title,
                defaults={
                    'field': field,
                    'kind': kind,
                    'message': message,
                    'is_hidden': False,
                },
            )

    def _create_library(self, user):
        samples = [
            {
                'title': 'Demo Shared ML Notes',
                'field': LibraryDocument.FIELD_COMPUTER_SCIENCE,
                'document_type': LibraryDocument.TYPE_NOTES,
                'course_name': 'Artificial Intelligence',
                'academic_year': '2026',
                'description': 'Approved demo notes covering machine learning basics.',
                'file': 'library/demo_shared_ml_notes.pdf',
            },
            {
                'title': 'Demo Probability Exam Review',
                'field': LibraryDocument.FIELD_SCIENCE,
                'document_type': LibraryDocument.TYPE_EXAM,
                'course_name': 'Statistics',
                'academic_year': '2026',
                'description': 'Approved demo resource for probability exam preparation.',
                'file': 'library/demo_probability_exam_review.pdf',
            },
        ]

        for sample in samples:
            LibraryDocument.objects.update_or_create(
                uploaded_by=user,
                title=sample['title'],
                defaults={
                    **sample,
                    'moderation_status': LibraryDocument.STATUS_APPROVED,
                    'is_public': True,
                    'reviewed_by': user,
                    'reviewed_at': timezone.now(),
                    'moderation_notes': 'Approved demo resource.',
                    'safety_scan_notes': 'Demo data created locally.',
                },
            )
