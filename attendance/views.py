"""Request handlers for the admin dashboard and real face-recognition workflow."""
import csv
import json
import logging
import mimetypes
import uuid
from datetime import date, datetime

from django.contrib import messages

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.cache import patch_cache_control
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.utils.http import url_has_allowed_host_and_scheme

from .face_recognition_utils import FaceRecognitionError, decode_data_url, generate_face_encoding, recognize_face
from .forms import StudentForm
from .models import Attendance, AttendanceSession, Student

logger = logging.getLogger(__name__)


def private_staff_view(view):
    """Require staff access and prevent authenticated data from entering shared caches."""
    return never_cache(staff_member_required(login_url="login")(view))


@never_cache
def login_view(request):
    """Authenticate only staff accounts; student records are never self-service accounts."""
    if request.user.is_authenticated and request.user.is_staff:
        return redirect("dashboard")
    form = AuthenticationForm(request, data=request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        if not user.is_staff or not user.is_active:
            form.add_error(None, "This account does not have administrator access.")
        else:
            login(request, user)
            next_url = request.GET.get("next", "")
            if not url_has_allowed_host_and_scheme(next_url, {request.get_host()}, require_https=request.is_secure()):
                next_url = ""
            return redirect(next_url or "dashboard")
    return render(request, "login.html", {"form": form})


@private_staff_view
@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


def _today() -> date:
    return timezone.localdate()


def _create_absent_rows(session: AttendanceSession) -> None:
    """Initialize every student enrolled by this session date as absent, idempotently."""
    students = Student.objects.filter(created_at__date__lte=session.date).only("id").iterator(chunk_size=500)
    pending = [
        Attendance(student_id=student.id, session=session, date=session.date, status=Attendance.Status.ABSENT)
        for student in students
    ]
    if pending:
        Attendance.objects.bulk_create(pending, ignore_conflicts=True, batch_size=500)


def _open_today_session(user) -> AttendanceSession:
    """Open one class session for today and create its initial absent attendance rows."""
    today = _today()
    try:
        with transaction.atomic():
            session, _created = AttendanceSession.objects.get_or_create(
                date=today,
                defaults={"opened_by": user if getattr(user, "is_authenticated", False) else None},
            )
            _create_absent_rows(session)
            return session
    except IntegrityError:
        # Another request may have opened the same day between the read and insert.
        session = AttendanceSession.objects.get(date=today)
        _create_absent_rows(session)
        return session


def _add_student_to_open_session(student: Student) -> None:
    """A student registered after today's page was opened still belongs in today's roll call."""
    today = _today()
    session = AttendanceSession.objects.filter(date=today).first()
    if session:
        Attendance.objects.get_or_create(
            student=student,
            date=today,
            defaults={"session": session, "status": Attendance.Status.ABSENT},
        )


def _store_student(form: StudentForm) -> tuple[Student | None, str | None]:
    """Validate the chosen photo with the real recognizer, then save its image and vector."""
    student = form.save(commit=False)
    webcam_data = form.cleaned_data.get("webcam_image", "")
    new_upload = bool(form.files.get("profile_image"))
    old_image_name = student.profile_image.name if student.pk and student.profile_image else ""
    image_source = None

    try:
        if webcam_data:
            image_bytes = decode_data_url(webcam_data)
            encoding = generate_face_encoding(image_bytes)
            image_source = (image_bytes, "webcam")
        elif new_upload:
            uploaded = form.cleaned_data["profile_image"]
            uploaded.seek(0)
            encoding = generate_face_encoding(uploaded)
            uploaded.seek(0)
        else:
            encoding = None

        if encoding is not None:
            student.face_encoding = json.dumps([float(value) for value in encoding.tolist()])
        if webcam_data and image_source:
            image_bytes, _source = image_source
            student.profile_image.save(
                f"capture-{uuid.uuid4().hex[:12]}.jpg",
                ContentFile(image_bytes),
                save=False,
            )
        student.save()
        form.save_m2m()
        if old_image_name and student.profile_image.name != old_image_name:
            try:
                student.profile_image.storage.delete(old_image_name)
            except OSError:
                logger.warning("Could not remove superseded profile image for student id=%s", student.pk)
        _add_student_to_open_session(student)
        return student, None
    except FaceRecognitionError as error:
        target = "webcam_image" if webcam_data else "profile_image"
        form.add_error(target, error.message)
        return None, error.message
    except IntegrityError:
        form.add_error("roll_number", "A student with this roll number is already registered.")
        return None, "duplicate_roll_number"
    except Exception:
        logger.exception("Unexpected error while saving student registration")
        form.add_error(None, "We could not save this student. Check the image and details, then try again.")
        return None, "save_error"


@private_staff_view
def dashboard(request):
    today = _today()
    total_students = Student.objects.count()
    session = AttendanceSession.objects.filter(date=today).first()
    present_today = absent_today = 0
    if session:
        present_today = Attendance.objects.filter(session=session, status=Attendance.Status.PRESENT).count()
        absent_today = Attendance.objects.filter(session=session, status=Attendance.Status.ABSENT).count()
    attendance_percentage = round((present_today / total_students) * 100) if total_students else 0

    recent_attendance = Attendance.objects.select_related("student", "session").order_by(
        "-date", "-time", "student__name"
    )[:8]
    sessions = list(AttendanceSession.objects.filter(date__lte=today).order_by("-date")[:7])
    sessions.reverse()
    chart_labels = [session.date.strftime("%d %b") for session in sessions]
    chart_present = [
        Attendance.objects.filter(session=session, status=Attendance.Status.PRESENT).count()
        for session in sessions
    ]
    chart_absent = [
        Attendance.objects.filter(session=session, status=Attendance.Status.ABSENT).count()
        for session in sessions
    ]
    chart_total = [present + absent for present, absent in zip(chart_present, chart_absent)]
    chart_context = {
        "labels": chart_labels,
        "present": chart_present,
        "absent": chart_absent,
        "total": chart_total,
        "today_present": present_today,
        "today_absent": absent_today,
    }
    return render(request, "dashboard.html", {
        "total_students": total_students,
        "present_today": present_today,
        "absent_today": absent_today,
        "attendance_percentage": attendance_percentage,
        "today_session": session,
        "recent_attendance": recent_attendance,
        "chart_data": chart_context,
        "today": today,
    })


@private_staff_view
def student_list(request):
    search = request.GET.get("q", "").strip()
    queryset = Student.objects.annotate(
        total_classes=Count("attendance_records", distinct=True),
        present_classes=Count(
            "attendance_records",
            filter=Q(attendance_records__status=Attendance.Status.PRESENT),
            distinct=True,
        ),
    ).order_by("name", "roll_number")
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(roll_number__icontains=search)
            | Q(branch__icontains=search) | Q(email__icontains=search)
        )
    page_obj = Paginator(queryset, 12).get_page(request.GET.get("page"))
    for student in page_obj.object_list:
        student.attendance_percentage = round(student.present_classes * 100 / student.total_classes) if student.total_classes else 0
    return render(request, "students.html", {"page_obj": page_obj, "search": search})


@private_staff_view
def student_create(request):
    form = StudentForm(request.POST if request.method == "POST" else None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        student, error = _store_student(form)
        if student:
            messages.success(request, f"{student.name} was registered with a verified face encoding.")
            return redirect("student-detail", pk=student.pk)
        if error not in {"duplicate_roll_number", "save_error"}:
            logger.info("Student registration was rejected by face/image validation.")
    return render(request, "student_form.html", {"form": form, "page_title": "Register student", "is_edit": False})


@private_staff_view
def student_edit(request, pk):
    student = get_object_or_404(Student, pk=pk)
    form = StudentForm(request.POST if request.method == "POST" else None, request.FILES or None, instance=student)
    if request.method == "POST" and form.is_valid():
        saved, _error = _store_student(form)
        if saved:
            messages.success(request, f"{saved.name}'s profile was updated.")
            return redirect("student-detail", pk=saved.pk)
    return render(request, "student_form.html", {
        "form": form,
        "page_title": "Edit student",
        "is_edit": True,
        "student": student,
    })


@private_staff_view
def student_delete(request, pk):
    if request.method != "POST":
        return redirect("student-detail", pk=pk)
    student = get_object_or_404(Student, pk=pk)
    name = student.name
    if student.profile_image:
        try:
            student.profile_image.delete(save=False)
        except OSError:
            logger.warning("Could not remove profile image while deleting student id=%s", student.pk)
    student.delete()
    messages.success(request, f"{name} and their attendance history were deleted.")
    return redirect("student-list")


@private_staff_view
def student_detail(request, pk):
    student = get_object_or_404(Student, pk=pk)
    enrolled_on = timezone.localtime(student.created_at).date()
    sessions_since_enrollment = AttendanceSession.objects.filter(date__gte=enrolled_on, date__lte=_today())
    total_classes = sessions_since_enrollment.count()
    enrollment_records = student.attendance_records.filter(session__in=sessions_since_enrollment)
    present = enrollment_records.filter(status=Attendance.Status.PRESENT).count()
    absent = max(total_classes - present, 0)
    percentage = round(present * 100 / total_classes) if total_classes else 0
    history = enrollment_records.select_related("session").order_by("-date", "-time")
    page_obj = Paginator(history, 15).get_page(request.GET.get("page"))
    return render(request, "student_detail.html", {
        "student": student,
        "total_classes": total_classes,
        "present_count": present,
        "absent_count": absent,
        "attendance_percentage": percentage,
        "page_obj": page_obj,
    })


@private_staff_view
def student_photo(request, pk):
    """Serve student photos only to staff; do not expose the media directory publicly."""
    student = get_object_or_404(Student, pk=pk)
    if not student.profile_image:
        raise Http404("Photo not found")
    try:
        student.profile_image.open("rb")
    except (FileNotFoundError, OSError):
        raise Http404("Photo not found")
    content_type = mimetypes.guess_type(student.profile_image.name)[0] or "application/octet-stream"
    response = FileResponse(student.profile_image.file, content_type=content_type)
    patch_cache_control(response, private=True, no_store=True)
    return response


@private_staff_view
def mark_attendance_page(request):
    session = _open_today_session(request.user)
    return render(request, "mark_attendance.html", {
        "today_session": session,
        "student_count": Student.objects.count(),
    })


@private_staff_view
@require_POST
def recognize_attendance(request):
    """Accept one webcam JPEG, recognize one registered face and update today's session."""
    try:
        if len(request.body) > 7 * 1024 * 1024:
            return JsonResponse({"recognized": False, "attendance_marked": False, "message": "The captured frame is too large. Please try again."}, status=413)
        payload = json.loads(request.body.decode("utf-8"))
        image_data = payload.get("image", "")
        mode = payload.get("mode", "entry").strip().lower()
        image_bytes = decode_data_url(image_data, max_bytes=5 * 1024 * 1024)
        students = Student.objects.exclude(face_encoding="").only("id", "name", "roll_number", "face_encoding")
        student, _distance = recognize_face(image_bytes, students)
        if student is None:
            return JsonResponse({
                "recognized": False,
                "attendance_marked": False,
                "message": "Student not recognized.",
            })
        today = _today()
        session = AttendanceSession.objects.filter(date=today).first()
        if session is None:
            return JsonResponse({
                "recognized": False,
                "attendance_marked": False,
                "message": "Open today's attendance session before scanning students.",
            }, status=409)

        if mode == "exit":
            try:
                with transaction.atomic():
                    _create_absent_rows(session)
                    record, _created = Attendance.objects.get_or_create(
                        student=student,
                        date=today,
                        defaults={"session": session, "status": Attendance.Status.ABSENT},
                    )
                    record = Attendance.objects.select_for_update().get(pk=record.pk)
                    if record.status == Attendance.Status.PRESENT:
                        record.status = Attendance.Status.ABSENT
                        record.time = None
                        record.save(update_fields=["status", "time"])
                        revoked = True
                    else:
                        revoked = False
            except IntegrityError:
                record = Attendance.objects.get(student=student, date=today)
                revoked = record.status == Attendance.Status.PRESENT
                if revoked:
                    record.status = Attendance.Status.ABSENT
                    record.time = None
                    record.save(update_fields=["status", "time"])

            return JsonResponse({
                "recognized": True,
                "action": "exit",
                "attendance_marked": revoked,
                "student_name": student.name,
                "roll_number": student.roll_number,
                "message": "Student marked Left Early (attendance revoked)." if revoked else "Student was already marked Absent.",
                "date": timezone.localtime().date().isoformat(),
                "time": timezone.localtime().strftime("%I:%M %p"),
            })
        else:
            try:
                with transaction.atomic():
                    _create_absent_rows(session)
                    record, _created = Attendance.objects.get_or_create(
                        student=student,
                        date=today,
                        defaults={"session": session, "status": Attendance.Status.ABSENT},
                    )
                    record = Attendance.objects.select_for_update().get(pk=record.pk)
                    if record.status == Attendance.Status.PRESENT:
                        marked = False
                    else:
                        record.status = Attendance.Status.PRESENT
                        record.time = timezone.localtime().time().replace(microsecond=0)
                        record.save(update_fields=["status", "time"])
                        marked = True
            except IntegrityError:
                # A parallel camera request may have marked the same student a moment earlier.
                record = Attendance.objects.get(student=student, date=today)
                marked = record.status != Attendance.Status.PRESENT
                if marked:
                    record.status = Attendance.Status.PRESENT
                    record.time = timezone.localtime().time().replace(microsecond=0)
                    record.save(update_fields=["status", "time"])
            return JsonResponse({
                "recognized": True,
                "action": "entry",
                "attendance_marked": marked,
                "student_name": student.name,
                "roll_number": student.roll_number,
                "message": "Attendance marked successfully." if marked else "Attendance already marked today.",
                "date": timezone.localtime().date().isoformat(),
                "time": timezone.localtime().strftime("%I:%M %p"),
            })
    except FaceRecognitionError as error:
        code = 503 if error.code == "backend_unavailable" else 400 if error.code == "invalid_image" else 200
        message = "No face detected. Please position your face inside the detection frame." if error.code == "no_face" else error.message
        return JsonResponse({"recognized": False, "attendance_marked": False, "message": message}, status=code)
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError, TypeError):
        return JsonResponse({
            "recognized": False,
            "attendance_marked": False,
            "message": "The camera frame could not be read. Please capture another frame.",
        }, status=400)
    except Exception:
        logger.exception("Unexpected error while processing an attendance frame")
        return JsonResponse({
            "recognized": False,
            "attendance_marked": False,
            "message": "Face processing is temporarily unavailable. Please try again.",
        }, status=500)


def _filtered_attendance(request):
    queryset = Attendance.objects.select_related("student", "session").order_by("-date", "-time", "student__name")
    search = request.GET.get("q", "").strip()
    date_value = request.GET.get("date", "").strip()
    student_value = request.GET.get("student", "").strip()
    if search:
        queryset = queryset.filter(Q(student__name__icontains=search) | Q(student__roll_number__icontains=search))
    if date_value:
        try:
            datetime.strptime(date_value, "%Y-%m-%d")
            queryset = queryset.filter(date=date_value)
        except ValueError:
            date_value = ""
    if student_value:
        if student_value.isdigit():
            queryset = queryset.filter(student_id=int(student_value))
        else:
            student_value = ""
    return queryset, {"q": search, "date": date_value, "student": student_value}


@private_staff_view
def attendance_records(request):
    queryset, filters = _filtered_attendance(request)
    page_obj = Paginator(queryset, 15).get_page(request.GET.get("page"))
    return render(request, "attendance_records.html", {
        "page_obj": page_obj,
        "filters": filters,
        "students": Student.objects.only("id", "name", "roll_number").order_by("name"),
    })


@private_staff_view
@require_POST
def attendance_toggle_status(request, pk):
    """Manually toggle a student's attendance between Present and Absent (e.g. if a student left early)."""
    record = get_object_or_404(Attendance.objects.select_related("student"), pk=pk)
    action = request.POST.get("action", "").strip()

    if action == "mark_absent" or (not action and record.status == Attendance.Status.PRESENT):
        record.status = Attendance.Status.ABSENT
        record.time = None
        record.save(update_fields=["status", "time"])
        messages.warning(request, f"{record.student.name} marked Absent (attendance revoked / left early).")
    elif action == "mark_present" or (not action and record.status == Attendance.Status.ABSENT):
        record.status = Attendance.Status.PRESENT
        record.time = timezone.localtime().time().replace(microsecond=0)
        record.save(update_fields=["status", "time"])
        messages.success(request, f"{record.student.name} manually marked Present.")

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or ""
    if not url_has_allowed_host_and_scheme(next_url, {request.get_host()}, require_https=request.is_secure()):
        next_url = "dashboard"
    return redirect(next_url)


def _safe_csv_text(value: str) -> str:
    """Neutralize spreadsheet formulas in all user-entered CSV text fields."""
    text = str(value)
    first_non_space = text.lstrip(" \t\r\n")[:1]
    if text[:1] in {"\t", "\r", "\n"} or first_non_space in {"=", "+", "-", "@"}:
        return "'" + text
    return text


@private_staff_view
def attendance_export(request):
    queryset, _filters = _filtered_attendance(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="attendance_export.csv"'
    response["Cache-Control"] = "private, no-store"
    writer = csv.writer(response)
    writer.writerow(["Student Name", "Roll Number", "Branch", "Date", "Time", "Status"])
    for record in queryset.iterator(chunk_size=500):
        writer.writerow([
            _safe_csv_text(record.student.name),
            _safe_csv_text(record.student.roll_number),
            _safe_csv_text(record.student.branch),
            record.date.strftime("%d-%m-%Y"),
            timezone.localtime(timezone.make_aware(datetime.combine(record.date, record.time))).strftime("%I:%M %p") if record.time else "—",
            record.status,
        ])
    return response


@private_staff_view
def settings_view(request):
    form = PasswordChangeForm(request.user, request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "Your password was updated.")
        return redirect("settings")
    return render(request, "settings.html", {
        "form": form,
        "timezone_name": timezone.get_current_timezone_name(),
        "recognition_tolerance": f"{settings.FACE_RECOGNITION_TOLERANCE:.2f}",
    })


def route_manifest(request):
    """Serve the complete root-level page manifest as a JSON file."""
    path = settings.BASE_DIR / "public" / "manus-routes.json"
    if not path.is_file():
        return JsonResponse({"routes": []}, status=503)
    response = JsonResponse(json.loads(path.read_text(encoding="utf-8")))
    response["Cache-Control"] = "no-cache"
    return response
