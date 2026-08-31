from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views
from .forms import EmailLoginForm

# The real email+password login. Always defined; only wired to name="login"
# when SIMPLE_LOGIN is off. It also stays reachable at /accounts/password-login/
# so nothing is lost.
_real_login = auth_views.LoginView.as_view(
    template_name="accounts/login.html",
    authentication_form=EmailLoginForm,
    redirect_authenticated_user=True,
)

# /accounts/login/ (name="login") is what LOGIN_URL / the middleware use. It
# points at the simple name-only view in testing mode, or the real
# email+password view otherwise. Both views are ALSO always reachable at their
# own fixed URLs so nothing is ever removed.
_login_view = views.simple_login if settings.SIMPLE_LOGIN else _real_login

urlpatterns = [
    path("login/", _login_view, name="login"),
    path("password-login/", _real_login, name="password_login"),
    path("simple-login/", views.simple_login, name="simple_login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("signup/", views.signup, name="signup"),

    # Password change (while logged in)
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url="/accounts/password/change/done/",
        ),
        name="password_change",
    ),
    path(
        "password/change/done/",
        auth_views.PasswordChangeDoneView.as_view(
            template_name="accounts/password_change_done.html"
        ),
        name="password_change_done",
    ),

    # Password reset (forgotten password - emails a link; console email in dev)
    path(
        "password/reset/",
        auth_views.PasswordResetView.as_view(
            template_name="accounts/password_reset.html",
            email_template_name="accounts/password_reset_email.txt",
            success_url="/accounts/password/reset/sent/",
        ),
        name="password_reset",
    ),
    path(
        "password/reset/sent/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="accounts/password_reset_sent.html"
        ),
        name="password_reset_done",
    ),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="accounts/password_reset_confirm.html",
            success_url="/accounts/reset/done/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="accounts/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
]
