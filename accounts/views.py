from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_not_required
from django.shortcuts import redirect, render
from django.utils.text import slugify

from .forms import SignupForm, SimpleLoginForm

User = get_user_model()

# Testing-mode users are ordinary User rows with this username suffix and an
# unusable password, so they can never log in through the real form.
TEST_USER_SUFFIX = ".test@simple.local"


@login_not_required
def signup(request):
    """Self-service account creation: name + email + password."""
    if settings.SIMPLE_LOGIN:
        return redirect("login")   # signup is not needed in testing mode
    if request.user.is_authenticated:
        return redirect("home")

    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.create_user()
        login(request, user, backend="accounts.auth_backends.EmailBackend")
        return redirect("home")

    return render(request, "accounts/signup.html", {"form": form})


def get_or_create_testing_user(name):
    """One testing user per (normalised) name, so the same person is recognised
    across sessions and shows a consistent identity in the activity log."""
    name = " ".join(name.split())[:120]
    slug = slugify(name) or "tester"
    username = f"{slug}{TEST_USER_SUFFIX}"
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"email": username, "first_name": name, "is_active": True},
    )
    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
    elif user.first_name != name:
        user.first_name = name          # keep capitalisation fresh
        user.save(update_fields=["first_name"])
    return user


@login_not_required
def simple_login(request):
    """Testing mode: enter a name, click through to the board."""
    if not settings.SIMPLE_LOGIN:
        return redirect("login")
    if request.user.is_authenticated:
        return redirect("home")

    form = SimpleLoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = get_or_create_testing_user(form.cleaned_data["name"])
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        return redirect("home")

    return render(request, "accounts/simple_login.html", {"form": form})
