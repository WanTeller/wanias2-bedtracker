"""
Views: each function handles one web request and returns a page (or, for the
HTMX task actions, a small HTML fragment that gets swapped into the page).

Every board view is wrapped by @ward_view, which reads the board from the
<slug> in the address, checks the logged-in user is a member of it, and hands
the Ward object to the view as its second argument.
"""

from datetime import datetime, timedelta
from functools import wraps
from itertools import groupby
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.db import IntegrityError, connection, transaction
from django.db.models import Prefetch, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localdate, localtime
from django.views.decorators.http import require_POST

from .forms import BoardForm, PatientForm, VitalsForm
from .models import (
    ActivityEvent, Bed, Note, Patient, Task, TaskCategory, TaskOption,
    VitalsEntry, Ward, WardMembership,
)
from . import services


# --------------------------------------------------------------------------- #
# health check (used by the host; no login)
# --------------------------------------------------------------------------- #

@login_not_required
def healthz(request):
    try:
        connection.ensure_connection()
    except Exception:  # noqa: BLE001
        return HttpResponse("db error", status=503)
    return HttpResponse("ok")


# --------------------------------------------------------------------------- #
# front page
# --------------------------------------------------------------------------- #

def home(request):
    """The front page: the boards you belong to, plus 'create' and 'join'."""
    memberships = list(
        request.user.ward_memberships.select_related("ward").order_by(
            "-joined_at"
        )
    )
    return render(
        request,
        "board/dashboard.html",
        {"memberships": memberships, "join_error": request.GET.get("bad")},
    )


def _join_url(request, ward):
    """The absolute share link for a board."""
    return request.build_absolute_uri(reverse("join", args=[ward.invite_token]))


def board_new(request):
    """Create a board. The creator becomes its owner."""
    form = BoardForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            ward = form.save(commit=False)
            ward.created_by = request.user
            ward.save()
            Bed.objects.bulk_create(
                [Bed(ward=ward, number=n)
                 for n in range(1, form.cleaned_data["bed_count"] + 1)]
            )
            WardMembership.objects.create(
                ward=ward,
                user=request.user,
                role=WardMembership.Role.OWNER,
                display_name=services.actor_name(request.user),
            )
        messages.success(
            request,
            f"Board “{ward.name}” created. Its share link is in the activity "
            f"panel (the ☰ menu) - send it to your team.",
        )
        return redirect("board", slug=ward.slug)

    return render(request, "board/board_new.html", {"form": form})


def join(request, token):
    """Open a board's invite link: confirm, then add the user as a member."""
    ward = get_object_or_404(Ward, invite_token=token)
    already = WardMembership.objects.filter(ward=ward, user=request.user).exists()

    if request.method == "POST" and not already:
        WardMembership.objects.get_or_create(
            ward=ward,
            user=request.user,
            defaults={
                "role": WardMembership.Role.MEMBER,
                "display_name": services.actor_name(request.user),
            },
        )
        messages.success(request, f"You've joined “{ward.name}”.")
        already = True

    if already:
        return redirect("board", slug=ward.slug)

    return render(request, "board/join_confirm.html", {"ward": ward})


@require_POST
def join_paste(request):
    """The dashboard's 'paste a link' box. Accepts a full link or a bare code."""
    raw = (request.POST.get("code") or "").strip()
    token = raw.rstrip("/").split("/")[-1] if raw else ""

    ward = None
    if token:
        ward = (
            Ward.objects.filter(invite_token=token).first()
            or Ward.objects.filter(slug=token).first()
        )
    if ward is None:
        return redirect(reverse("home") + "?bad=1")
    return redirect("join", token=ward.invite_token)


# --------------------------------------------------------------------------- #
# access control
# --------------------------------------------------------------------------- #

def ward_view(view):
    """Resolve <slug> to a Ward, require membership, pass the Ward to the view."""
    @wraps(view)
    def _wrapped(request, slug, *args, **kwargs):
        ward = get_object_or_404(Ward, slug=slug)
        membership = WardMembership.objects.filter(
            ward=ward, user=request.user
        ).first()
        if membership is None:
            return render(
                request, "board/not_a_member.html", {"ward": ward}, status=403
            )
        request.ward = ward
        request.membership = membership
        return view(request, ward, *args, **kwargs)

    return _wrapped


def _board_url(ward, **params):
    url = reverse("board", args=[ward.slug])
    if params:
        url += "?" + urlencode(params)
    return url


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _ordered_beds(ward):
    """Occupied beds first, then empty; numeric within each group."""
    beds = list(ward.beds.all())
    beds.sort(key=lambda b: (not b.is_occupied, b.number))
    return beds


def _group_events_by_day(events):
    groups = []
    for day, items in groupby(events, key=lambda e: localtime(e.created_at).date()):
        groups.append((day, list(items)))
    return groups


def _open_tasks(ward):
    """All open (not done, not cancelled) tasks for patients currently on a bed
    in this ward."""
    return [
        t
        for t in Task.objects.filter(
            status=Task.Status.OPEN,
            patient__status=Patient.Status.ACTIVE,
            patient__bed__ward=ward,
        ).select_related("category", "patient", "patient__bed")
        if t.patient.bed_id is not None
    ]


def _ward_options(ward):
    """Preset buttons visible on this board: the shared defaults (ward NULL)
    plus this board's own custom buttons."""
    return TaskOption.objects.filter(
        Q(is_custom=False) | Q(ward=ward)
    ).order_by("sort_order", "label")


def _chip_data(open_tasks, active_filter):
    """Build the filter-chip bar: All / Pending / Overdue / one per category."""
    overdue = [t for t in open_tasks if t.is_overdue]
    pending = [t for t in open_tasks if t.is_pending]

    chips = [
        {"key": "all", "label": "All", "count": None},
        {"key": "pending", "label": "Pending", "count": len(pending)},
        {"key": "overdue", "label": "Overdue", "count": len(overdue)},
    ]
    per_cat = {}
    for t in open_tasks:
        per_cat.setdefault(t.category_id, 0)
        per_cat[t.category_id] += 1
    for cat in TaskCategory.objects.all():
        count = per_cat.get(cat.id, 0)
        if count:
            chips.append(
                {"key": f"cat:{cat.key}", "label": cat.name, "count": count}
            )
    for c in chips:
        c["active"] = c["key"] == active_filter
    return chips, len(pending), len(overdue)


def _apply_filter(beds, open_tasks, active_filter):
    """Narrow the bed list according to the selected chip."""
    if active_filter in (None, "", "all"):
        return beds

    beds_with = set()
    for t in open_tasks:
        if active_filter == "pending" and t.is_pending:
            beds_with.add(t.patient.bed_id)
        elif active_filter == "overdue" and t.is_overdue:
            beds_with.add(t.patient.bed_id)
        elif active_filter == f"cat:{t.category.key}":
            beds_with.add(t.patient.bed_id)
    return [b for b in beds if b.id in beds_with]


def _search(ward, term):
    """Search current patients, their open/done tasks and their notes."""
    term = term.strip()
    active = {"status": Patient.Status.ACTIVE, "bed__ward": ward}
    patients = list(
        Patient.objects.filter(**active).filter(
            Q(name__icontains=term)
            | Q(record_no__icontains=term)
            | Q(chief_complaint__icontains=term)
            | Q(brief_history__icontains=term)
            | Q(active_plan__icontains=term)
        ).select_related("bed")
    )
    tasks = list(
        Task.objects.filter(
            patient__status=Patient.Status.ACTIVE,
            patient__bed__ward=ward,
            name__icontains=term,
        )
        .exclude(status=Task.Status.CANCELLED)
        .select_related("patient", "patient__bed", "category")
    )
    notes = list(
        Note.objects.filter(
            patient__status=Patient.Status.ACTIVE,
            patient__bed__ward=ward,
            body__icontains=term,
        ).select_related("patient", "patient__bed")
    )
    return {
        "term": term,
        "patients": patients,
        "tasks": tasks,
        "notes": notes,
        "total": len(patients) + len(tasks) + len(notes),
    }


def _build_slot_rows(patient, ward):
    """Turn a patient's tasks into the list of slots shown on the Tasks tab.

    Each row is one category, except paired categories (Order Labs + Chase
    Labs) which share a row and are always drawn side by side. Rows are in a
    fixed order (category.sort_order); the Unassigned row is always last.
    """
    categories = list(
        TaskCategory.objects.prefetch_related(
            Prefetch("options", queryset=_ward_options(ward))
        )
    )
    tasks = list(patient.tasks.select_related("category", "option"))

    tasks_by_cat = {}
    for t in tasks:
        tasks_by_cat.setdefault(t.category_id, []).append(t)

    slots = {}
    for cat in categories:
        ctasks = tasks_by_cat.get(cat.id, [])
        open_tasks = [t for t in ctasks if t.is_open]
        open_tasks.sort(key=lambda t: (not t.is_overdue, t.created_at))
        done_tasks = [t for t in ctasks if t.status == Task.Status.DONE]
        slots[cat.key] = {
            "category": cat,
            "open_tasks": open_tasks,
            "done_tasks": done_tasks,
            "open_count": len(open_tasks),
            "overdue_count": sum(1 for t in open_tasks if t.is_overdue),
            # Master checkbox is ticked while there's still something to do;
            # "cleared" = has tasks, none open.
            "checked": len(open_tasks) > 0,
            "cleared": bool(done_tasks) and not open_tasks,
        }

    # group into rows (pairs stay together)
    rows, used = [], set()
    for cat in sorted(categories, key=lambda c: c.sort_order):
        if cat.key in used:
            continue
        if cat.pair_group:
            mates = [c for c in categories if c.pair_group == cat.pair_group]
            mates.sort(key=lambda c: c.sort_order)
            used.update(c.key for c in mates)
            rows.append({"paired": True, "slots": [slots[c.key] for c in mates]})
        else:
            used.add(cat.key)
            rows.append({"paired": False, "slots": [slots[cat.key]]})

    # Fixed order by sort_order; the Unassigned row is always pinned last.
    def row_key(r):
        is_unassigned = any(s["category"].key == "unassigned" for s in r["slots"])
        return (is_unassigned, min(s["category"].sort_order for s in r["slots"]))

    rows.sort(key=row_key)
    return rows


def _tasks_context(bed, ward, open_key=None, editing_task_id=None):
    return {
        "selected_bed": bed,
        "slot_rows": _build_slot_rows(bed.current_patient, ward),
        "open_key": open_key,
        "editing_task_id": editing_task_id,
    }


def _render_task_action(request, ward, bed, open_key=None, editing_task_id=None):
    """Response for an HTMX task action: the tasks panel + out-of-band updates
    for the summary counts, the chip bar and this bed's card.

    If the request did NOT come from HTMX (e.g. JS disabled), just go back to
    the board with this bed open.
    """
    if not request.headers.get("HX-Request"):
        return redirect(_board_url(ward, bed=bed.id, tab="tasks"))

    open_tasks = _open_tasks(ward)
    active_filter = request.GET.get("filter") or "all"
    chips, pending_count, overdue_count = _chip_data(open_tasks, active_filter)

    ctx = _tasks_context(bed, ward, open_key, editing_task_id)
    ctx.update(
        {
            "oob": True,
            "chips": chips,
            "active_filter": active_filter,
            "panel_tab": "tasks",
            "pending_count": pending_count,
            "overdue_count": overdue_count,
            "ward": ward,
            "oob_bed": bed,
        }
    )
    return render(request, "board/_tasks_response.html", ctx)


# --------------------------------------------------------------------------- #
# main pages
# --------------------------------------------------------------------------- #

@ward_view
def board_view(request, ward):
    beds = _ordered_beds(ward)
    open_tasks = _open_tasks(ward)
    active_filter = request.GET.get("filter") or "all"
    chips, pending_count, overdue_count = _chip_data(open_tasks, active_filter)
    visible_beds = _apply_filter(beds, open_tasks, active_filter)

    selected_bed = None
    patient_form = None
    panel_tab = None
    bed_id = request.GET.get("bed")
    if bed_id:
        selected_bed = get_object_or_404(Bed, pk=bed_id, ward=ward)
        patient_form = PatientForm(instance=selected_bed.current_patient)
        if selected_bed.current_patient is None:
            # An empty bed: only the Patient tab is reachable until a name is
            # saved. An occupied bed opens on Tasks by default.
            panel_tab = "patient"
        else:
            panel_tab = request.GET.get("tab", "tasks")

    query = request.GET.get("q", "")

    context = {
        "ward": ward,
        "beds": visible_beds,
        "chips": chips,
        "active_filter": active_filter,
        "pending_count": pending_count,
        "overdue_count": overdue_count,
        "selected_bed": selected_bed,
        "patient_form": patient_form,
        "panel_tab": panel_tab,
        "confirm_discharge": request.GET.get("confirm") == "discharge",
        "sidebar_open": False,
        "sidebar_tab": None,
        "query": query,
        "search": _search(ward, query) if query.strip() else None,
    }

    patient = selected_bed.current_patient if selected_bed else None
    if patient and panel_tab == "tasks":
        context.update(_tasks_context(selected_bed, ward))
    elif patient and panel_tab == "notes":
        context["notes"] = list(patient.notes.all())
    elif patient and panel_tab == "vitals":
        context["vitals_form"] = VitalsForm()
        context["vitals_entries"] = list(patient.vitals.all())
    elif selected_bed and panel_tab == "history":
        events = list(patient.events.all()) if patient else []
        context["event_groups"] = _group_events_by_day(events)

    return render(request, "board/board.html", context)


@ward_view
@require_POST
def save_patient(request, ward, bed_id):
    bed = get_object_or_404(Bed, pk=bed_id, ward=ward)

    existing = bed.current_patient
    is_new_admission = existing is None

    # Optimistic concurrency: if someone else saved this patient while this
    # user had the form open, refuse rather than silently overwrite them.
    if existing is not None:
        seen = request.POST.get("expected_updated_at", "")
        if seen and seen != existing.updated_at.isoformat():
            messages.error(
                request,
                f"Bed {bed.number}: another user changed these details while "
                f"you were editing. Your changes were NOT saved - reopen the "
                f"bed to see the current details.",
            )
            return redirect(_board_url(ward, bed=bed.id, tab="patient"))

    form = PatientForm(request.POST, instance=existing)
    if form.is_valid():
        patient = form.save(commit=False)
        if patient.bed_id is None:
            patient.bed = bed
        if not patient.admission_date:
            patient.admission_date = timezone.localdate()
        try:
            patient.save()
        except IntegrityError:
            # The one-active-patient-per-bed constraint fired: someone admitted
            # to this bed a moment ago.
            messages.error(
                request,
                f"Bed {bed.number} was just taken by another user. "
                f"Nothing was saved.",
            )
            return redirect("board", slug=ward.slug)

        if is_new_admission:
            services.record_admission(patient, actor=request.user)
            messages.success(request, f"Bed {bed.number}: {patient.name} admitted.")
        else:
            messages.success(request, "Patient details saved.")
        # Stay on the Patient tab so the user can keep filling in details.
        return redirect(_board_url(ward, bed=bed.id, tab="patient"))

    beds = _ordered_beds(ward)
    open_tasks = _open_tasks(ward)
    chips, pending_count, overdue_count = _chip_data(open_tasks, "all")
    return render(
        request,
        "board/board.html",
        {
            "ward": ward,
            "beds": beds,
            "chips": chips,
            "active_filter": "all",
            "pending_count": pending_count,
            "overdue_count": overdue_count,
            "selected_bed": bed,
            "patient_form": form,
            "panel_tab": "patient",
            "confirm_discharge": False,
            "sidebar_open": False,
            "sidebar_tab": None,
        },
    )


@ward_view
@require_POST
def discharge_patient(request, ward, bed_id):
    bed = get_object_or_404(Bed, pk=bed_id, ward=ward)

    with transaction.atomic():
        patient = (
            Patient.objects.select_for_update()
            .filter(bed=bed, status=Patient.Status.ACTIVE)
            .first()
        )
        if patient is None:
            messages.info(request, f"Bed {bed.number} is already empty.")
            return redirect("board", slug=ward.slug)
        services.record_discharge(patient, actor=request.user)
        patient.discharge()

    messages.success(request, f"Bed {bed.number}: {patient.name} discharged.")
    return redirect("board", slug=ward.slug)


@ward_view
def activity_view(request, ward):
    tab = request.GET.get("tab", "activity")
    beds = _ordered_beds(ward)
    open_tasks = _open_tasks(ward)
    chips, pending_count, overdue_count = _chip_data(open_tasks, "all")

    context = {
        "ward": ward,
        "beds": beds,
        "chips": chips,
        "active_filter": "all",
        "pending_count": pending_count,
        "overdue_count": overdue_count,
        "selected_bed": None,
        "panel_tab": "patient",
        "confirm_discharge": False,
        "sidebar_open": True,
        "sidebar_tab": tab,
        "dev_clear_enabled": (
            bool(settings.DEV_CLEAR_PASSWORD) and request.membership.is_owner
        ),
        "is_owner": request.membership.is_owner,
        "join_url": _join_url(request, ward),
        "query": "",
        "search": None,
    }

    if tab == "discharged":
        context["discharged_patients"] = (
            Patient.objects.filter(
                status=Patient.Status.DISCHARGED, bed__ward=ward
            )
            .select_related("bed")
            .order_by("-discharged_at")
        )
    elif tab == "tomorrow":
        tomorrow = localdate() + timedelta(days=1)
        items = [
            t for t in open_tasks
            if t.effective_due and localtime(t.effective_due).date() == tomorrow
        ]
        items.sort(key=lambda t: (t.patient.bed.number, t.effective_due))
        context["tomorrow_items"] = items
        context["tomorrow_date"] = tomorrow
    else:
        events = list(
            ActivityEvent.objects.filter(ward=ward).select_related("patient", "bed")[:100]
        )
        context["event_groups"] = _group_events_by_day(events)

    return render(request, "board/board.html", context)


@ward_view
@require_POST
def rotate_link(request, ward):
    """Owner-only: generate a fresh share link (the old one stops working)."""
    if request.membership.is_owner:
        ward.rotate_invite_token()
        messages.success(
            request, "New share link generated. The old link no longer works."
        )
    return redirect("activity", slug=ward.slug)


@ward_view
@require_POST
def dev_clear(request, ward):
    """Owner-only: wipe this board's patient data. Also guarded by a password
    set in settings (BEDTRACKER_DEV_CLEAR_PASSWORD). Lives only in the sidebar."""
    if not settings.DEV_CLEAR_PASSWORD or not request.membership.is_owner:
        return redirect("activity", slug=ward.slug)

    if request.POST.get("password") == settings.DEV_CLEAR_PASSWORD:
        services.clear_ward_patient_data(ward, actor=request.user)
        messages.success(request, "All patient data cleared.")
    else:
        messages.error(request, "Wrong password - nothing was cleared.")
    return redirect("board", slug=ward.slug)


# --------------------------------------------------------------------------- #
# task actions (HTMX)
# --------------------------------------------------------------------------- #

def _get_bed_patient(ward, bed_id):
    bed = get_object_or_404(Bed, pk=bed_id, ward=ward)
    return bed, bed.current_patient


def _patient_matches(request, patient):
    """Guard against the bed's patient changing (discharge + re-admit) between
    the page render and this action."""
    submitted = request.POST.get("patient_id")
    return not submitted or str(patient.id) == submitted


@ward_view
@require_POST
def task_add(request, ward, bed_id):
    bed, patient = _get_bed_patient(ward, bed_id)
    if patient is None or not _patient_matches(request, patient):
        return _render_task_action(request, ward, bed)

    cat_key = request.POST.get("category_key", "unassigned")
    category = get_object_or_404(TaskCategory, key=cat_key)

    option_id = request.POST.get("option_id")
    custom_name = (request.POST.get("custom_name") or "").strip()

    with transaction.atomic():
        if option_id:
            option = get_object_or_404(
                _ward_options(ward).filter(category=category), pk=option_id
            )
            services.add_task(patient, category, option.label,
                              option=option, actor=request.user)
        elif custom_name:
            services.add_task(patient, category, custom_name, actor=request.user)

    return _render_task_action(request, ward, bed, open_key=cat_key)


def _lock_task(ward, task_id):
    """Fetch a task FOR UPDATE (serialises concurrent actions on the same row)."""
    return get_object_or_404(
        Task.objects.select_for_update(),
        pk=task_id,
        patient__status=Patient.Status.ACTIVE,
        patient__bed__ward=ward,
    )


@ward_view
@require_POST
def task_toggle(request, ward, task_id):
    with transaction.atomic():
        task = _lock_task(ward, task_id)
        bed = task.patient.bed
        was = request.POST.get("was")  # the state the user's page believed
        if was and was != task.status:
            # Someone else already changed it - do nothing, just show reality.
            pass
        elif task.status == Task.Status.DONE:
            services.reopen_task(task, actor=request.user)
        elif task.status == Task.Status.OPEN:
            services.complete_task(task, actor=request.user)
    return _render_task_action(request, ward, bed, open_key=task.category.key)


@ward_view
@require_POST
def task_cancel(request, ward, task_id):
    with transaction.atomic():
        task = _lock_task(ward, task_id)
        bed = task.patient.bed
        if task.status != Task.Status.CANCELLED:
            services.cancel_task(task, actor=request.user)
    return _render_task_action(request, ward, bed, open_key=task.category.key)


@ward_view
def task_edit(request, ward, task_id):
    """GET = swap this task row into an edit form.
       POST = apply the new name / due time."""
    if request.method == "POST":
        with transaction.atomic():
            task = _lock_task(ward, task_id)
            bed = task.patient.bed
            due_raw = request.POST.get("due_at")
            if due_raw:
                parsed = datetime.fromisoformat(due_raw)
                if timezone.is_naive(parsed):
                    parsed = timezone.make_aware(parsed)
                due_at = parsed
            elif "due_at" in request.POST:
                due_at = None
            else:
                due_at = "__keep__"
            services.edit_task(
                task, name=request.POST.get("name"), due_at=due_at,
                actor=request.user,
            )
        return _render_task_action(request, ward, bed, open_key=task.category.key)

    task = get_object_or_404(
        Task, pk=task_id, patient__status=Patient.Status.ACTIVE,
        patient__bed__ward=ward,
    )
    return _render_task_action(
        request, ward, task.patient.bed,
        open_key=task.category.key, editing_task_id=task.id,
    )


@ward_view
@require_POST
def slot_toggle(request, ward, bed_id, cat_key):
    bed, patient = _get_bed_patient(ward, bed_id)
    category = get_object_or_404(TaskCategory, key=cat_key)
    if patient is not None and _patient_matches(request, patient):
        with transaction.atomic():
            services.toggle_slot(patient, category, actor=request.user)
    return _render_task_action(request, ward, bed, open_key=cat_key)


@ward_view
@require_POST
def option_add(request, ward, cat_key):
    """The slot's "+ Add custom option" box: register a reusable button (for
    this board) AND add the task to this patient right now."""
    category = get_object_or_404(TaskCategory, key=cat_key)
    bed = get_object_or_404(Bed, pk=request.POST.get("bed_id"), ward=ward)
    label = (request.POST.get("label") or "").strip()
    if label and bed.current_patient and _patient_matches(request, bed.current_patient):
        with transaction.atomic():
            option = services.add_custom_option(category, label, ward)
            services.add_task(bed.current_patient, category, label,
                              option=option, actor=request.user)
    return _render_task_action(request, ward, bed, open_key=cat_key)


@ward_view
@require_POST
def option_delete(request, ward, option_id):
    """The small × on a custom button - removes it (permanent presets have no ×,
    and one board can't remove another's)."""
    option = get_object_or_404(TaskOption, pk=option_id, ward=ward)
    cat_key = option.category.key
    bed = get_object_or_404(Bed, pk=request.POST.get("bed_id"), ward=ward)
    services.delete_option(option)
    return _render_task_action(request, ward, bed, open_key=cat_key)


# --------------------------------------------------------------------------- #
# notes & vitals (HTMX)
# --------------------------------------------------------------------------- #

@ward_view
@require_POST
def note_add(request, ward, bed_id):
    bed, patient = _get_bed_patient(ward, bed_id)
    if patient is not None and _patient_matches(request, patient):
        services.add_note(patient, request.POST.get("body") or "",
                          actor=request.user)
    if not request.headers.get("HX-Request"):
        return redirect(_board_url(ward, bed=bed.id, tab="notes"))
    return render(request, "board/_notes.html",
                  {"selected_bed": bed, "ward": ward,
                   "notes": list(patient.notes.all())})


@ward_view
@require_POST
def vitals_add(request, ward, bed_id):
    bed, patient = _get_bed_patient(ward, bed_id)
    form = VitalsForm(request.POST or None)
    if patient is not None and _patient_matches(request, patient) and form.is_valid():
        services.add_vitals(patient, actor=request.user, **form.cleaned_data)
        form = VitalsForm()  # fresh blank form after a successful save
    if not request.headers.get("HX-Request"):
        return redirect(_board_url(ward, bed=bed.id, tab="vitals"))
    return render(request, "board/_vitals.html", {
        "selected_bed": bed,
        "ward": ward,
        "vitals_form": form,
        "vitals_entries": list(patient.vitals.all()),
    })
