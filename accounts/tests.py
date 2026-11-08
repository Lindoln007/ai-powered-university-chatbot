from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from core.testing import STRONG_PASSWORD, APITestBase

User = get_user_model()


class RegistrationTests(APITestBase):
    def payload(self, **overrides):
        data = {"username": "newstudent", "email": "New.Student@Example.com", "password": STRONG_PASSWORD,
                "password_confirm": STRONG_PASSWORD, "first_name": "New", "last_name": "Student"}
        data.update(overrides)
        return data

    def test_register_returns_token_and_hashes_password(self):
        response = self.client.post("/api/auth/register/", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="newstudent")
        self.assertEqual(response.data["token"], Token.objects.get(user=user).key)
        self.assertEqual(response.data["user"]["role"], "prospective_student")
        self.assertEqual(user.email, "new.student@example.com")
        self.assertNotEqual(user.password, STRONG_PASSWORD)
        self.assertTrue(user.password.startswith(("pbkdf2_", "argon2", "bcrypt", "scrypt")))
        self.assertNotIn("password", response.data["user"])

    def test_register_as_student(self):
        response = self.client.post("/api/auth/register/", self.payload(role="student"), format="json")
        self.assertEqual(response.data["user"]["role"], "student")

    def test_cannot_self_register_as_administrator(self):
        response = self.client.post("/api/auth/register/", self.payload(role="administrator"), format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(username="newstudent").exists())

    def test_validation_errors(self):
        self.make_user("taken")
        cases = [
            self.payload(password_confirm="Different-Pass-1"),
            self.payload(password="12345678", password_confirm="12345678"),
            self.payload(email="taken@example.com"),
            self.payload(username="taken"),
            self.payload(email="not-an-email"),
        ]
        for payload in cases:
            with self.subTest(payload=payload):
                response = self.client.post("/api/auth/register/", payload, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.data["error"]["code"], "validation_error")


class LoginLogoutTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user("carol")

    def test_login_with_username_or_email(self):
        for identifier in ["carol", "CAROL@example.com"]:
            response = self.client.post("/api/auth/login/", {"username": identifier, "password": STRONG_PASSWORD},
                                        format="json")
            self.assertEqual(response.status_code, 200, identifier)
            self.assertTrue(response.data["token"])
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)

    def test_wrong_password_is_rejected(self):
        response = self.client.post("/api/auth/login/", {"username": "carol", "password": "wrong"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("token", response.data)

    def test_inactive_user_cannot_log_in(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.post("/api/auth/login/", {"username": "carol", "password": STRONG_PASSWORD},
                                    format="json")
        self.assertEqual(response.status_code, 400)

    def test_logout_invalidates_token(self):
        self.authenticate(self.user)
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 200)
        self.assertFalse(Token.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 401)

    def test_login_is_rate_limited(self):
        statuses = [self.client.post("/api/auth/login/", {"username": "carol", "password": "wrong"},
                                     format="json").status_code for _ in range(11)]
        self.assertEqual(statuses[-1], 429)
        self.assertIn("retry_after_seconds", self.client.post(
            "/api/auth/login/", {"username": "carol", "password": "wrong"}, format="json").data["error"])


class ProfileTests(APITestBase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user("dave")
        self.authenticate(self.user)

    def test_profile_requires_authentication(self):
        self.logout_client()
        self.assertEqual(self.client.get("/api/auth/profile/").status_code, 401)

    def test_get_and_update_profile(self):
        response = self.client.get("/api/auth/profile/")
        self.assertEqual(response.data["username"], "dave")
        self.assertEqual(response.data["account_status"], "active")
        response = self.client.patch("/api/auth/profile/", {"first_name": "David", "role": "administrator"},
                                     format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "David")
        self.assertEqual(self.user.role, "student")  # role is read-only for users

    def test_password_change(self):
        response = self.client.post("/api/auth/password/change/",
                                    {"current_password": STRONG_PASSWORD, "new_password": "Another-Strong-Pass-9"},
                                    format="json")
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Another-Strong-Pass-9"))
        bad = self.client.post("/api/auth/password/change/",
                               {"current_password": "wrong", "new_password": "Another-Strong-Pass-9"}, format="json")
        self.assertIn(bad.status_code, (400, 401))


class RoleAndPermissionTests(APITestBase):
    def test_superuser_is_administrator(self):
        admin = User.objects.create_superuser("root", "root@example.com", STRONG_PASSWORD)
        self.assertEqual(admin.role, "administrator")
        self.assertTrue(admin.is_administrator)

    def test_administrator_role_grants_staff_access(self):
        admin = self.make_user("manager", role="administrator")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_administrator)

    def test_user_management_is_restricted_to_administrators(self):
        student = self.make_user("erin")
        self.authenticate(student)
        self.assertEqual(self.client.get("/api/auth/users/").status_code, 403)
        self.authenticate(self.make_user("manager", role="administrator"))
        self.assertEqual(self.client.get("/api/auth/users/").data["count"], 2)
        response = self.client.patch(f"/api/auth/users/{student.pk}/", {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 200)
        student.refresh_from_db()
        self.assertFalse(student.is_active)
