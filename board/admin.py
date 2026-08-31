"""
Registering models here gives us a ready-made web UI at /admin/ to view and
edit data directly - useful for checking things while we build, and later for
the developer-only maintenance tasks.
"""

from django.contrib import admin

from .models import (
    Ward, Bed, Patient, ActivityEvent,
    TaskCategory, TaskOption, Task,
    Note, VitalsEntry,
)


@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ["name", "bed_count", "occupied_count"]


@admin.register(Bed)
class BedAdmin(admin.ModelAdmin):
    list_display = ["__str__", "ward", "is_occupied", "current_patient"]
    list_filter = ["ward"]
    ordering = ["ward", "number"]


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ["display_label", "bed", "status", "admission_date"]
    list_filter = ["status", "sex"]
    search_fields = ["name", "record_no"]


@admin.register(ActivityEvent)
class ActivityEventAdmin(admin.ModelAdmin):
    list_display = ["created_at", "kind", "summary", "patient", "bed", "actor_name"]
    list_filter = ["kind", "created_at", "actor"]
    search_fields = ["summary", "actor_name"]
    readonly_fields = ["created_at"]


class TaskOptionInline(admin.TabularInline):
    model = TaskOption
    extra = 0


@admin.register(TaskCategory)
class TaskCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "key", "sort_order", "overdue_after_minutes",
                    "allow_custom", "pair_group"]
    ordering = ["sort_order"]
    inlines = [TaskOptionInline]


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "patient", "status", "created_at", "due_at"]
    list_filter = ["status", "category"]
    search_fields = ["name"]


@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ["patient", "created_at", "__str__"]
    search_fields = ["body"]


@admin.register(VitalsEntry)
class VitalsEntryAdmin(admin.ModelAdmin):
    list_display = ["patient", "recorded_at", "bp", "pulse", "temp_c", "spo2"]
