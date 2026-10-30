"""Application routes are collected in attendance_system.urls for a single clear route table."""
from django.urls import path

from . import views

app_name = "attendance"
urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("students/", views.student_list, name="student_list"),
]
