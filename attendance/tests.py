"""Functional tests for the main Django workflows and database constraints."""
import base64
import csv
import io
import json
from datetime import date, timedelta
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from .face_recognition_utils import FaceRecognitionError, compare_faces, generate_face_encoding
from .models import Attendance, AttendanceSession, Student


def make_image_bytes(color=(245, 245, 245), image_format="JPEG"):
    output = io.BytesIO()
    Image.new("RGB", (240, 240), color=color).save(output, format=image_format)
    return output.getvalue()


def image_data_url(content=None):
    content = content if content is not None else make_image_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(content).decode("ascii")


def make_uploaded_image(filename="student.jpg"):
    return SimpleUploadedFile(filename, make_image_bytes(), content_type="image/jpeg")


class StaffTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="campus-admin",
            password="Strong-passphrase-2026!",
            is_staff=True,
            is_superuser=True,
        )
        self.client.login(username="campus-admin", password="Strong-passphrase-2026!")

    def make_student(self, name="Aisha Mehta", roll="23CSE101", encoding=None):
        return Student.objects.create(
            name=name,
            roll_number=roll,
            branch="Computer Science",
            semester=5,
            email=f"{roll.lower()}@college.edu",
            face_encoding=json.dumps(encoding or [0.0] * 128),
        )


class AuthenticationAndPageTests(StaffTestCase):
    def test_dashboard_requires_staff_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_staff_login_and_post_logout_work(self):
        self.client.logout()
        response = self.client.post(reverse("login"), {"username": "campus-admin", "password": "Strong-passphrase-2026!"})
        self.assertRedirects(response, reverse("dashboard"))
        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))

    def test_login_form_sets_token_and_accepts_csrf_protected_post(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        csrf_cookie = client.cookies.get("csrftoken")
        self.assertIsNotNone(csrf_cookie)
        response = client.post(
            reverse("login"),
            {"username": "campus-admin", "password": "Strong-passphrase-2026!"},
            HTTP_X_CSRFTOKEN=csrf_cookie.value,
        )
        self.assertRedirects(response, reverse("dashboard"))

    def test_logout_requires_post(self):
        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 405)

    def test_all_primary_pages_render_for_staff(self):
        student = self.make_student()
        AttendanceSession.objects.create(date=timezone.localdate(), opened_by=self.user)
        urls = [
            reverse("dashboard"), reverse("student-list"), reverse("student-create"),
            reverse("mark-attendance"), reverse("attendance-records"),
            reverse("student-detail", args=[student.pk]), reverse("student-edit", args=[student.pk]),
            reverse("settings"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_route_manifest_is_valid_json_with_page_routes(self):
        response = self.client.get(reverse("route-manifest"))
        self.assertEqual(response.status_code, 200)
        manifest = json.loads(response.content)
        self.assertEqual(set(manifest), {"routes"})
        paths = {route["path"] for route in manifest["routes"]}
        self.assertIn("/dashboard/", paths)
        self.assertIn("/students/:pk/", paths)
        self.assertNotIn("/attendance/recognize/", paths)


class StudentManagementTests(StaffTestCase):
    def setUp(self):
        super().setUp()
        self.temporary_media = TemporaryDirectory(prefix="campus-attendance-tests-")
        self.addCleanup(self.temporary_media.cleanup)
        self.media_settings = override_settings(MEDIA_ROOT=self.temporary_media.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)

    def test_duplicate_roll_number_is_rejected(self):
        self.make_student()
        response = self.client.post(reverse("student-create"), {
            "name": "Another Student", "roll_number": "23cse101", "branch": "CSE",
            "semester": 3, "email": "another@college.edu", "profile_image": make_uploaded_image(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered")
        self.assertEqual(Student.objects.count(), 1)

    def test_database_enforces_case_insensitive_roll_number_uniqueness(self):
        self.make_student()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Student.objects.create(
                    name="Duplicate Case",
                    roll_number="23cse101",
                    branch="Computer Science",
                    semester=5,
                    email="duplicate-case@college.edu",
                    face_encoding=json.dumps([0.0] * 128),
                )

    def test_no_face_image_is_rejected_during_registration(self):
        response = self.client.post(reverse("student-create"), {
            "name": "Blank Image", "roll_number": "23ECE201", "branch": "ECE",
            "semester": 2, "email": "blank@college.edu",
            "profile_image": SimpleUploadedFile("blank.jpg", make_image_bytes(), content_type="image/jpeg"),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No face detected")
        self.assertFalse(Student.objects.filter(roll_number="23ECE201").exists())

    @patch("attendance.views.generate_face_encoding", return_value=np.zeros(128, dtype=np.float64))
    def test_valid_photo_registration_stores_face_encoding(self, _encoding):
        opened_session = AttendanceSession.objects.create(date=timezone.localdate(), opened_by=self.user)
        response = self.client.post(reverse("student-create"), {
            "name": "Mina Patel", "roll_number": "23CSE301", "branch": "CSE",
            "semester": 4, "email": "mina@college.edu", "profile_image": make_uploaded_image(),
        })
        student = Student.objects.get(roll_number="23CSE301")
        self.assertRedirects(response, reverse("student-detail", args=[student.pk]))
        self.assertEqual(len(json.loads(student.face_encoding)), 128)
        self.assertTrue(student.profile_image)
        self.assertEqual(Attendance.objects.get(student=student, session=opened_session).status, Attendance.Status.ABSENT)

    def test_student_can_be_edited_without_replacing_verified_face(self):
        student = self.make_student()
        response = self.client.post(reverse("student-edit", args=[student.pk]), {
            "name": "Aisha Updated", "roll_number": student.roll_number, "branch": student.branch,
            "semester": 6, "email": student.email,
        })
        student.refresh_from_db()
        self.assertRedirects(response, reverse("student-detail", args=[student.pk]))
        self.assertEqual(student.name, "Aisha Updated")
        self.assertEqual(student.semester, 6)
        self.assertEqual(len(json.loads(student.face_encoding)), 128)

    def test_student_delete_removes_student_and_attendance_history(self):
        student = self.make_student()
        session = AttendanceSession.objects.create(date=timezone.localdate(), opened_by=self.user)
        Attendance.objects.create(student=student, session=session, date=session.date)
        response = self.client.post(reverse("student-delete", args=[student.pk]))
        self.assertRedirects(response, reverse("student-list"))
        self.assertFalse(Student.objects.filter(pk=student.pk).exists())
        self.assertFalse(Attendance.objects.filter(student_id=student.pk).exists())

    def test_missing_required_fields_and_invalid_email_are_rejected(self):
        missing = self.client.post(reverse("student-create"), {})
        self.assertEqual(missing.status_code, 200)
        self.assertIn("name", missing.context["form"].errors)
        self.assertIn("profile_image", missing.context["form"].errors)
        invalid_email = self.client.post(reverse("student-create"), {
            "name": "Invalid Email", "roll_number": "23CSE402", "branch": "CSE",
            "semester": 3, "email": "not-an-email", "profile_image": make_uploaded_image(),
        })
        self.assertEqual(invalid_email.status_code, 200)
        self.assertFalse(Student.objects.filter(roll_number="23CSE402").exists())

    def test_invalid_semester_is_reported(self):
        response = self.client.post(reverse("student-create"), {
            "name": "Out of Range", "roll_number": "23CSE401", "branch": "CSE",
            "semester": 13, "email": "bad@college.edu", "profile_image": make_uploaded_image(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "between 1 and 12")
        self.assertFalse(Student.objects.filter(roll_number="23CSE401").exists())


class RecognitionUtilityTests(TestCase):
    def test_blank_image_returns_real_no_face_error(self):
        with self.assertRaises(FaceRecognitionError) as error:
            generate_face_encoding(make_image_bytes())
        self.assertEqual(error.exception.code, "no_face")
        self.assertIn("No face detected", error.exception.message)

    @patch("attendance.face_recognition_utils.detect_face", return_value=[(10, 100, 100, 10), (20, 180, 120, 90)])
    def test_multiple_face_detection_is_rejected_before_encoding(self, _boxes):
        with self.assertRaises(FaceRecognitionError) as error:
            generate_face_encoding(make_image_bytes())
        self.assertEqual(error.exception.code, "multiple_faces")

    def test_real_face_distance_comparison_is_conservative(self):
        candidate = np.zeros(128, dtype=np.float64)
        close_index, close_distance = compare_faces([[0.0] * 128], candidate)
        far_index, far_distance = compare_faces([[1.0] * 128], candidate)
        self.assertEqual(close_index, 0)
        self.assertEqual(close_distance, 0.0)
        self.assertIsNone(far_index)
        self.assertGreater(far_distance, 0.48)


class AttendanceWorkflowTests(StaffTestCase):
    def test_opening_mark_attendance_creates_session_and_absent_rows(self):
        first = self.make_student()
        second = self.make_student(name="Mina Patel", roll="23CSE102")
        response = self.client.get(reverse("mark-attendance"))
        self.assertEqual(response.status_code, 200)
        session = AttendanceSession.objects.get(date=timezone.localdate())
        self.assertEqual(session.records.count(), 2)
        self.assertEqual(session.records.filter(status=Attendance.Status.ABSENT).count(), 2)
        self.assertSetEqual(set(session.records.values_list("student_id", flat=True)), {first.pk, second.pk})

    def test_recognized_student_is_marked_once_and_repeat_is_duplicate(self):
        student = self.make_student()
        self.client.get(reverse("mark-attendance"))
        frame = json.dumps({"image": image_data_url()})
        with patch("attendance.views.recognize_face", return_value=(student, 0.1)):
            first = self.client.post(reverse("recognize-attendance"), data=frame, content_type="application/json")
            second = self.client.post(reverse("recognize-attendance"), data=frame, content_type="application/json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["recognized"], True)
        self.assertEqual(first.json()["attendance_marked"], True)
        self.assertEqual(first.json()["student_name"], student.name)
        self.assertEqual(set(first.json()), {"recognized", "action", "attendance_marked", "student_name", "roll_number", "message", "date", "time"})
        self.assertEqual(first.json()["date"], timezone.localdate().isoformat())
        self.assertTrue(first.json()["time"])
        self.assertEqual(second.json()["attendance_marked"], False)
        self.assertEqual(second.json()["message"], "Attendance already marked today.")
        self.assertEqual(Attendance.objects.filter(student=student, date=timezone.localdate()).count(), 1)

    def test_unknown_face_creates_no_attendance(self):
        self.make_student()
        self.client.get(reverse("mark-attendance"))
        with patch("attendance.views.recognize_face", return_value=(None, 0.8)):
            response = self.client.post(
                reverse("recognize-attendance"),
                data=json.dumps({"image": image_data_url()}),
                content_type="application/json",
            )
        self.assertEqual(response.json()["message"], "Student not recognized.")
        self.assertEqual(Attendance.objects.filter(status=Attendance.Status.PRESENT).count(), 0)

    def test_no_face_frame_does_not_mark_attendance(self):
        self.make_student()
        self.client.get(reverse("mark-attendance"))
        response = self.client.post(
            reverse("recognize-attendance"),
            data=json.dumps({"image": image_data_url()}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("No face detected", response.json()["message"])
        self.assertEqual(Attendance.objects.filter(status=Attendance.Status.PRESENT).count(), 0)

    @patch("attendance.face_recognition_utils.detect_face", return_value=[(10, 100, 100, 10), (20, 180, 120, 90)])
    def test_multiple_face_frame_does_not_mark_attendance(self, _boxes):
        self.make_student()
        self.client.get(reverse("mark-attendance"))
        response = self.client.post(
            reverse("recognize-attendance"),
            data=json.dumps({"image": image_data_url()}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Multiple faces detected", response.json()["message"])
        self.assertEqual(Attendance.objects.filter(status=Attendance.Status.PRESENT).count(), 0)

    def test_invalid_frame_returns_structured_error(self):
        response = self.client.post(
            reverse("recognize-attendance"),
            data=json.dumps({"image": "bad-data"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("message", response.json())
        self.assertNotIn("face_encoding", response.json())

    def test_database_prevents_duplicate_student_date(self):
        student = self.make_student()
        session = AttendanceSession.objects.create(date=timezone.localdate(), opened_by=self.user)
        Attendance.objects.create(student=student, session=session, date=session.date)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Attendance.objects.create(student=student, session=session, date=session.date)

    def test_student_detail_uses_session_days_on_or_after_enrollment(self):
        student = self.make_student()
        today = timezone.localdate()
        earlier = today - timedelta(days=1)
        earlier_session = AttendanceSession.objects.create(date=earlier, opened_by=self.user)
        current_session = AttendanceSession.objects.create(date=today, opened_by=self.user)
        Attendance.objects.create(student=student, session=earlier_session, date=earlier, status=Attendance.Status.PRESENT)
        Attendance.objects.create(student=student, session=current_session, date=today, status=Attendance.Status.ABSENT)
        response = self.client.get(reverse("student-detail", args=[student.pk]))
        self.assertEqual(response.context["total_classes"], 1)
        self.assertEqual(response.context["present_count"], 0)
        self.assertEqual(response.context["absent_count"], 1)
        self.assertEqual(response.context["attendance_percentage"], 0)

    def test_csv_escapes_formula_inputs_in_every_user_text_column(self):
        student = self.make_student(name="=HYPERLINK(\"x\")", roll="+12345")
        student.branch = "@SUM(A1:A2)"
        student.save(update_fields=["branch"])
        session = AttendanceSession.objects.create(date=timezone.localdate(), opened_by=self.user)
        Attendance.objects.create(student=student, session=session, date=session.date)
        response = self.client.get(reverse("attendance-export"))
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(rows[1][0], "'=HYPERLINK(\"x\")")
        self.assertEqual(rows[1][1], "'+12345")
        self.assertEqual(rows[1][2], "'@SUM(A1:A2)")

    def test_dashboard_statistics_come_from_database_rows(self):
        student = self.make_student()
        self.client.get(reverse("mark-attendance"))
        record = Attendance.objects.get(student=student, date=timezone.localdate())
        record.status = Attendance.Status.PRESENT
        record.time = timezone.localtime().time().replace(microsecond=0)
        record.save(update_fields=["status", "time"])
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["total_students"], 1)
        self.assertEqual(response.context["present_today"], 1)
        self.assertEqual(response.context["absent_today"], 0)
        self.assertEqual(response.context["attendance_percentage"], 100)
        self.assertContains(response, "Attendance trend")

    def test_search_date_student_filters_pagination_and_csv_use_database(self):
        one = self.make_student(name="Aisha Mehta", roll="23CSE101")
        two = self.make_student(name="Mina Patel", roll="23ECE201")
        day = timezone.localdate()
        session = AttendanceSession.objects.create(date=day, opened_by=self.user)
        Attendance.objects.create(student=one, session=session, date=day, status=Attendance.Status.PRESENT, time=timezone.localtime().time())
        Attendance.objects.create(student=two, session=session, date=day, status=Attendance.Status.ABSENT)
        filtered = self.client.get(reverse("attendance-records"), {"q": "Aisha", "date": day.isoformat(), "student": one.pk})
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.context["page_obj"].paginator.count, 1)
        self.assertContains(filtered, one.roll_number)
        exported = self.client.get(reverse("attendance-export"), {"student": one.pk})
        rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"))))
        self.assertEqual(rows[0], ["Student Name", "Roll Number", "Branch", "Date", "Time", "Status"])
        self.assertEqual(rows[1][0], one.name)
        self.assertEqual(rows[1][1], one.roll_number)
        self.assertEqual(rows[1][-1], Attendance.Status.PRESENT)

        for offset in range(1, 17):
            old_day = day - timedelta(days=offset)
            old_session = AttendanceSession.objects.create(date=old_day, opened_by=self.user)
            Attendance.objects.create(student=one, session=old_session, date=old_day, status=Attendance.Status.ABSENT)
        page_two = self.client.get(reverse("attendance-records"), {"student": one.pk, "page": 2})
        self.assertEqual(page_two.status_code, 200)
        self.assertEqual(page_two.context["page_obj"].number, 2)

    def test_attendance_toggle_status_mark_absent_and_present(self):
        student = self.make_student(name="Rahul Sharma", roll="23CSE105")
        day = timezone.localdate()
        session = AttendanceSession.objects.create(date=day, opened_by=self.user)
        record = Attendance.objects.create(
            student=student,
            session=session,
            date=day,
            status=Attendance.Status.PRESENT,
            time=timezone.localtime().time(),
        )

        # Mark Absent (e.g. left early)
        response = self.client.post(
            reverse("attendance-toggle", args=[record.pk]),
            {"action": "mark_absent", "next": reverse("dashboard")},
        )
        self.assertRedirects(response, reverse("dashboard"))
        record.refresh_from_db()
        self.assertEqual(record.status, Attendance.Status.ABSENT)
        self.assertIsNone(record.time)

        # Mark Present
        response = self.client.post(
            reverse("attendance-toggle", args=[record.pk]),
            {"action": "mark_present", "next": reverse("dashboard")},
        )
        self.assertRedirects(response, reverse("dashboard"))
        record.refresh_from_db()
        self.assertEqual(record.status, Attendance.Status.PRESENT)
        self.assertIsNotNone(record.time)

    def test_recognized_student_exit_scan_marks_absent(self):
        student = self.make_student(name="Samir Khan", roll="23CSE109")
        self.client.get(reverse("mark-attendance"))
        frame_entry = json.dumps({"image": image_data_url(), "mode": "entry"})
        frame_exit = json.dumps({"image": image_data_url(), "mode": "exit"})

        with patch("attendance.views.recognize_face", return_value=(student, 0.1)):
            # 1. Entry scan -> marks Present
            entry_resp = self.client.post(reverse("recognize-attendance"), data=frame_entry, content_type="application/json")
            self.assertEqual(entry_resp.json()["attendance_marked"], True)
            record = Attendance.objects.get(student=student, date=timezone.localdate())
            self.assertEqual(record.status, Attendance.Status.PRESENT)

            # 2. Exit scan -> marks Left Early / Absent
            exit_resp = self.client.post(reverse("recognize-attendance"), data=frame_exit, content_type="application/json")
            self.assertEqual(exit_resp.json()["attendance_marked"], True)
            self.assertEqual(exit_resp.json()["action"], "exit")
            self.assertIn("Left Early", exit_resp.json()["message"])
            record.refresh_from_db()
            self.assertEqual(record.status, Attendance.Status.ABSENT)
            self.assertIsNone(record.time)

            # 3. Repeat Exit scan on already Absent student
            repeat_exit = self.client.post(reverse("recognize-attendance"), data=frame_exit, content_type="application/json")
            self.assertEqual(repeat_exit.json()["attendance_marked"], False)
            self.assertIn("already marked Absent", repeat_exit.json()["message"])
