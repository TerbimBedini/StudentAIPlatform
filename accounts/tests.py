from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from documents.achievements import check_and_award_achievements, get_achievement_progress
from documents.analytics import get_dashboard_analytics
from documents.models import (
    Achievement,
    CommunityMessage,
    Document,
    FlashcardAttempt,
    Notification,
    QuizAttempt,
    LibraryDocument,
    StudySession,
)


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
        self.assertContains(response, 'StudentAI Command Center')
        self.assertContains(response, 'Learning Snapshot')
        self.assertContains(response, 'Recommended Next Step')
        self.assertContains(response, 'Quick Navigation')
        self.assertContains(response, 'Knowledge Score')
        self.assertContains(response, 'Exam Readiness')
        self.assertContains(response, 'Study Streak')
        self.assertContains(response, 'Quiz Accuracy')
        self.assertContains(response, 'Upload your first document')
        self.assertContains(response, 'Advanced Analytics')
        self.assertContains(response, 'Analytics Visuals')
        self.assertContains(response, 'id="dashboard-analytics-data"')
        self.assertContains(response, 'Weekly Study Hours')
        self.assertContains(response, 'No quiz history yet.')
        self.assertContains(response, 'No weak topics detected yet.')
        self.assertNotContains(response, '<article class="glass-card document-card"')

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
        self.assertContains(response, 'StudentAI Command Center')
        self.assertContains(response, 'Learning Snapshot')
        self.assertContains(response, 'Recommended Next Step')
        self.assertContains(response, 'Quick Navigation')
        self.assertContains(response, 'Advanced Analytics')
        self.assertContains(response, 'Analytics Visuals')
        self.assertContains(response, 'id="dashboard-analytics-data"')
        self.assertContains(response, 'id="quizAccuracyChart"')
        self.assertContains(response, 'id="weakTopicsChart"')
        self.assertContains(response, 'id="strongTopicsChart"')
        self.assertContains(response, 'Flashcard Success')
        self.assertContains(response, 'Probability - 40.0%')
        self.assertContains(response, 'Algorithms - 100.0%')
        self.assertNotContains(response, '<article class="glass-card document-card"')

    def test_first_upload_achievement_is_awarded(self):
        user = User.objects.create_user(
            username='achievement_upload',
            password='StrongPass123!'
        )
        Document.objects.create(
            title='First Notes',
            file='documents/first.pdf',
            uploaded_by=user
        )

        awarded = check_and_award_achievements(user)

        self.assertTrue(any(item.badge_type == 'first_upload' for item in awarded))
        self.assertTrue(
            Achievement.objects.filter(
                user=user,
                badge_type='first_upload'
            ).exists()
        )

    def test_first_quiz_and_perfect_quiz_achievements_are_awarded(self):
        user = User.objects.create_user(
            username='achievement_quiz',
            password='StrongPass123!'
        )
        document = Document.objects.create(
            title='Quiz Notes',
            file='documents/quiz.pdf',
            uploaded_by=user
        )
        QuizAttempt.objects.create(
            document=document,
            user=user,
            score=5,
            total=5
        )

        check_and_award_achievements(user)

        self.assertTrue(
            Achievement.objects.filter(
                user=user,
                badge_type='first_quiz'
            ).exists()
        )
        self.assertTrue(
            Achievement.objects.filter(
                user=user,
                badge_type='perfect_quiz'
            ).exists()
        )

    def test_achievements_are_not_duplicated(self):
        user = User.objects.create_user(
            username='achievement_no_duplicates',
            password='StrongPass123!'
        )
        Document.objects.create(
            title='Duplicate Notes',
            file='documents/duplicate.pdf',
            uploaded_by=user
        )

        check_and_award_achievements(user)
        check_and_award_achievements(user)

        self.assertEqual(
            Achievement.objects.filter(
                user=user,
                badge_type='first_upload'
            ).count(),
            1
        )

    def test_dashboard_renders_achievement_progress(self):
        user = User.objects.create_user(
            username='achievement_dashboard',
            password='StrongPass123!'
        )
        Document.objects.create(
            title='Dashboard Badge Notes',
            file='documents/dashboard-badge.pdf',
            uploaded_by=user
        )
        self.client.login(
            username='achievement_dashboard',
            password='StrongPass123!'
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Achievements')
        self.assertContains(response, 'First Upload')
        self.assertContains(response, 'Earned')
        self.assertTrue(get_achievement_progress(user))

    def test_dashboard_renders_community_and_library_shortcuts_without_full_previews(self):
        user = User.objects.create_user(
            username='dashboard_community',
            password='StrongPass123!'
        )
        uploader = User.objects.create_user(
            username='dashboard_library_uploader',
            password='StrongPass123!'
        )
        CommunityMessage.objects.create(
            user=uploader,
            field=LibraryDocument.FIELD_COMPUTER_SCIENCE,
            kind=CommunityMessage.KIND_DISCUSSION,
            title='Study group tonight',
            message='We are reviewing algorithms exercises.'
        )
        LibraryDocument.objects.create(
            title='Shared Algorithms Notes',
            field=LibraryDocument.FIELD_COMPUTER_SCIENCE,
            document_type=LibraryDocument.TYPE_NOTES,
            course_name='Algorithms',
            description='Sorting and graphs notes.',
            file='library/shared-algorithms.pdf',
            uploaded_by=uploader,
            moderation_status=LibraryDocument.STATUS_APPROVED,
            is_public=True
        )
        self.client.login(
            username='dashboard_community',
            password='StrongPass123!'
        )

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quick Navigation')
        self.assertContains(response, 'Community')
        self.assertContains(response, 'AI Library')
        self.assertContains(response, reverse('community_chat'))
        self.assertContains(response, reverse('library_home'))
        self.assertNotContains(response, 'Study group tonight')
        self.assertNotContains(response, 'Shared Algorithms Notes')

    def test_sidebar_navigation_is_clear_for_new_user_without_documents(self):
        user = User.objects.create_user(
            username='nav_empty',
            password='StrongPass123!'
        )
        Notification.objects.create(
            user=user,
            title='Welcome to StudentAI',
            message='Your AI study coach is ready.',
            notification_type=Notification.TYPE_AI_RECOMMENDATION
        )
        self.client.login(username='nav_empty', password='StrongPass123!')

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Multi-Doc AI')
        self.assertContains(response, 'Ask questions across multiple documents.')
        self.assertContains(response, 'Quiz History')
        self.assertContains(response, 'Flashcard History')
        self.assertContains(response, 'AI Tutor')
        self.assertContains(response, 'Exam Simulator')
        self.assertContains(response, 'AI Tutor: upload a document first')
        self.assertContains(response, reverse('upload_document'))
        self.assertContains(response, 'Notifications')
        self.assertContains(response, 'Your AI study coach is ready.')
        self.assertNotContains(response, '<button class="notification-btn"')

    def test_sidebar_navigation_links_document_tools_for_existing_user(self):
        user = User.objects.create_user(
            username='nav_document',
            password='StrongPass123!'
        )
        document = Document.objects.create(
            title='Navigation Notes',
            file='documents/navigation.pdf',
            uploaded_by=user,
            summary='Navigation summary.'
        )
        self.client.login(username='nav_document', password='StrongPass123!')

        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'AI Tutor: learn with one selected document in Study Mode')
        self.assertContains(response, reverse('study_document', args=[document.id]))
        self.assertContains(response, 'Exam Simulator: start a mock exam for your recommended document')
        self.assertContains(response, reverse('exam_simulator', args=[document.id]))
        self.assertContains(response, reverse('quiz_history'))
        self.assertContains(response, reverse('flashcard_history'))
