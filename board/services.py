"""
Helper functions that change data AND write the matching ActivityEvent.

Every function that records an event takes an optional `actor` (the logged-in
User). It is stored on the event both as a link (`actor`) and as a name
snapshot (`actor_name`) so the history stays readable and attributable.

Views call these instead of touching the models directly.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ActivityEvent, Note, Task, VitalsEntry

# A brand-new task identical to one just added is almost always an accidental
# double-click / double-submit. Collapse repeats inside this window.
_DEDUPE_SECONDS = 6


def actor_name(actor):
    if actor is None or not getattr(actor, "is_authenticated", False):
        return ""
    return (actor.get_full_name() or actor.first_name or actor.email or "")[:80]


def _event(*, patient, bed, kind, summary, actor=None):
    ActivityEvent.objects.create(
        patient=patient, bed=bed, kind=kind, summary=summary,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_name=actor_name(actor),
    )


# --------------------------------------------------------------------------- #
# patient lifecycle
# --------------------------------------------------------------------------- #

def record_admission(patient, actor=None):
    bed = patient.bed
    _event(patient=patient, bed=bed, kind=ActivityEvent.Kind.ADMITTED,
           summary=f"Admitted to bed {bed.number}" if bed else "Admitted",
           actor=actor)


def record_discharge(patient, actor=None):
    bed = patient.bed
    _event(patient=patient, bed=bed, kind=ActivityEvent.Kind.DISCHARGED,
           summary=f"Discharged from bed {bed.number}" if bed else "Discharged",
           actor=actor)


# --------------------------------------------------------------------------- #
# tasks
# --------------------------------------------------------------------------- #

def _task_event(task, kind, actor=None, summary=None):
    _event(patient=task.patient, bed=task.patient.bed, kind=kind,
           summary=summary or f"{task.category.name}: {task.name}", actor=actor)


def add_task(patient, category, name, option=None, actor=None):
    name = name.strip()

    # De-dupe accidental rapid repeats.
    recent = patient.tasks.filter(
        category=category, name=name, status=Task.Status.OPEN,
        created_at__gte=timezone.now() - timedelta(seconds=_DEDUPE_SECONDS),
    ).first()
    if recent is not None:
        return recent

    task = Task.objects.create(
        patient=patient, category=category, name=name, option=option
    )
    _task_event(task, ActivityEvent.Kind.TASK_ADDED, actor=actor)
    return task


def complete_task(task, actor=None):
    task.mark_done()
    _task_event(task, ActivityEvent.Kind.TASK_DONE, actor=actor)
    _autolink_order_to_chase(task, actor=actor)


def _autolink_order_to_chase(task, actor=None):
    """Completing an 'Order Labs' item means it's been ordered - so it now needs
    chasing. Create the matching 'Chase Labs' task if one isn't already open."""
    if task.category.key != "order_labs":
        return
    from .models import TaskCategory

    chase = TaskCategory.objects.filter(key="chase_labs").first()
    if chase is None:
        return
    exists = task.patient.tasks.filter(
        category=chase, name=task.name, status=Task.Status.OPEN
    ).exists()
    if not exists:
        add_task(task.patient, chase, task.name, actor=actor)


def reopen_task(task, actor=None):
    task.reopen()
    _task_event(task, ActivityEvent.Kind.TASK_REOPENED, actor=actor)


def cancel_task(task, actor=None):
    task.cancel()
    _task_event(task, ActivityEvent.Kind.TASK_CANCELLED, actor=actor)


def edit_task(task, *, name=None, due_at="__keep__", actor=None):
    """Rename and/or reschedule a task, logging the change."""
    changes = []
    if name and name.strip() and name.strip() != task.name:
        changes.append(f"renamed to “{name.strip()}”")
        task.name = name.strip()
    if due_at != "__keep__" and due_at != task.due_at:
        if due_at:
            changes.append(f"due {timezone.localtime(due_at):%d %b %H:%M}")
        else:
            changes.append("due time cleared")
        task.due_at = due_at
    task.save()
    if changes:
        _task_event(
            task, ActivityEvent.Kind.TASK_EDITED, actor=actor,
            summary=f"{task.category.name}: {task.name} – {', '.join(changes)}",
        )


# --------------------------------------------------------------------------- #
# slot tick
# --------------------------------------------------------------------------- #

def toggle_slot(patient, category, actor=None):
    """The slot's master checkbox. A ticked checkbox means "still to do":
      - slot has open tasks   -> untick = complete them all
      - slot has only done    -> tick   = reopen them all
      - empty single-item slot (Receiving Notes) -> tick = create the task
    """
    slot_tasks = patient.tasks.filter(category=category)
    open_tasks = list(slot_tasks.filter(status=Task.Status.OPEN))
    done_tasks = list(slot_tasks.filter(status=Task.Status.DONE))

    if open_tasks:
        for task in open_tasks:
            complete_task(task, actor=actor)
    elif done_tasks:
        for task in done_tasks:
            reopen_task(task, actor=actor)
    elif (
        category.key != "unassigned"
        and not category.allow_custom
        and not category.options.exists()
    ):
        add_task(patient, category, category.name, actor=actor)


# --------------------------------------------------------------------------- #
# custom preset buttons
# --------------------------------------------------------------------------- #

def add_custom_option(category, label):
    from .models import TaskOption

    label = label.strip()
    if not label:
        return None
    option, _ = TaskOption.objects.get_or_create(
        category=category, label=label,
        defaults={"is_custom": True, "sort_order": category.options.count()},
    )
    return option


def delete_option(option):
    if option.is_custom:
        option.delete()


# --------------------------------------------------------------------------- #
# notes & vitals
# --------------------------------------------------------------------------- #

def add_note(patient, body, actor=None):
    body = body.strip()
    if not body:
        return None
    note = Note.objects.create(
        patient=patient, body=body, author_name=actor_name(actor)
    )
    _event(patient=patient, bed=patient.bed, kind=ActivityEvent.Kind.NOTE_ADDED,
           summary=body[:80] + ("…" if len(body) > 80 else ""), actor=actor)
    return note


def add_vitals(patient, actor=None, **fields):
    clean = {k: v for k, v in fields.items() if v not in (None, "")}
    entry = VitalsEntry.objects.create(patient=patient, **clean)
    _event(patient=patient, bed=patient.bed,
           kind=ActivityEvent.Kind.VITALS_ADDED, summary=entry.summary, actor=actor)
    return entry


# --------------------------------------------------------------------------- #
# developer reset
# --------------------------------------------------------------------------- #

def clear_all_patient_data(actor=None):
    """Wipe every patient and everything attached to them. Beds and the task
    catalogue are kept. One final activity event records who did it."""
    with transaction.atomic():
        Note.objects.all().delete()
        VitalsEntry.objects.all().delete()
        Task.objects.all().delete()
        ActivityEvent.objects.all().delete()
        from .models import Patient
        Patient.objects.all().delete()
        _event(patient=None, bed=None, kind=ActivityEvent.Kind.DATA_CLEARED,
               summary="All patient data cleared", actor=actor)
