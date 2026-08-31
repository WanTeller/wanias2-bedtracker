from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import LoginEvent


def _client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


@receiver(user_logged_in)
def record_login(sender, request, user, **kwargs):
    LoginEvent.objects.create(
        user=user,
        ip_address=_client_ip(request) if request else None,
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:300] if request else ""),
    )
