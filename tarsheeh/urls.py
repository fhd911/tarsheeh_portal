from django.urls import path
from . import views

app_name = "tarsheeh"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("batch/new/", views.create_batch, name="create_batch"),
    path("opportunity/new/", views.create_opportunity, name="create_opportunity"),

    path("add/manual/", views.add_manual, name="add_manual"),
    path("add/paste/", views.paste_import, name="paste_import"),

    path("applications/", views.applications, name="applications"),
    path("scores/", views.scores, name="scores"),
]
