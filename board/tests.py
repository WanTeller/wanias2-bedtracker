"""
A few automated checks. Run them with:  python manage.py test

Each test creates its own throwaway database, so it never touches your real
data. If we accidentally break admission or discharge later, these fail loudly.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import (
    ActivityEvent, Bed, Note, Patient, Task, TaskCategory, VitalsEntry, Ward,
)

User = get_user_model()


def make_user(email="nurse@example.com", name="Test Nurse", password="pw-testing-123"):
    return User.objects.create_user(
        username=email, email=email, first_name=name, password=password
    )


class WardBoardTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.ward = Ward.objects.create(name="Test Ward")
        self.bed = Bed.objects.create(ward=self.ward, number=1)

    def test_empty_bed_is_not_occupied(self):
        self.assertFalse(self.bed.is_occupied)
        self.assertEqual(self.ward.occupied_count, 0)

    def test_saving_a_name_occupies_the_bed_and_logs_admission(self):
        self.client.post(
            reverse("save_patient", args=[self.bed.id]),
            {"name": "Test Patient"},
        )
        self.bed.refresh_from_db()
        self.assertTrue(self.bed.is_occupied)
        self.assertEqual(self.bed.current_patient.name, "Test Patient")
        self.assertEqual(
            ActivityEvent.objects.filter(kind="admitted").count(), 1
        )

    def test_saving_without_a_name_is_rejected(self):
        self.client.post(reverse("save_patient", args=[self.bed.id]), {"name": ""})
        self.assertFalse(self.bed.is_occupied)
        self.assertEqual(Patient.objects.count(), 0)

    def test_discharge_frees_bed_but_keeps_patient(self):
        patient = Patient.objects.create(bed=self.bed, name="Going Home")

        self.client.post(reverse("discharge_patient", args=[self.bed.id]))

        self.bed.refresh_from_db()
        patient.refresh_from_db()
        self.assertFalse(self.bed.is_occupied)              # bed is free
        self.assertEqual(patient.status, Patient.Status.DISCHARGED)
        self.assertEqual(patient.bed, self.bed)             # link kept for history
        self.assertEqual(
            ActivityEvent.objects.filter(kind="discharged").count(), 1
        )

    def test_activity_sidebar_tabs_load(self):
        for tab in ["activity", "discharged", "tomorrow"]:
            response = self.client.get(reverse("activity"), {"tab": tab})
            self.assertEqual(response.status_code, 200)

    def test_empty_bed_opens_on_patient_tab_with_others_locked(self):
        r = self.client.get(reverse("board"), {"bed": self.bed.id})
        self.assertEqual(r.context["panel_tab"], "patient")
        self.assertContains(r, '<span class="tab disabled">Tasks</span>', html=True)

    def test_occupied_bed_opens_on_tasks_tab(self):
        Patient.objects.create(bed=self.bed, name="Someone")
        r = self.client.get(reverse("board"), {"bed": self.bed.id})
        self.assertEqual(r.context["panel_tab"], "tasks")


class TaskTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.ward = Ward.objects.create(name="Test Ward")
        self.bed = Bed.objects.create(ward=self.ward, number=1)
        self.patient = Patient.objects.create(bed=self.bed, name="Task Patient")
        self.cat = TaskCategory.objects.create(
            key="hydration", name="Hydration", sort_order=1,
            overdue_after_minutes=60,
        )
        self.headers = {"HTTP_HX_REQUEST": "true"}

    def _age_task(self, task, minutes):
        Task.objects.filter(pk=task.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes)
        )
        task.refresh_from_db()

    def test_overdue_only_after_the_category_threshold(self):
        task = Task.objects.create(patient=self.patient, category=self.cat, name="IV fluids")
        self._age_task(task, 30)
        self.assertTrue(task.is_pending)
        self.assertFalse(task.is_overdue)

        self._age_task(task, 90)
        self.assertTrue(task.is_overdue)
        self.assertFalse(task.is_pending)

    def test_done_task_is_never_overdue(self):
        task = Task.objects.create(patient=self.patient, category=self.cat, name="IV fluids")
        self._age_task(task, 999)
        task.mark_done()
        self.assertFalse(task.is_overdue)

    def test_add_task_via_htmx_creates_task_and_event(self):
        self.client.post(
            reverse("task_add", args=[self.bed.id]),
            {"category_key": "hydration", "custom_name": "Oral fluids"},
            **self.headers,
        )
        self.assertEqual(self.patient.tasks.count(), 1)
        self.assertEqual(self.patient.tasks.first().name, "Oral fluids")
        self.assertEqual(ActivityEvent.objects.filter(kind="ordered").count(), 1)

    def test_toggle_completes_then_reopens(self):
        task = Task.objects.create(patient=self.patient, category=self.cat, name="IV fluids")
        self.client.post(reverse("task_toggle", args=[task.id]), **self.headers)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DONE)

        self.client.post(reverse("task_toggle", args=[task.id]), **self.headers)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.OPEN)

    def test_bed_attention_reflects_worst_task(self):
        task = Task.objects.create(patient=self.patient, category=self.cat, name="IV fluids")
        self._age_task(task, 30)
        self.assertEqual(self.bed.attention, "pending")

        self._age_task(task, 120)
        self.assertEqual(self.bed.attention, "overdue")

        task.mark_done()
        self.assertEqual(self.bed.attention, "clear")

    def test_overdue_filter_narrows_the_bed_list(self):
        other_bed = Bed.objects.create(ward=self.ward, number=2)
        Patient.objects.create(bed=other_bed, name="Calm Patient")

        overdue = Task.objects.create(patient=self.patient, category=self.cat, name="IV fluids")
        self._age_task(overdue, 300)

        response = self.client.get(reverse("board"), {"filter": "overdue"})
        self.assertContains(response, "Task Patient")
        self.assertNotContains(response, "Calm Patient")

    def test_open_task_renders_as_a_ticked_checkbox(self):
        Task.objects.create(patient=self.patient, category=self.cat, name="IV fluids")
        response = self.client.get(
            reverse("board"), {"bed": self.bed.id, "tab": "tasks"}
        )
        # ticked = still to do (prototype convention)
        self.assertContains(response, 'type="checkbox" checked')

    def test_slot_checkbox_completes_then_reopens_its_tasks(self):
        task = Task.objects.create(patient=self.patient, category=self.cat, name="IV fluids")

        # slot has an open task -> unticking it completes the task
        self.client.post(
            reverse("slot_toggle", args=[self.bed.id, "hydration"]), **self.headers
        )
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DONE)

        # slot now has only done tasks -> re-ticking reopens them
        self.client.post(
            reverse("slot_toggle", args=[self.bed.id, "hydration"]), **self.headers
        )
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.OPEN)

    def test_completing_order_labs_autocreates_chase_labs(self):
        order = TaskCategory.objects.create(
            key="order_labs", name="Order Labs", sort_order=1, overdue_after_minutes=240,
        )
        chase = TaskCategory.objects.create(
            key="chase_labs", name="Chase Labs", sort_order=2, overdue_after_minutes=180,
        )
        task = Task.objects.create(patient=self.patient, category=order, name="CBC")

        self.client.post(reverse("task_toggle", args=[task.id]), **self.headers)

        self.assertTrue(
            Task.objects.filter(patient=self.patient, category=chase, name="CBC").exists()
        )

    def test_custom_option_add_creates_button_and_task_with_removable_x(self):
        from .models import TaskOption

        self.client.post(
            reverse("option_add", args=["hydration"]),
            {"bed_id": self.bed.id, "label": "Custom fluid"},
            **self.headers,
        )
        opt = TaskOption.objects.get(label="Custom fluid")
        self.assertTrue(opt.is_custom)                       # gets an ×
        self.assertTrue(self.patient.tasks.filter(name="Custom fluid").exists())

        self.client.post(reverse("option_delete", args=[opt.id]),
                         {"bed_id": self.bed.id}, **self.headers)
        self.assertFalse(TaskOption.objects.filter(label="Custom fluid").exists())

    def test_non_htmx_task_action_redirects_to_the_board(self):
        task = Task.objects.create(patient=self.patient, category=self.cat, name="IV fluids")
        response = self.client.post(reverse("task_toggle", args=[task.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"bed={self.bed.id}", response["Location"])


class NotesVitalsTomorrowTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.client.force_login(self.user)
        self.ward = Ward.objects.create(name="Test Ward")
        self.bed = Bed.objects.create(ward=self.ward, number=1)
        self.patient = Patient.objects.create(bed=self.bed, name="NV Patient")
        self.headers = {"HTTP_HX_REQUEST": "true"}

    def test_adding_a_note_stores_it_and_logs_an_event(self):
        self.client.post(reverse("note_add", args=[self.bed.id]),
                         {"body": "Reviewed, stable."}, **self.headers)
        self.assertEqual(self.patient.notes.count(), 1)
        self.assertEqual(ActivityEvent.objects.filter(kind="note").count(), 1)

    def test_blank_note_is_ignored(self):
        self.client.post(reverse("note_add", args=[self.bed.id]),
                         {"body": "   "}, **self.headers)
        self.assertEqual(self.patient.notes.count(), 0)

    def test_recording_vitals_stores_the_set_and_computes_bp(self):
        self.client.post(reverse("vitals_add", args=[self.bed.id]),
                         {"recorded_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                          "systolic": 120, "diastolic": 80, "pulse": 74},
                         **self.headers)
        entry = self.patient.vitals.get()
        self.assertEqual(entry.bp, "120/80")
        self.assertEqual(ActivityEvent.objects.filter(kind="vitals").count(), 1)

    def test_search_finds_patients_tasks_and_notes(self):
        cat = TaskCategory.objects.create(key="review", name="Review", sort_order=1)
        Task.objects.create(patient=self.patient, category=cat, name="Chase histology")
        Note.objects.create(patient=self.patient, body="awaiting histology report")

        r = self.client.get(reverse("board"), {"q": "histolog"})
        s = r.context["search"]
        self.assertEqual(len(s["tasks"]), 1)
        self.assertEqual(len(s["notes"]), 1)

        r2 = self.client.get(reverse("board"), {"q": "NV Pat"})
        self.assertEqual(len(r2.context["search"]["patients"]), 1)

    def test_dev_clear_requires_the_right_password(self):
        Task.objects.create(
            patient=self.patient,
            category=TaskCategory.objects.create(key="x", name="X", sort_order=1),
            name="keep me",
        )
        self.client.post(reverse("dev_clear"), {"password": "wrong"})
        self.assertEqual(Patient.objects.count(), 1)

        self.client.post(reverse("dev_clear"),
                         {"password": settings.DEV_CLEAR_PASSWORD})
        self.assertEqual(Patient.objects.count(), 0)
        self.assertEqual(Task.objects.count(), 0)
        self.assertEqual(Bed.objects.filter(number=1).count(), 1)  # beds kept

    def test_tomorrow_tab_lists_tasks_due_tomorrow_with_a_count(self):
        cat = TaskCategory.objects.create(key="review", name="Review", sort_order=1)
        due_tomorrow = timezone.now() + timedelta(days=1)
        due_next_week = timezone.now() + timedelta(days=7)
        Task.objects.create(patient=self.patient, category=cat, name="Round", due_at=due_tomorrow)
        Task.objects.create(patient=self.patient, category=cat, name="Later", due_at=due_next_week)

        response = self.client.get(reverse("activity"), {"tab": "tomorrow"})
        self.assertEqual(len(response.context["tomorrow_items"]), 1)
        self.assertEqual(response.context["tomorrow_items"][0].name, "Round")


class AuthTests(TestCase):
    def test_board_requires_login(self):
        r = self.client.get(reverse("board"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    def test_signup_creates_account_and_logs_in(self):
        r = self.client.post(reverse("signup"), {
            "name": "Dr Wania", "email": "Wania@Example.com",
            "password1": "s3cure-pw-9911", "password2": "s3cure-pw-9911",
        })
        self.assertEqual(r.status_code, 302)
        user = User.objects.get(email="wania@example.com")   # normalised
        self.assertEqual(user.first_name, "Dr Wania")
        self.assertEqual(user.username, "wania@example.com")

    def test_email_must_be_unique(self):
        make_user(email="taken@example.com")
        r = self.client.post(reverse("signup"), {
            "name": "Someone Else", "email": "TAKEN@example.com",
            "password1": "another-pw-4412", "password2": "another-pw-4412",
        })
        self.assertContains(r, "already exists")
        self.assertEqual(User.objects.filter(email="taken@example.com").count(), 1)

    def test_login_with_email_records_a_login_event(self):
        from accounts.models import LoginEvent
        make_user(email="log@example.com", password="pw-testing-123")
        r = self.client.post(reverse("login"), {
            "username": "log@example.com", "password": "pw-testing-123",
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(LoginEvent.objects.filter(user__email="log@example.com").count(), 1)

    def test_login_registry_is_staff_only(self):
        make_user(email="plain@example.com", password="pw-testing-123")
        self.client.login(username="plain@example.com", password="pw-testing-123")
        r = self.client.get("/admin/accounts/loginevent/")
        self.assertIn(r.status_code, (302, 403))  # redirected to admin login / denied

    def test_signup_shows_a_visible_error_for_a_weak_password(self):
        r = self.client.post(reverse("signup"), {
            "name": "Bob", "email": "bob@example.com",
            "password1": "password", "password2": "password",
        })
        self.assertEqual(r.status_code, 200)          # not created, form redisplayed
        self.assertContains(r, "too common")          # error is actually on the page
        self.assertFalse(User.objects.filter(email="bob@example.com").exists())


class SimpleLoginTests(TestCase):
    """Testing-mode login: name only, no email/password."""

    def test_disabled_by_default(self):
        r = self.client.get(reverse("simple_login"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    @override_settings(SIMPLE_LOGIN=True)
    def test_name_only_login_enters_the_app(self):
        r = self.client.post(reverse("simple_login"), {"name": "Wania Khan"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("board"))
        u = User.objects.get(username="wania-khan.test@simple.local")
        self.assertEqual(u.first_name, "Wania Khan")
        self.assertFalse(u.has_usable_password())
        # session is authenticated as that user
        self.assertEqual(int(self.client.session["_auth_user_id"]), u.id)

    @override_settings(SIMPLE_LOGIN=True)
    def test_same_name_is_the_same_identity_across_sessions(self):
        self.client.post(reverse("simple_login"), {"name": "Wania"})
        self.client.logout()
        self.client.post(reverse("simple_login"), {"name": "  wania  "})  # normalised
        self.assertEqual(User.objects.filter(
            username="wania.test@simple.local").count(), 1)

    @override_settings(SIMPLE_LOGIN=True)
    def test_two_browsers_keep_separate_identities(self):
        from django.test import Client
        a, b = Client(), Client()
        a.post(reverse("simple_login"), {"name": "Aisha"})
        b.post(reverse("simple_login"), {"name": "Bilal"})

        ward = Ward.objects.create(name="Surgical Unit 2")
        bed_a = Bed.objects.create(ward=ward, number=1)
        bed_b = Bed.objects.create(ward=ward, number=2)
        a.post(reverse("save_patient", args=[bed_a.id]), {"name": "Patient A"})
        b.post(reverse("save_patient", args=[bed_b.id]), {"name": "Patient B"})

        self.assertEqual(
            ActivityEvent.objects.get(bed=bed_a, kind="admitted").actor_name, "Aisha")
        self.assertEqual(
            ActivityEvent.objects.get(bed=bed_b, kind="admitted").actor_name, "Bilal")

    @override_settings(SIMPLE_LOGIN=True)
    def test_signup_is_bypassed_in_testing_mode(self):
        r = self.client.get(reverse("signup"))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], reverse("login"))

    @override_settings(SIMPLE_LOGIN=True)
    def test_real_password_login_still_reachable(self):
        make_user(email="real@example.com", password="pw-testing-123")
        r = self.client.post(reverse("password_login"), {
            "username": "real@example.com", "password": "pw-testing-123",
        })
        self.assertEqual(r.status_code, 302)


class ConcurrencyTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.other = make_user(email="other@example.com", name="Other User")
        self.client.force_login(self.user)
        self.ward = Ward.objects.create(name="Test Ward")
        self.bed = Bed.objects.create(ward=self.ward, number=1)
        self.cat = TaskCategory.objects.create(
            key="hydration", name="Hydration", sort_order=1, overdue_after_minutes=60
        )
        self.hx = {"HTTP_HX_REQUEST": "true"}

    def test_stale_patient_edit_is_rejected_not_silently_overwritten(self):
        p = Patient.objects.create(bed=self.bed, name="Original", chief_complaint="A")
        stale = p.updated_at.isoformat()
        # someone else saves in the meantime
        Patient.objects.filter(pk=p.pk).update(
            chief_complaint="B", updated_at=timezone.now()
        )
        r = self.client.post(reverse("save_patient", args=[self.bed.id]), {
            "name": "Original", "chief_complaint": "MY EDIT",
            "expected_updated_at": stale,
        })
        p.refresh_from_db()
        self.assertEqual(p.chief_complaint, "B")          # my edit did NOT land
        self.assertEqual(r.status_code, 302)

    def test_db_forbids_two_active_patients_on_one_bed(self):
        Patient.objects.create(bed=self.bed, name="First")
        # This is what stops a race between two "admit to the empty bed" requests:
        # the second Patient.save() fails at the database level.
        with self.assertRaises(IntegrityError):
            Patient.objects.create(bed=self.bed, name="Second")

    def test_a_discharged_patient_does_not_block_re_admission(self):
        first = Patient.objects.create(bed=self.bed, name="First")
        first.discharge()
        Patient.objects.create(bed=self.bed, name="Second")   # no error
        self.assertEqual(self.bed.current_patient.name, "Second")

    def test_toggle_ignores_a_click_from_a_stale_page(self):
        p = Patient.objects.create(bed=self.bed, name="P")
        task = Task.objects.create(patient=p, category=self.cat, name="IV fluids")
        task.mark_done()  # another user already completed it
        # this user's page still thinks it's open and unticks... er, clicks it
        self.client.post(reverse("task_toggle", args=[task.id]),
                         {"was": "open"}, **self.hx)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.Status.DONE)   # not flipped back open

    def test_actor_is_recorded_on_events(self):
        p = Patient.objects.create(bed=self.bed, name="P")
        self.client.post(reverse("task_add", args=[self.bed.id]),
                         {"category_key": "hydration", "custom_name": "Oral fluids"},
                         **self.hx)
        ev = ActivityEvent.objects.filter(kind="ordered").latest("id")
        self.assertEqual(ev.actor, self.user)
        self.assertEqual(ev.actor_name, "Test Nurse")

    def test_rapid_duplicate_add_is_collapsed(self):
        p = Patient.objects.create(bed=self.bed, name="P")
        for _ in range(3):
            self.client.post(reverse("task_add", args=[self.bed.id]),
                             {"category_key": "hydration", "custom_name": "Analgesia"},
                             **self.hx)
        self.assertEqual(
            p.tasks.filter(name="Analgesia", status=Task.Status.OPEN).count(), 1
        )
