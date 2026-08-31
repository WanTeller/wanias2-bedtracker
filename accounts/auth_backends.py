"""
Let people log in with their email address + password.

We store the email in User.username (and User.email), so this backend just
looks the user up by email, case-insensitively, and checks the password.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

User = get_user_model()


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        email = (username or kwargs.get("email") or "").strip()
        if not email or password is None:
            return None
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Run the default hasher once to blunt timing attacks.
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            user = User.objects.filter(email__iexact=email).order_by("id").first()
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
