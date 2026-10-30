from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from attendance import views

urlpatterns = [
    path("", RedirectView.as_view(pattern_name="dashboard", permanent=False), name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("students/", views.student_list, name="student-list"),
    path("students/register/", views.student_create, name="student-create"),
    path("students/<int:pk>/", views.student_detail, name="student-detail"),
    path("students/<int:pk>/edit/", views.student_edit, name="student-edit"),
    path("students/<int:pk>/delete/", views.student_delete, name="student-delete"),
    path("students/<int:pk>/photo/", views.student_photo, name="student-photo"),
    path("attendance/mark/", views.mark_attendance_page, name="mark-attendance"),
    path("attendance/recognize/", views.recognize_attendance, name="recognize-attendance"),
    path("attendance/records/", views.attendance_records, name="attendance-records"),
    path("attendance/<int:pk>/toggle/", views.attendance_toggle_status, name="attendance-toggle"),
    path("attendance/export.csv/", views.attendance_export, name="attendance-export"),
    path("settings/", views.settings_view, name="settings"),
    path("manus-routes.json", views.route_manifest, name="route-manifest"),
    path("admin/", admin.site.urls),
]
