from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from documents.analytics import get_dashboard_analytics
from documents.models import Document, FlashcardAttempt, QuizAttempt, StudySession


class AuthenticationSecurityTests(TestCase):
    def test_authenticated_user_is_redirected_from_login_and_register(self):
        User.objects.create_user(
            username='secure_student',
            password='StrongPass123!'
        )
        self.client.login(
            username='secure_student',
            password='StrongPass123!'
        )

        login_response = self.client.get(reverse('login'))
        register_response = self.client.get(reverse('register'))

        self.assertRedirects(login_response, reverse('dashboard'))
        self.assertRedirects(register_response, reverse('dashboard'))

    def test_logout_requires_post(self):
        User.objects.create_user(
            username='logout_student',
            password='StrongPass123!'
        )
        self.client.login(
            username='logout_student',
            password='StrongPass123!'
        )

        get_response = self.client.get(reverse('logout'))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse('logout'))
        self.assertRedirects(post_response, reverse('home'))

    def test_study_plan_requires_documents(self):
        User.objects.create_user(
            username='plan_empty',
            password='StrongPass123!'
        )
        self.client.login(
            username='plan_empty',
            password='StrongPass123!'
        )

        response = self.client.get(reverse('study_plan'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Upload documents first to generate your study plan.'
        )

    def test_study_plan_shows_timeline_and_weak_areas(self):
        user = User.objects.create_user(
            username='plan_student',
            password='StrongPass123!'
        )
        document = Document.objects.create(
            title='Calculus',
            file='documents/calculus.pdf',
            uploaded_by=user,
            summary='Limits and derivatives summary.'
        )
        QuizAttempt.objects.create(
            document=document,
            user=user,
            score=5,
            total=10
        )
        self.client.login(
            username='plan_student',
            password='StrongPass123!'
        )

        response = self.client.get(reverse('study_plan'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Study Plan')
        self.assertContains(response, 'Knowledge Score')
        self.assertContains(response, 'Calculus - 50.0%')
        self.assertContains(response, 'Day 1: Review weak areas')
        self.assertContains(response, 'Day 7: Final quiz and review')
        self.assertContains(
            response,
            reverse('start_study_session', args=[document.id])
        )

    def test_exam_preparation_handles_user_without_history(self):
        User.objects.create_user(
            username='exam_empty',
            password='StrongPass123!'
        )
        self.client.login(
            username='exam_empty',
            password='StrongPass123!'
        )

        response = self.client.get(reverse('exam_preparation'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Exam Preparation Center')
        self.assertContains(response, 'Predicted Exam Score')
        self.assertContains(response, 'HIGH')
        self.assertContains(response, 'Upload your first document')

    def test_exam_preparation_shows_exam_simulator_action(self):
        user = User.objects.create_user(
            username='exam_ready_student',
            password='StrongPass123!'
        )
        document = Document.objects.create(
            title='Physics',
            file='documents/physics.pdf',
            uploaded_by=user,
            summary='Motion and forces summary.'
        )
        QuizAttempt.objects.create(
            document=document,
            user=user,
            score=8,
            total=10
        )
        self.client.login(
            username='exam_ready_student',
            password='StrongPass123!'
        )

        response = self.client.get(reverse('exam_preparation'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Start Exam Simulator')
        self.assertContains(response, reverse('exam_simulator', args=[document.id]))
        self.assertContains(response, 'Physics')

    def test_dashboard_analytics_returns_expected_keys_for_new_user(self):
        user = User.objects.create_user(
            username='analytics_empty',
            password='StrongPass123!'
        )

        analytics = get_dashboard_analytics(user)

        self.assertEqual(
            set(analytics.keys()),
            {
                'weekly_study_hours',
                'monthly_progress',
                'quiz_accuracy_trend',
                'flashcard_success_rate',
                'knowledge_growth',
                'exam_readiness_trend',
                'weak_topics_chart',
                'strong_topics_chart',
                'learning_streak',
            }
        )
        self.assertEqual(analytics['weekly_study_hours'], 0)
        self.assertEqual(analytics['quiz_accuracy_trend']['current'], 0)
        self.assertEqual(analytics['flashcard_success_rate']['current'], 0)

    def test_dashboard_renders_advanced_analytics_for_new_user(self):
        User.objects.create_user(
            username='dashboard_analytics_empty',
            password='StrongPass123!'
        )
        self.client.login(
            username='dashboard_analytics_empty',
            password='StrongPass123!'
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Advanced Analytics')
        self.assertContains(response, 'Weekly Study Hours')
        self.assertContains(response, 'No weak topics detected yet.')

    def test_dashboard_renders_advanced_analytics_with_activity(self):
        user = User.objects.create_user(
            username='dashboard_analytics_active',
            password='StrongPass123!'
        )
        weak_document = Document.objects.create(
            title='Probability',
            file='documents/probability.pdf',
            uploaded_by=user,
            summary='Probability summary.'
        )
        strong_document = Document.objects.create(
            title='Algorithms',
            file='documents/algorithms.pdf',
            uploaded_by=user,
            summary='Algorithms summary.'
        )
        QuizAttempt.objects.create(
            document=weak_document,
            user=user,
            score=2,
            total=5
        )
        QuizAttempt.objects.create(
            document=strong_document,
            user=user,
            score=5,
            total=5
        )
        FlashcardAttempt.objects.create(
            document=strong_document,
            user=user,
            average_score=90,
            category='Shume mire'
        )
        StudySession.objects.create(
            document=strong_document,
            user=user,
            status=StudySession.STATUS_COMPLETED,
            completed_at=timezone.now()
        )
        self.client.login(
            username='dashboard_analytics_active',
            password='StrongPass123!'
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Advanced Analytics')
        self.assertContains(response, 'Flashcard Success')
        self.assertContains(response, 'Probability - 40.0%')
        self.assertContains(response, 'Algorithms - 100.0%')
