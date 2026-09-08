"""
Fills the database with sample data so the board isn't empty while we build.

Run it with:   python manage.py seed_demo
Wipe + refill: python manage.py seed_demo --reset

All patients here are invented. Do NOT put real patient data in seed files.
"""

from datetime import date, datetime, time, timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from board.models import (
    ActivityEvent, Ward, Bed, Patient, Task, TaskCategory,
    Note, VitalsEntry, WardMembership,
)
from board import services

WARD_NAME = "Surgical Unit 2"
TOTAL_BEDS = 44

# (bed number, name, record number, age, sex, chief complaint)
SAMPLE_PATIENTS = [
    (15, "Dostana", "27402", 46, "M", "RUQ pain, ? cholecystitis"),
    (16, "Faisal", "26257", 33, "M", "Appendicitis - post-op day 1"),
    (17, "Umar", "32332", 58, "M", "Obstructive jaundice, for ERCP"),
    (18, "Rasheed", "21392", 41, "M", "Perianal abscess"),
    (20, "Ghulam Haider", "32316", 67, "M", "Inguinal hernia, elective"),
    (23, "Kareem", "44810", 29, "M", "Blunt abdominal trauma, observation"),
]

# A patient who has already gone home - shows up under the "Discharged" tab.
DISCHARGED_PATIENT = (12, "Saleem", "41902", 52, "M", "Lap chole - discharged day 2")

# (bed number, category key, task label, hours ago it was added, done?)
# Tasks older than their category's threshold show up as OVERDUE.
SAMPLE_TASKS = [
    (15, "order_labs", "Baseline Labs", 9, False),
    (15, "hydration", "N/S", 2, False),
    (15, "radiology", "Ultrasound", 14, False),
    (16, "medication", "Tramal", 1, False),
    (16, "medication", "Provas", 5, True),
    (16, "vitals", "Baseline", 7, False),
    (16, "hydration", "N/S", 3, False),
    (17, "order_labs", "LDH", 10, False),
    (17, "order_labs", "Prot AG", 10, False),
    (17, "order_labs", "Baseline Labs", 12, True),
    (17, "radiology", "MRCP", 2, False),
    (17, "arrange_blood", "Crossmatch 2 units", 6, False),
    (18, "medication", "Rizek", 2, False),
    (18, "unassigned", "Mark site pre-op", 1, False),
    (20, "ga_fitness", "ECG", 16, False),
    (20, "referral", "Anaesthetics", 3, False),
    (20, "order_labs", "HbA1c", 2, False),
    (23, "vitals", "RBS", 6, False),
    (23, "radiology", "CT with contrast", 4, False),
    (23, "order_labs", "Blood Culture", 8, False),
]


class Command(BaseCommand):
    help = "Create a sample ward with 44 beds and a few invented patients."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing wards/beds/patients/tasks/events first.",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            Note.objects.all().delete()
            VitalsEntry.objects.all().delete()
            Task.objects.all().delete()
            ActivityEvent.objects.all().delete()
            Patient.objects.all().delete()
            Bed.objects.all().delete()
            Ward.objects.all().delete()
            from board.models import TaskOption
            TaskOption.objects.filter(is_custom=True).delete()
            self.stdout.write("Cleared existing data.")

        # Task categories + preset buttons (safe to run every time).
        call_command("seed_categories")

        # A ready-to-use demo login so you can sign in during development.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        demo_user, _ = User.objects.get_or_create(
            username="demo@ward.local",
            defaults={"email": "demo@ward.local", "first_name": "Demo Intern"},
        )
        if not demo_user.has_usable_password():
            demo_user.set_password("demo-pass-1234")
            demo_user.save(update_fields=["password"])
        self.stdout.write("Demo login: demo@ward.local / demo-pass-1234")

        ward, created = Ward.objects.get_or_create(name=WARD_NAME)
        self.stdout.write(f"{'Created' if created else 'Found'} ward: "
                          f"{ward.name}  (/w/{ward.slug}/)")

        # The demo user owns the demo board.
        WardMembership.objects.update_or_create(
            ward=ward, user=demo_user,
            defaults={"role": WardMembership.Role.OWNER,
                      "display_name": demo_user.first_name},
        )

        made = 0
        for n in range(1, TOTAL_BEDS + 1):
            _, was_created = Bed.objects.get_or_create(ward=ward, number=n)
            made += int(was_created)
        self.stdout.write(f"Beds: {ward.beds.count()} total ({made} new).")

        if Patient.objects.exists():
            self.stdout.write("Patients already present - skipping sample patients.")
            self.stdout.write(self.style.SUCCESS("Done."))
            return

        today = date.today()

        # --- current patients -------------------------------------------- #
        patients_by_bed = {}
        for bed_no, name, rec, age, sex, complaint in SAMPLE_PATIENTS:
            bed = ward.beds.get(number=bed_no)
            patient = Patient.objects.create(
                bed=bed, name=name, record_no=rec, age=age, sex=sex,
                admission_date=today - timedelta(days=2),
                chief_complaint=complaint,
            )
            patients_by_bed[bed_no] = patient
            services.record_admission(patient)
            self._backdate_last_event(patient, today - timedelta(days=2), hour=9)

        # --- sample tasks ----------------------------------------------- #
        categories = {c.key: c for c in TaskCategory.objects.all()}
        for bed_no, cat_key, label, hours_ago, done in SAMPLE_TASKS:
            patient = patients_by_bed[bed_no]
            category = categories[cat_key]
            option = category.options.filter(label=label).first()
            task = services.add_task(patient, category, label, option=option)

            added_at = timezone.now() - timedelta(hours=hours_ago)
            Task.objects.filter(pk=task.pk).update(created_at=added_at)
            self._backdate_last_event(patient, added_at)

            if done:
                task.refresh_from_db()
                services.complete_task(task)
                self._backdate_last_event(patient, added_at + timedelta(hours=1))

        # --- notes & vitals ------------------------------------------- #
        services.add_note(patients_by_bed[16],
                          "POD1 lap appendicectomy. Comfortable, tolerating "
                          "orals. Wounds clean. Plan: mobilise, home tomorrow "
                          "if stable.")
        services.add_note(patients_by_bed[17],
                          "Awaiting ERCP slot. Bilirubin trending down. "
                          "Continue IV antibiotics.")
        for bed_no, sys, dia, hr, temp, rr, spo2 in [
            (16, 118, 74, 82, "37.1", 16, 98),
            (16, 122, 78, 88, "37.6", 18, 97),
            (17, 134, 82, 96, "38.2", 20, 95),
        ]:
            services.add_vitals(
                patients_by_bed[bed_no], systolic=sys, diastolic=dia,
                pulse=hr, temp_c=temp, resp_rate=rr, spo2=spo2,
            )

        # --- one task scheduled for tomorrow ------------------------- #
        tmr_task = services.add_task(
            patients_by_bed[20], categories["review"], "Consultant round"
        )
        tomorrow_9am = timezone.make_aware(
            datetime.combine(today + timedelta(days=1), time(9, 0))
        )
        Task.objects.filter(pk=tmr_task.pk).update(due_at=tomorrow_9am)

        # --- one discharged patient ----------------------------------- #
        bed_no, name, rec, age, sex, complaint = DISCHARGED_PATIENT
        bed = ward.beds.get(number=bed_no)
        gone = Patient.objects.create(
            bed=bed, name=name, record_no=rec, age=age, sex=sex,
            admission_date=today - timedelta(days=4), chief_complaint=complaint,
        )
        services.record_admission(gone)
        self._backdate_last_event(gone, today - timedelta(days=4), hour=10)
        services.record_discharge(gone)
        gone.discharge()
        discharge_dt = timezone.make_aware(
            datetime.combine(today - timedelta(days=1), time(14, 0))
        )
        Patient.objects.filter(pk=gone.pk).update(discharged_at=discharge_dt)
        self._backdate_last_event(gone, today - timedelta(days=1), hour=14)

        self.stdout.write(
            f"Created {len(SAMPLE_PATIENTS)} current + 1 discharged patient, "
            f"{len(SAMPLE_TASKS)} tasks, plus activity events."
        )
        self.stdout.write(self.style.SUCCESS("Done."))

    def _backdate_last_event(self, patient, when, hour=None):
        """Move the patient's most recent event to a past time so the activity
        feed looks realistic. Accepts a date (with hour=) or a full datetime."""
        if hour is not None:
            when = datetime.combine(when, time(hour, 0))
        if timezone.is_naive(when):
            when = timezone.make_aware(when)
        latest = ActivityEvent.objects.filter(patient=patient).order_by("-id").first()
        if latest:
            ActivityEvent.objects.filter(pk=latest.pk).update(created_at=when)
