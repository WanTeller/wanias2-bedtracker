"""
We use Django's built-in User model (username == the person's email address,
email is unique). No custom user model - that keeps things simple and lets the
admin site work with zero extra code.

The one model here is LoginEvent: a developer-only audit trail of every login,
so the user registry shows more than just "last login".
"""

from django.conf import settings
from django.db import models


class LoginEvent(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="login_events",
    )
    at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-at"]

    def __str__(self):
        return f"{self.user} @ {self.at:%Y-%m-%d %H:%M}"
