"""URL patterns for the board app: which web address runs which view."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.board_view, name="board"),
    path("healthz/", views.healthz, name="healthz"),
    path("activity/", views.activity_view, name="activity"),
    path("dev/clear/", views.dev_clear, name="dev_clear"),

    # patient
    path("bed/<int:bed_id>/save/", views.save_patient, name="save_patient"),
    path("bed/<int:bed_id>/discharge/", views.discharge_patient, name="discharge_patient"),

    # tasks (HTMX)
    path("bed/<int:bed_id>/task/add/", views.task_add, name="task_add"),
    path("task/<int:task_id>/toggle/", views.task_toggle, name="task_toggle"),
    path("task/<int:task_id>/cancel/", views.task_cancel, name="task_cancel"),
    path("task/<int:task_id>/edit/", views.task_edit, name="task_edit"),
    path("bed/<int:bed_id>/slot/<slug:cat_key>/toggle/", views.slot_toggle, name="slot_toggle"),
    path("category/<slug:cat_key>/option/add/", views.option_add, name="option_add"),
    path("option/<int:option_id>/delete/", views.option_delete, name="option_delete"),

    # notes & vitals (HTMX)
    path("bed/<int:bed_id>/note/add/", views.note_add, name="note_add"),
    path("bed/<int:bed_id>/vitals/add/", views.vitals_add, name="vitals_add"),
]
