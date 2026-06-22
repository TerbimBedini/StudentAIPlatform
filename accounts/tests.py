from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from documents.models import Document, QuizAttempt


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
