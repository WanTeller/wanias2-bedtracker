"""
Database models for the ward board.

A "model" is a Python class that Django turns into a database table.
Each attribute that is a "...Field" becomes a column. Django also writes the
SQL to create/update these tables for us (that's what "migrations" are).

Phase 1 has just three models:

    Ward  --< Bed  --< Patient

The "--<" means "one to many": one Ward has many Beds; one Bed has had many
Patients over time (past occupants stay in the table for history), but only
one Patient is the *current* occupant at any moment.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify


def _new_invite_token():
    """A short, hard-to-guess string for a board's share link."""
    return secrets.token_urlsafe(9)   # ~12 URL-safe characters


class Ward(models.Model):
    """A board: one ward's beds, patients and tasks, with its own group of
    people. Created from the front page; shared by its invite link."""

    name = models.CharField(max_length=100)

    # Readable id used in the address bar, e.g. /w/medicine-2/. Filled in
    # automatically from the name on first save (see save() below).
    slug = models.SlugField(max_length=60, unique=True)

    # The secret in the share link. Rotating it locks out anyone who only had
    # the old link.
    invite_token = models.CharField(
        max_length=32, unique=True, default=_new_invite_token
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="wards_created",
    )
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        # What shows up in the admin site and in shell output.
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "ward"
            slug, n = base, 2
            while Ward.objects.exclude(pk=self.pk).filter(slug=slug).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        if not self.invite_token:
            self.invite_token = _new_invite_token()
        super().save(*args, **kwargs)

    def rotate_invite_token(self):
        self.invite_token = _new_invite_token()
        self.save(update_fields=["invite_token"])

    @property
    def occupied_count(self):
        """How many of this ward's beds currently have a patient."""
        return sum(1 for bed in self.beds.all() if bed.is_occupied)

    @property
    def bed_count(self):
        return self.beds.count()


class WardMembership(models.Model):
    """Links a person to a board they've joined (via its invite link).

    The board's views check for one of these before showing anything. The
    person who created the board is the "owner" (can rotate the link and clear
    the board's data); everyone else is a "member".
    """

    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MEMBER = "member", "Member"

    ward = models.ForeignKey(
        Ward, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ward_memberships",
    )
    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.MEMBER
    )
    # The name this person used when they joined (snapshot for display).
    display_name = models.CharField(max_length=80, blank=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["ward", "display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["ward", "user"], name="unique_ward_membership"
            )
        ]

    def __str__(self):
        return f"{self.display_name or self.user} @ {self.ward}"

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER


class Bed(models.Model):
    """One physical bed in a ward, identified by its number."""

    ward = models.ForeignKey(
        Ward,
        on_delete=models.CASCADE,      # delete a ward -> its beds go too
        related_name="beds",           # lets us write  ward.beds.all()
    )
    number = models.PositiveIntegerField()

    class Meta:
        ordering = ["ward", "number"]
        # No two beds in the same ward can share a number.
        constraints = [
            models.UniqueConstraint(
                fields=["ward", "number"], name="unique_bed_number_per_ward"
            )
        ]

    def __str__(self):
        return f"Bed {self.number}"

    @property
    def current_patient(self):
        """The patient occupying this bed right now, or None.

        A discharged patient keeps pointing at their old bed for history, so
        we filter to status='active' to find the real current occupant.
        """
        return self.patients.filter(status=Patient.Status.ACTIVE).first()

    @property
    def is_occupied(self):
        return self.current_patient is not None

    @property
    def attention(self):
        """Drives the bed card colour: 'overdue' (red), 'pending' (amber),
        'clear' (occupied, nothing outstanding) or 'empty'."""
        patient = self.current_patient
        if patient is None:
            return "empty"
        if patient.has_overdue:
            return "overdue"
        if patient.has_pending:
            return "pending"
        return "clear"


class Patient(models.Model):
    """A patient admitted to a bed. Fields other than 'name' are optional -
    a bed becomes "occupied" as soon as it has a patient with a name."""

    class Status(models.TextChoices):
        # value stored in DB , label shown to humans
        ACTIVE = "active", "Active"
        DISCHARGED = "discharged", "Discharged"

    class Sex(models.TextChoices):
        MALE = "M", "Male"
        FEMALE = "F", "Female"
        OTHER = "O", "Other"

    bed = models.ForeignKey(
        Bed,
        on_delete=models.SET_NULL,     # if a bed is deleted, keep the patient
        null=True,
        blank=True,
        related_name="patients",
    )

    # The only required clinical field.
    name = models.CharField(max_length=120)

    record_no = models.CharField(max_length=40, blank=True)
    age = models.PositiveIntegerField(null=True, blank=True)
    sex = models.CharField(max_length=1, choices=Sex.choices, blank=True)
    admission_date = models.DateField(null=True, blank=True)

    chief_complaint = models.TextField(blank=True)
    brief_history = models.TextField(blank=True)
    active_plan = models.TextField(blank=True)

    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )

    created_at = models.DateTimeField(auto_now_add=True)   # set once, on create
    updated_at = models.DateTimeField(auto_now=True)       # updated every save
    discharged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            # A bed can hold at most one ACTIVE patient. This is what stops two
            # people admitting different patients to the same empty bed at the
            # same moment - the second save raises IntegrityError.
            models.UniqueConstraint(
                fields=["bed"],
                condition=models.Q(status="active", bed__isnull=False),
                name="one_active_patient_per_bed",
            )
        ]

    def __str__(self):
        return self.display_label

    @property
    def display_label(self):
        """'Dostana-27402' style label used on bed cards and the panel header."""
        if self.record_no:
            return f"{self.name}-{self.record_no}"
        return self.name

    def discharge(self):
        """Mark this patient as discharged.

        We keep the 'bed' reference so their history still shows which bed
        they were in. The bed correctly reads as empty anyway, because
        Bed.current_patient only counts patients with status 'active'.
        """
        self.status = self.Status.DISCHARGED
        self.discharged_at = timezone.now()
        self.save()

    # -- task roll-ups (used by the board colour + summary counts) -------- #

    @property
    def has_overdue(self):
        return any(t.is_overdue for t in self.tasks.all())

    @property
    def has_pending(self):
        return any(t.is_pending for t in self.tasks.all())


class ActivityEvent(models.Model):
    """A timestamped record of something that happened on the ward.

    One model feeds two screens:
      - the per-patient History tab  (events filtered to one patient)
      - the Ward Activity sidebar    (all events, newest first)

    Phase 3 adds more 'kinds' for task events (ordered / completed / ...).
    """

    class Kind(models.TextChoices):
        ADMITTED = "admitted", "Admitted"
        DISCHARGED = "discharged", "Discharged"
        TASK_ADDED = "ordered", "Ordered"
        TASK_DONE = "completed", "Completed"
        TASK_REOPENED = "reopened", "Reopened"
        TASK_EDITED = "edited", "Edited"
        TASK_CANCELLED = "cancelled", "Cancelled"
        NOTE_ADDED = "note", "Note"
        VITALS_ADDED = "vitals", "Vitals"
        DATA_CLEARED = "cleared_all", "Data cleared"

    # Which board this happened on. Denormalised (also reachable via
    # patient/bed) so the Ward Activity feed is a single fast query.
    ward = models.ForeignKey(
        Ward,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="events",
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    bed = models.ForeignKey(
        Bed,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    summary = models.CharField(max_length=200)

    # Who did it. `actor` is the live link (for the developer registry);
    # `actor_name` is a snapshot that survives even if the account is deleted.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    actor_name = models.CharField(max_length=80, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    # Set when an event refers to something planned for a future day; this is
    # what the sidebar's "Tomorrow" tab will read once tasks exist.
    scheduled_for = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.summary


# =========================================================================== #
#  Tasks
# =========================================================================== #

class TaskCategory(models.Model):
    """A "slot" on the Tasks tab - Hydration, Order Labs, Unassigned, etc.

    This is a table (not a fixed list in code) so the seed data controls the
    slots, their order, their overdue timing and their preset buttons, and so
    we could let users manage them later.
    """

    key = models.SlugField(max_length=40, unique=True)   # stable id, e.g. "chase_labs"
    name = models.CharField(max_length=60)               # shown to users
    sort_order = models.PositiveIntegerField(default=0)

    # How long after a task is added (with no explicit due time) before it
    # counts as overdue. Null = this slot's tasks never go overdue on their own.
    overdue_after_minutes = models.PositiveIntegerField(null=True, blank=True)

    # Show the "+ add your own" box under this slot's preset buttons.
    allow_custom = models.BooleanField(default=True)

    # Slots sharing a non-empty pair_group are always drawn side by side
    # (used for Order Labs + Chase Labs).
    pair_group = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "task categories"

    def __str__(self):
        return self.name


class TaskOption(models.Model):
    """A preset button under a slot ("ECG", "CXR", "Baseline labs"...).

    is_custom marks options a user added via "+ add your own"; they are kept
    ward-wide so the button is there next time too.
    """

    category = models.ForeignKey(
        TaskCategory, on_delete=models.CASCADE, related_name="options"
    )
    # The 13 default buttons are shared by every board (ward is NULL). Buttons a
    # user adds in the app belong to just that board (ward set, is_custom=True).
    ward = models.ForeignKey(
        Ward,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="task_options",
    )
    label = models.CharField(max_length=80)
    sort_order = models.PositiveIntegerField(default=0)
    is_custom = models.BooleanField(default=False)

    class Meta:
        ordering = ["sort_order", "label"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "label", "ward"],
                name="unique_option_per_category_ward",
            )
        ]

    def __str__(self):
        return f"{self.category.name} / {self.label}"


class Task(models.Model):
    """One task for one patient, filed under a category/slot."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="tasks"
    )
    category = models.ForeignKey(
        TaskCategory, on_delete=models.PROTECT, related_name="tasks"
    )
    # The option this came from, if any (kept for reference; the text lives
    # in 'name' so renaming an option later doesn't rewrite history).
    option = models.ForeignKey(
        TaskOption, on_delete=models.SET_NULL, null=True, blank=True
    )
    name = models.CharField(max_length=120)

    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.OPEN
    )

    created_at = models.DateTimeField(auto_now_add=True)
    done_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # An explicit due time set via "reschedule". When empty we fall back to
    # created_at + the category's overdue_after_minutes.
    due_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return self.name

    # -- state helpers ---------------------------------------------------- #

    @property
    def is_open(self):
        return self.status == self.Status.OPEN

    @property
    def effective_due(self):
        """When this task is 'due', or None if it never auto-expires."""
        if self.due_at:
            return self.due_at
        minutes = self.category.overdue_after_minutes
        if minutes is None:
            return None
        return self.created_at + timedelta(minutes=minutes)

    @property
    def is_overdue(self):
        if not self.is_open:
            return False
        due = self.effective_due
        return due is not None and timezone.now() > due

    @property
    def is_pending(self):
        """Open but not yet overdue."""
        return self.is_open and not self.is_overdue

    # -- transitions ---------------------------------------------------- #

    def mark_done(self):
        self.status = self.Status.DONE
        self.done_at = timezone.now()
        self.save()

    def reopen(self):
        self.status = self.Status.OPEN
        self.done_at = None
        self.save()

    def cancel(self):
        self.status = self.Status.CANCELLED
        self.cancelled_at = timezone.now()
        self.save()


# =========================================================================== #
#  Notes & Vitals
# =========================================================================== #

class Note(models.Model):
    """A free-text clinical/progress note on a patient."""

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="notes"
    )
    body = models.TextField()
    author_name = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.body[:50]


class VitalsEntry(models.Model):
    """One set of observations. Every measurement is optional - record what you
    have."""

    patient = models.ForeignKey(
        Patient, on_delete=models.CASCADE, related_name="vitals"
    )
    recorded_at = models.DateTimeField(default=timezone.now)

    systolic = models.PositiveIntegerField(null=True, blank=True)
    diastolic = models.PositiveIntegerField(null=True, blank=True)
    pulse = models.PositiveIntegerField(null=True, blank=True)
    temp_c = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    resp_rate = models.PositiveIntegerField(null=True, blank=True)
    spo2 = models.PositiveIntegerField(null=True, blank=True)
    rbs = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    note = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name_plural = "vitals entries"

    def __str__(self):
        return f"{self.patient.name} @ {self.recorded_at:%d %b %H:%M}"

    @property
    def bp(self):
        if self.systolic and self.diastolic:
            return f"{self.systolic}/{self.diastolic}"
        return ""

    @property
    def summary(self):
        """Short one-liner for the activity feed."""
        bits = []
        if self.bp:
            bits.append(f"BP {self.bp}")
        if self.pulse:
            bits.append(f"HR {self.pulse}")
        if self.temp_c:
            bits.append(f"T {self.temp_c}")
        if self.spo2:
            bits.append(f"SpO2 {self.spo2}%")
        return ", ".join(bits) or "Vitals recorded"
