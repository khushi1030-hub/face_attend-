# Campus AI Attendance

A Django web application for managing a college student roster and marking attendance with real webcam-based face recognition. An administrator registers a student using one clear face image. The server validates the image, generates a `face_recognition` encoding, stores it privately with the student profile, and compares later webcam frames with registered encodings. Attendance is stored in SQLite during development, with database constraints preventing duplicate records for a student on the same day.

## Features

- Django administrator login/logout with protected pages and CSRF-protected forms.
- Student registration and management: details, unique roll number, validated profile image, actual webcam capture, face encoding, edit, delete and profile/history pages.
- A real browser webcam using WebRTC. Frames are sent to Django for OpenCV face detection and `face_recognition` matching. The application never invents a recognition result.
- Opened-session attendance. Opening **Mark attendance** creates one session for the local date and initializes enrolled students as **Absent**. A verified face match updates that student to **Present**. A repeat match is reported as already marked.
- Database-backed dashboard statistics, session trend charts, present/absent chart and recent records.
- Attendance record search, date and student filters, pagination and CSV export.
- Private staff-only profile-photo delivery; face encodings are not sent to the browser.
- Responsive, dark-blue glassmorphism dashboard and clear toast/error states.

## Technology stack

| Technology | Purpose |
| --- | --- |
| Python 3.11 or 3.12 | Application language |
| Django 5.2 | Authentication, forms, server-rendered pages, ORM, migrations and security protections |
| SQLite | Simple local development database |
| OpenCV | Image decoding and face-location detection |
| `face_recognition` / dlib | 128-value face embeddings and conservative distance comparison |
| Pillow | Image validation and format checks |
| HTML, CSS and JavaScript | Responsive interface and camera access through WebRTC |

The Django models are conventional and can be migrated to MySQL later. A MySQL production configuration and durable production image storage are not included in the local development setup.

## Installation

### Ubuntu / Linux

The `dlib` package includes native code. Install its compiler/build prerequisites first:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake python3-dev libopenblas-dev liblapack-dev
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
cp .env.example .env
```

### Windows

Use 64-bit Python 3.11 or 3.12. `dlib` may need the Microsoft C++ build tools and CMake; WSL with Ubuntu is often the simpler route if its wheel cannot be built natively.

```powershell
py -3.12 -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
copy .env.example .env
```

## Environment configuration

Edit `.env` (never commit it; it is in `.gitignore`). Generate a Django key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Paste the output into `DJANGO_SECRET_KEY` in `.env`. Keep `DJANGO_DEBUG=True` only in development. Set `DJANGO_ALLOWED_HOSTS` to the hostnames used by your environment. For the secure embedded Preview, set `DJANGO_SECURE_COOKIES=True` and add the HTTPS Preview origin to `DJANGO_CSRF_TRUSTED_ORIGINS`; the browser-facing camera API requires HTTPS (except on localhost). `DJANGO_TIME_ZONE` defaults to `Asia/Kolkata` and can be changed to the college's local timezone. `FACE_RECOGNITION_TOLERANCE` defaults to `0.48`; do not raise it casually, because a more permissive threshold can increase false matches. `MAX_UPLOAD_SIZE_MB` defaults to 6.

No administrator account or password is included. Create one locally with `createsuperuser`.

## Database setup and migrations

```bash
python manage.py makemigrations attendance
python manage.py migrate
```

The first command creates migration files when models change; the second applies them. Do not delete migration files or the SQLite database to solve a migration error. Back up the database and inspect migration state before making recovery changes.

## Create an administrator and run the project

```bash
python manage.py createsuperuser
python manage.py runserver
```

Open the printed local address, normally `http://127.0.0.1:8000/`. For the managed Webdev Preview configured on port 3000, run:

```bash
python manage.py runserver 0.0.0.0:3000
```

Sign in at `/login/`. Only active Django staff accounts can access the dashboard. The Django admin is also available at `/admin/`.

## Register students

1. Sign in as an administrator and choose **Register student**.
2. Enter the student's name, roll number, branch/course, semester (1–12) and email.
3. Upload one JPEG/PNG/WebP image or switch to **Use webcam**, start the real camera and capture one face. The two sources cannot be submitted together.
4. Submit. The server validates the image, checks that exactly one face is visible, generates its real face encoding and stores the image and encoding. No face, multiple faces, invalid uploads and duplicate roll numbers are rejected with a useful message.
5. Open the student profile to confirm the saved details and attendance history.

A profile image must be at least 64 × 64 pixels and no larger than the configured upload limit. A newly enrolled student is added as Absent if today's attendance session has already been opened.

## Mark attendance

1. Open **Mark attendance**. This opens one class session for the local date and creates an Absent row for every enrolled student.
2. Start the camera and allow browser permission. Place one student's face inside the guide.
3. The browser captures a JPEG every three seconds and posts it with a CSRF token. Django decodes the frame, uses OpenCV's frontal-face detector, computes a `face_recognition` embedding, and compares it with registered embeddings using a conservative distance threshold.
4. A recognized student becomes Present and receives the server-local scan time. Further scans for the same student return **Attendance already marked today.** Unknown, no-face and multiple-face frames do not change attendance.
5. Stop the camera when finished. Live camera use requires an HTTPS page or localhost and browser camera permission.

Only the enrollment/profile image is retained for the student. Attendance frames sent to the recognition endpoint are processed in memory and are not saved as profile photos.

## How face recognition works

```text
Webcam image
    ↓
OpenCV decodes the frame and detects the face region(s)
    ↓
Reject zero or multiple faces
    ↓
face_recognition / dlib creates a 128-value face encoding
    ↓
Compare with securely stored student encodings using face distance
    ↓
If the closest match is within the conservative tolerance, identify the student
    ↓
Update today's unique attendance row from Absent to Present
```

The system is a practical college-project face matcher, not liveness detection. It cannot prove that a person is physically present rather than showing a photograph to the camera. Use supervised check-in and follow your institution's policies for biometric consent, retention and access.

## Common errors

| Error | Suggested fix |
| --- | --- |
| `No module named cv2` | Activate the virtual environment and run `pip install -r requirements.txt`; this project uses `opencv-python-headless`. |
| `No module named face_recognition` | Activate the project environment and install requirements. If installation failed at `dlib`, install CMake, a C/C++ compiler and Python development headers that match your Python version, then retry. |
| `Python.h: No such file or directory` | On Ubuntu, install the matching development package, such as `python3.12-dev` for Python 3.12, and retry the package install. |
| Camera permission denied | Allow camera access in the browser's site settings, reload the HTTPS page and press **Start camera** again. |
| No camera / camera unavailable | Connect a webcam, close other applications using it, ensure the page is HTTPS (or localhost), and retry. |
| No face detected | Face the camera, improve lighting, move closer, remove obstructions and capture one sharp image. |
| Multiple faces detected | Ensure only the student being registered or checked in is visible. |
| Student not recognized | Confirm the student was enrolled with a clear front-facing photo; improve lighting and avoid extreme angles. Re-enroll with a clearer photo if appropriate. |
| Migration error | Keep existing migration files and `db.sqlite3`; inspect `python manage.py showmigrations` and `python manage.py check` before changing schema state. Back up data first. |
| Duplicate roll number | Roll numbers are unique case-insensitively. Search the Students page, then edit the existing record or choose the correct unique number. |
| Duplicate attendance | The database enforces one row per student/date. A repeated Present scan is reported as already marked rather than inserted again. |
| Windows `dlib` build failure | Install CMake and Visual Studio C++ build tools with the Windows SDK. If the matching Python wheel is unavailable, use WSL/Ubuntu with its compiler and `python3-dev` package. |

## Project structure

```text
faceattend/
├── manage.py
├── requirements.txt
├── README.md
├── .env.example
├── .gitignore
├── ideas.md
├── public/manus-routes.json
├── attendance_system/       # Django settings, root routes, ASGI and WSGI
├── attendance/              # Models, forms, views, face utilities, admin, tests, migrations
├── templates/               # Login, dashboard, student and attendance pages
├── static/css/style.css     # Responsive dark-blue dashboard styles
├── static/js/               # WebRTC camera, chart and shared interactions
├── static/images/           # Project logo and fallback avatar
└── media/students/          # Local development profile-photo uploads
```

`.env`, `db.sqlite3`, uploaded media and virtual environments are local-only and ignored by Git.

## Teacher/judge demonstration

1. Run migrations and create an administrator; sign in.
2. Open **Register student**, enter student details, and capture/upload a clear single-face image.
3. Open **Mark attendance** to create today's session, then start the webcam.
4. Have the enrolled student face the camera; show the recognized name/roll and Present result.
5. Scan the same student again; show **Attendance already marked today.** and the single database row.
6. Try an unknown face, no face, or multiple faces and show that none creates a Present record.
7. Open **Attendance records**, filter by student/date, and export the filtered CSV.
8. Return to the Dashboard to show database-derived totals, present/absent counts, trend charts and recent records.
9. Open the student detail page to show attendance percentage and history.

## Testing and development checks

```bash
python manage.py check
python manage.py test attendance
```

The test suite covers authentication, protected pages, registration/image validation, database uniqueness, session initialization, idempotent attendance, unknown/no-face/multiple-face outcomes, database-derived stats, filters, pagination and CSV export. Automated tests do not have access to a physical camera; use an HTTPS browser session with a camera to verify live capture in your environment.
