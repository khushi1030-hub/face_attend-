from django.contrib import admin

from .models import Attendance, AttendanceSession, Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ("name", "roll_number", "branch", "semester", "email", "created_at")
    search_fields = ("name", "roll_number", "email", "branch")
    list_filter = ("branch", "semester")
    readonly_fields = ("face_encoding", "created_at")


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ("date", "opened_by", "created_at")
    readonly_fields = ("date", "opened_by", "created_at")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("student", "date", "time", "status")
    list_filter = ("date", "status")
    search_fields = ("student__name", "student__roll_number")
    readonly_fields = ("student", "session", "date", "time", "status", "created_at")
