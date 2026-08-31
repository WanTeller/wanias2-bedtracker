"""
Enforce "one account per email address" at the database level.

We normalise existing emails to lower-case, fail loudly if any real duplicates
exist, then add a partial unique index (blank emails - e.g. a superuser created
without one - are ignored). Works on both SQLite and PostgreSQL.
"""

from django.db import migrations


def normalise_and_check(apps, schema_editor):
    User = apps.get_model("auth", "User")
    for user in User.objects.exclude(email=""):
        low = user.email.strip().lower()
        if low != user.email:
            user.email = low
            user.save(update_fields=["email"])

    seen = {}
    for user in User.objects.exclude(email=""):
        seen.setdefault(user.email, []).append(user.pk)
    dupes = {e: ids for e, ids in seen.items() if len(ids) > 1}
    if dupes:
        raise RuntimeError(
            f"Cannot enforce unique emails - duplicates already exist: {dupes}. "
            "Fix these in the admin, then re-run migrate."
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(normalise_and_check, migrations.RunPython.noop),
        migrations.RunSQL(
            sql=(
                "CREATE UNIQUE INDEX IF NOT EXISTS accounts_user_email_unique "
                "ON auth_user (email) WHERE email <> '';"
            ),
            reverse_sql="DROP INDEX IF EXISTS accounts_user_email_unique;",
        ),
    ]
