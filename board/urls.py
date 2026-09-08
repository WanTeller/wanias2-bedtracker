"""URL patterns for the board app: which web address runs which view.

Everything that belongs to one board lives under  /w/<slug>/  so the board is
always known from the address. The bare  /  is the front page.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),

    # Front page: "your boards" dashboard.
    path("", views.home, name="home"),
    path("boards/new/", views.board_new, name="board_new"),
    path("boards/join/", views.join_paste, name="join_paste"),
    path("join/<str:token>/", views.join, name="join"),

    # --- one board, everything scoped under its slug ---------------------- #
    path("w/<slug:slug>/", views.board_view, name="board"),
    path("w/<slug:slug>/activity/", views.activity_view, name="activity"),
    path("w/<slug:slug>/rotate-link/", views.rotate_link, name="rotate_link"),
    path("w/<slug:slug>/dev/clear/", views.dev_clear, name="dev_clear"),

    # patient
    path("w/<slug:slug>/bed/<int:bed_id>/save/", views.save_patient, name="save_patient"),
    path("w/<slug:slug>/bed/<int:bed_id>/discharge/", views.discharge_patient, name="discharge_patient"),

    # tasks (HTMX)
    path("w/<slug:slug>/bed/<int:bed_id>/task/add/", views.task_add, name="task_add"),
    path("w/<slug:slug>/task/<int:task_id>/toggle/", views.task_toggle, name="task_toggle"),
    path("w/<slug:slug>/task/<int:task_id>/cancel/", views.task_cancel, name="task_cancel"),
    path("w/<slug:slug>/task/<int:task_id>/edit/", views.task_edit, name="task_edit"),
    path("w/<slug:slug>/bed/<int:bed_id>/slot/<slug:cat_key>/toggle/", views.slot_toggle, name="slot_toggle"),
    path("w/<slug:slug>/category/<slug:cat_key>/option/add/", views.option_add, name="option_add"),
    path("w/<slug:slug>/option/<int:option_id>/delete/", views.option_delete, name="option_delete"),

    # notes & vitals (HTMX)
    path("w/<slug:slug>/bed/<int:bed_id>/note/add/", views.note_add, name="note_add"),
    path("w/<slug:slug>/bed/<int:bed_id>/vitals/add/", views.vitals_add, name="vitals_add"),
]
