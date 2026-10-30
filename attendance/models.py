"""Database models for students, opened class days, and attendance."""
from django.conf import settings
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


class Student(models.Model):
    name = models.CharField(max_length=120)
    roll_number = models.CharField(max_length=32)
    branch = models.CharField(max_length=80)
    semester = models.PositiveSmallIntegerField()
    email = models.EmailField(max_length=254)
    profile_image = models.ImageField(upload_to="students/%Y/%m/", blank=True)
    # JSON-encoded 128-value face vector; never expose this field to templates or APIs.
    face_encoding = models.TextField(blank=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["name", "roll_number"]
        constraints = [
            models.UniqueConstraint(Lower("roll_number"), name="student_roll_number_ci_uniq"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.roll_number})"


class AttendanceSession(models.Model):
    """A class day explicitly opened by an admin via the Mark Attendance page."""
    date = models.DateField(unique=True, default=timezone.localdate)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="attendance_sessions_opened",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"Attendance session — {self.date:%d %b %Y}"


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = "Present", "Present"
        ABSENT = "Absent", "Absent"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="attendance_records")
    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name="records")
    date = models.DateField(default=timezone.localdate)
    time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ABSENT)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-date", "-time", "student__name"]
        constraints = [
            models.UniqueConstraint(fields=["student", "date"], name="unique_student_attendance_per_day"),
        ]
        indexes = [
            models.Index(fields=["date", "status"], name="attendance_date_status_idx"),
            models.Index(fields=["student", "date"], name="attendance_student_date_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.student.roll_number} — {self.status} — {self.date:%Y-%m-%d}"
