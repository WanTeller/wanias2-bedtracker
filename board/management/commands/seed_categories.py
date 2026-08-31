"""
Creates / updates the task categories (the "slots" on the Tasks tab) and their
permanent preset buttons - taken from the Base44 prototype.

Safe to re-run. It keeps the permanent presets in sync with the list below and
NEVER touches options a user added in the app (those have is_custom=True).

    python manage.py seed_categories
"""

from django.core.management.base import BaseCommand

from board.models import TaskCategory, TaskOption

_REFERRAL_LIST = [
    "Medicine", "Vascular", "Plastic", "Urologic", "Surgical", "Orthopaedics",
    "ICU", "Anaesthetics", "ENT", "Ophthalmology", "Dermatology", "Oncology",
]
_LABS_LIST = [
    "Baseline Labs", "Indirect & Direct Bilirubin", "Blood Culture", "Pus C/S",
    "Albumin", "Troponin", "Prot AG", "BTD", "LDH", "Cal Mag Phos", "ABG",
    "HbA1c", "Urine CS", "Urine DR", "UCE",
]

# Slot display order (Unassigned is also force-pinned to the bottom in the view).
#  key,             name,             order, overdue_min, allow_custom, pair,   permanent presets
CATEGORIES = [
    ("order_labs", "Order Labs", 10, 240, True, "labs", _LABS_LIST),
    ("chase_labs", "Chase Labs", 15, 180, True, "labs", _LABS_LIST),
    ("hydration", "Hydration", 20, 360, True, "",
        ["N/S", "Ringers", "Provas", "Vit K"]),
    ("medication", "Medication", 30, 240, True, "",
        ["Provas", "Rizek", "Tramal", "Metacolon", "Insulin", "Nebs", "Vit K"]),
    ("radiology", "Radiology", 40, 720, True, "",
        ["CXR", "ECHO", "MRI", "CT with contrast", "CT without contrast",
         "Ultrasound", "ERCP", "MRCP"]),
    ("histopath", "Histopath", 50, 1440, True, "", []),
    ("referral", "Referral", 60, 720, True, "", _REFERRAL_LIST),
    ("review", "Review", 70, 480, True, "", _REFERRAL_LIST),
    ("arrange_blood", "Arrange Blood", 80, 240, True, "", []),
    ("ga_fitness", "GA Fitness", 90, 720, True, "",
        ["ECG", "CXray", "ECHO", "Cardiac Fitness"]),
    ("vitals", "Vitals", 100, 240, True, "",
        ["Baseline", "RBS", "Fever Charting"]),
    ("receiving_notes", "Receiving Notes", 110, 180, False, "", []),
    ("unassigned", "Unassigned", 900, 240, False, "", []),
]


class Command(BaseCommand):
    help = "Create/update task categories and their permanent preset buttons."

    def handle(self, *args, **options):
        keep_keys = {c[0] for c in CATEGORIES}

        for key, name, order, overdue_min, allow_custom, pair, presets in CATEGORIES:
            category, _ = TaskCategory.objects.update_or_create(
                key=key,
                defaults={
                    "name": name,
                    "sort_order": order,
                    "overdue_after_minutes": overdue_min,
                    "allow_custom": allow_custom,
                    "pair_group": pair,
                },
            )
            # Sync the PERMANENT presets (is_custom=False) to the list above.
            category.options.filter(is_custom=False).exclude(label__in=presets).delete()
            for i, label in enumerate(presets):
                TaskOption.objects.update_or_create(
                    category=category, label=label,
                    defaults={"sort_order": i, "is_custom": False},
                )

        # Drop categories we no longer use (e.g. an earlier "assessment").
        removed = TaskCategory.objects.exclude(key__in=keep_keys)
        if removed.exists():
            self.stdout.write(f"Removing old categories: "
                              f"{', '.join(removed.values_list('key', flat=True))}")
            removed.delete()

        self.stdout.write(self.style.SUCCESS(
            f"{TaskCategory.objects.count()} categories, "
            f"{TaskOption.objects.filter(is_custom=False).count()} permanent presets, "
            f"{TaskOption.objects.filter(is_custom=True).count()} custom."
        ))
