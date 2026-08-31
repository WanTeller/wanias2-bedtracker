"""
Top-level URL routing.

/admin/  -> Django's built-in admin site
everything else -> handled by the board app (board/urls.py)
"""

from django.contrib import admin
from django.contrib.auth.decorators import login_not_required
from django.urls import include, path
from django.views.generic import TemplateView

# Served from the site root so the service worker can control the whole app.
_manifest = login_not_required(TemplateView.as_view(
    template_name="manifest.webmanifest", content_type="application/manifest+json",
))
_sw = login_not_required(TemplateView.as_view(
    template_name="sw.js", content_type="application/javascript",
))

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("manifest.webmanifest", _manifest, name="manifest"),
    path("sw.js", _sw, name="service_worker"),
    path("", include("board.urls")),
]
