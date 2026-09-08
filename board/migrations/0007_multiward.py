"""
Multi-board groundwork.

Adds:
  - Ward.slug / .invite_token / .created_by / .created_at
  - WardMembership (who belongs to which board)
  - TaskOption.ward   (custom buttons belong to one board; defaults stay shared)
  - ActivityEvent.ward (so each board's activity feed is one quick query)

Then it back-fills the one board that already exists: gives it a slug and an
invite token, ties its existing custom buttons and activity events to it, and
makes every current account a member (superusers become owners).

No behaviour changes yet - the app still shows the single board to everyone.
"""

import secrets

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.utils.text import slugify

import board.models


def backfill(apps, schema_editor):
    Ward = apps.get_model("board", "Ward")
    WardMembership = apps.get_model("board", "WardMembership")
    TaskOption = apps.get_model("board", "TaskOption")
    ActivityEvent = apps.get_model("board", "ActivityEvent")
    User = apps.get_model(settings.AUTH_USER_MODEL)

    for ward in Ward.objects.all().order_by("id"):
        changed = False
        if not ward.slug:
            base = slugify(ward.name) or "ward"
            slug, n = base, 2
            while Ward.objects.exclude(pk=ward.pk).filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            ward.slug = slug
            changed = True
        if not ward.invite_token:
            ward.invite_token = secrets.token_urlsafe(9)
            changed = True
        if changed:
            ward.save()

    home = Ward.objects.order_by("id").first()
    if home is None:
        return   # fresh database (e.g. the test runner): nothing to back-fill

    TaskOption.objects.filter(ward__isnull=True, is_custom=True).update(ward=home)
    ActivityEvent.objects.filter(ward__isnull=True).update(ward=home)

    for user in User.objects.all():
        WardMembership.objects.get_or_create(
            ward=home,
            user=user,
            defaults={
                "role": "owner" if user.is_superuser else "member",
                "display_name": (user.first_name or user.email or "")[:80],
            },
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("board", "0006_activityevent_actor_alter_activityevent_kind_and_more"),
    ]

    operations = [
        # --- new Ward columns (nullable / defaulted so existing rows are fine)
        migrations.AddField(
            model_name="ward",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AddField(
            model_name="ward",
            name="created_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="wards_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="ward",
            name="slug",
            field=models.SlugField(max_length=60, null=True),
        ),
        migrations.AddField(
            model_name="ward",
            name="invite_token",
            field=models.CharField(max_length=32, null=True),
        ),
        # --- new membership table
        migrations.CreateModel(
            name="WardMembership",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        choices=[("owner", "Owner"), ("member", "Member")],
                        default="member",
                        max_length=10,
                    ),
                ),
                ("display_name", models.CharField(blank=True, max_length=80)),
                (
                    "joined_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "ward",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="board.ward",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ward_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["ward", "display_name"]},
        ),
        migrations.AddConstraint(
            model_name="wardmembership",
            constraint=models.UniqueConstraint(
                fields=["ward", "user"], name="unique_ward_membership"
            ),
        ),
        # --- ward links on the child tables
        migrations.AddField(
            model_name="taskoption",
            name="ward",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="task_options",
                to="board.ward",
            ),
        ),
        migrations.AddField(
            model_name="activityevent",
            name="ward",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="events",
                to="board.ward",
            ),
        ),
        migrations.RemoveConstraint(
            model_name="taskoption",
            name="unique_option_per_category",
        ),
        migrations.AddConstraint(
            model_name="taskoption",
            constraint=models.UniqueConstraint(
                fields=["category", "label", "ward"],
                name="unique_option_per_category_ward",
            ),
        ),
        # --- back-fill, then tighten slug / invite_token to their final shape
        migrations.RunPython(backfill, noop),
        migrations.AlterField(
            model_name="ward",
            name="slug",
            field=models.SlugField(max_length=60, unique=True),
        ),
        migrations.AlterField(
            model_name="ward",
            name="invite_token",
            field=models.CharField(
                default=board.models._new_invite_token,
                max_length=32,
                unique=True,
            ),
        ),
    ]
