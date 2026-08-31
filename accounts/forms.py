from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class EmailLoginForm(AuthenticationForm):
    """Same as Django's login form but the first field is labelled 'Email'."""
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )


class SignupForm(forms.Form):
    name = forms.CharField(
        label="Your name", max_length=120,
        widget=forms.TextInput(attrs={"autofocus": True}),
        help_text="Shown on the activity log next to actions you take.",
    )
    email = forms.EmailField(label="Email", max_length=150)
    password1 = forms.CharField(
        label="Password", widget=forms.PasswordInput,
        help_text="At least 8 characters; not all numbers or a common password.",
    )
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput)

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        # One email -> one account. Only an admin can reassign an email.
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account with this email already exists. Try logging in, or "
                "ask the administrator if you need it changed."
            )
        return email

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        if p1:
            # Attach password-strength errors to the password field so they
            # actually show up on the form (raising here would hide them as a
            # non-field error).
            try:
                validate_password(
                    p1, User(username=data.get("email", ""),
                             email=data.get("email", "")),
                )
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return data

    def create_user(self):
        d = self.cleaned_data
        user = User(username=d["email"], email=d["email"], first_name=d["name"])
        user.set_password(d["password1"])
        user.save()
        return user


class SimpleLoginForm(forms.Form):
    """Testing mode only: just a name, no email/password."""
    name = forms.CharField(
        label="Your name", max_length=120,
        widget=forms.TextInput(attrs={"autofocus": True,
                                      "placeholder": "e.g. Wania Khan"}),
    )

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if not name:
            raise forms.ValidationError("Please enter your name.")
        return name
