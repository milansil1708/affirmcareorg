from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse

from provider_organizations.models import ProviderOrganization
from users.admin import UserAdmin
from users.forms import UserAdminCreationForm


User = get_user_model()


class UserManagerTests(TestCase):
    def test_create_superuser_uses_super_admin_account_type(self):
        user = User.objects.create_superuser(
            email="admin@example.com",
            password="A-secure-password-2026",
        )

        self.assertEqual(user.account_type, User.AccountType.SUPER_ADMIN)
        self.assertEqual(user.username, user.email)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

    def test_admin_creation_form_uses_custom_user_model(self):
        request = RequestFactory().get("/admin/users/user/add/")
        model_admin = UserAdmin(User, AdminSite())

        form_class = model_admin.get_form(request)

        self.assertTrue(issubclass(form_class, UserAdminCreationForm))
        self.assertIs(form_class._meta.model, User)


class AuthenticationViewTests(TestCase):
    password = "A-secure-password-2026"

    def test_register_creates_provider_and_shows_success_toast(self):
        response = self.client.post(
            reverse("users:register"),
            {
                "email": "provider@example.com",
                "password1": self.password,
                "password2": self.password,
            },
            follow=True,
        )

        user = User.objects.get(email="provider@example.com")
        self.assertEqual(user.account_type, User.AccountType.PROVIDER)
        self.assertTrue(user.check_password(self.password))
        self.assertRedirects(response, reverse("users:login"))
        self.assertContains(response, "Registration successful")
        self.assertContains(response, "auth-toast-success")

    def test_multiple_provider_accounts_get_unique_compatibility_usernames(self):
        for email in ["first@example.com", "second@example.com"]:
            response = self.client.post(
                reverse("users:register"),
                {
                    "email": email,
                    "password1": self.password,
                    "password2": self.password,
                },
            )
            self.assertRedirects(response, reverse("users:login"))

        self.assertEqual(
            list(
                User.objects.filter(email__contains="@example.com")
                .order_by("email")
                .values_list("username", flat=True)
            ),
            ["first@example.com", "second@example.com"],
        )

    def test_register_shows_field_error_and_error_toast(self):
        response = self.client.post(
            reverse("users:register"),
            {
                "email": "provider@example.com",
                "password1": self.password,
                "password2": "Different-password-2026",
            },
        )

        self.assertFalse(User.objects.filter(email="provider@example.com").exists())
        self.assertContains(response, "The two password fields do not match.")
        self.assertContains(response, "Registration failed")
        self.assertContains(response, "auth-toast-error")

    def test_login_authenticates_with_email_without_success_toast(self):
        User.objects.create_user(
            email="provider@example.com",
            password=self.password,
        )

        response = self.client.post(
            reverse("users:login"),
            {"email": "provider@example.com", "password": self.password},
            follow=True,
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(
            str(self.client.session.get("_auth_user_id")),
            str(User.objects.get(email="provider@example.com").pk),
        )
        self.assertNotContains(response, "auth-toast")

    def test_login_explains_that_the_portal_is_for_providers(self):
        response = self.client.get(reverse("users:login"))

        self.assertContains(
            response,
            "This secure portal is for healthcare providers and their teams.",
        )
        self.assertContains(response, "You do not need an account to search")
        self.assertContains(response, 'href="/#provider-search"')

    def test_failed_login_shows_form_error_and_error_toast(self):
        response = self.client.post(
            reverse("users:login"),
            {"email": "provider@example.com", "password": "wrong-password"},
        )

        self.assertContains(
            response,
            "The email or password you entered is incorrect.",
        )
        self.assertContains(response, "Login failed")
        self.assertContains(response, "auth-toast-error")

    def test_header_shows_login_link_for_anonymous_user(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, reverse("users:login"))
        self.assertNotContains(response, ">Organization</div>")
        self.assertNotContains(response, ">Blogs</div>")

    def test_header_shows_organization_and_logout_for_authenticated_user(self):
        user = User.objects.create_user(
            email="provider@example.com",
            password=self.password,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertContains(response, ">Organization</div>")
        self.assertNotContains(response, ">Blogs</div>")
        self.assertContains(response, reverse("provider_account"))
        self.assertNotContains(response, "provider@example.com")
        self.assertNotContains(response, "profile-menu")
        self.assertContains(response, reverse("users:logout"))
        self.assertContains(response, "logout-menu-button")

    def test_logout_requires_post_and_ends_session(self):
        user = User.objects.create_user(
            email="provider@example.com",
            password=self.password,
        )
        self.client.force_login(user)

        get_response = self.client.get(reverse("users:logout"))
        self.assertEqual(get_response.status_code, 405)

        post_response = self.client.post(reverse("users:logout"))
        self.assertRedirects(post_response, reverse("home"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_provider_organization_user_is_optional(self):
        organization = ProviderOrganization.objects.create(
            name="Affirming Health",
            org_type="clinic",
            description="Provider description",
            phone="555-0100",
            email="care@example.com",
        )

        self.assertIsNone(organization.user)
