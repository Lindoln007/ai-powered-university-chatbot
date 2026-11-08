from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user built on Django's authentication system.

    Django provides the id, username, hashed password, names, `is_active`
    (account status), `date_joined` (created date) and `last_login` fields.
    """

    class Role(models.TextChoices):
        ADMINISTRATOR = "administrator", "Administrator"
        STUDENT = "student", "Student"
        PROSPECTIVE_STUDENT = "prospective_student", "Prospective Student"
        GUEST = "guest", "Guest"

    SELF_REGISTRATION_ROLES = (Role.STUDENT, Role.PROSPECTIVE_STUDENT)

    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.PROSPECTIVE_STUDENT, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ["username"]

    def save(self, *args, **kwargs):
        if self.is_superuser:
            self.role = self.Role.ADMINISTRATOR
        if self.role == self.Role.ADMINISTRATOR:
            # Administrators manage the knowledge base through Django Admin.
            self.is_staff = True
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def is_administrator(self) -> bool:
        return self.is_active and (self.is_superuser or self.role == self.Role.ADMINISTRATOR)

    def __str__(self):
        return self.username
