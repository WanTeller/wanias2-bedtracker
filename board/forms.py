"""
A Form describes which fields a user can fill in, validates what they submit,
and can save it straight to the database.

PatientForm is a "ModelForm": it builds itself from the Patient model, so we
just list the fields we want on screen.
"""

from django import forms

from .models import Patient, VitalsEntry, Ward


class BoardForm(forms.ModelForm):
    """Create-a-board form: a name and how many beds."""

    bed_count = forms.IntegerField(
        label="Number of beds", min_value=1, max_value=200, initial=44,
    )

    class Meta:
        model = Ward
        fields = ["name"]
        labels = {"name": "Board name"}
        widgets = {
            "name": forms.TextInput(
                attrs={"placeholder": "e.g. Medicine-2", "autocomplete": "off"}
            ),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            "name",
            "record_no",
            "age",
            "sex",
            "admission_date",
            "chief_complaint",
            "brief_history",
            "active_plan",
        ]
        widgets = {
            # type="date" makes the browser show a date picker.
            "admission_date": forms.DateInput(attrs={"type": "date"}),
            "chief_complaint": forms.Textarea(attrs={"rows": 2}),
            "brief_history": forms.Textarea(attrs={"rows": 3}),
            "active_plan": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "record_no": "Record no.",
            "chief_complaint": "Chief complaint",
            "brief_history": "Brief history",
            "active_plan": "Active management plan",
        }


class VitalsForm(forms.ModelForm):
    class Meta:
        model = VitalsEntry
        fields = [
            "recorded_at", "systolic", "diastolic", "pulse",
            "temp_c", "resp_rate", "spo2", "rbs", "note",
        ]
        widgets = {
            "recorded_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "note": forms.TextInput(attrs={"placeholder": "optional"}),
        }
        labels = {
            "temp_c": "Temp °C",
            "resp_rate": "RR",
            "spo2": "SpO₂ %",
            "rbs": "RBS",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill the timestamp with "now" for a new entry.
        if not self.instance.pk and not self.initial.get("recorded_at"):
            from django.utils import timezone
            self.initial["recorded_at"] = timezone.localtime().strftime(
                "%Y-%m-%dT%H:%M"
            )
