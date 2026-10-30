"""Small, explicit face-recognition helpers used by registration and attendance views."""
import base64
import binascii
import json
import logging
from dataclasses import dataclass
from typing import BinaryIO

import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    import cv2
except ImportError:  # Keep the rest of Django usable and show a helpful camera error.
    cv2 = None

try:
    import face_recognition
except (ImportError, SystemExit) as error:
    logger.warning("face_recognition backend is unavailable: %s", error)
    face_recognition = None


@dataclass
class FaceRecognitionError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


def decode_data_url(value: str, max_bytes: int | None = None) -> bytes:
    """Decode a browser image data URL, rejecting malformed or oversized payloads."""
    if not isinstance(value, str) or "," not in value:
        raise FaceRecognitionError("invalid_image", "The captured frame is invalid. Please capture again.")
    header, encoded = value.split(",", 1)
    if header.lower() not in {"data:image/jpeg;base64", "data:image/png;base64", "data:image/webp;base64"}:
        raise FaceRecognitionError("invalid_image", "The captured frame must be a JPEG, PNG or WebP image.")
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise FaceRecognitionError("invalid_image", "The captured frame is invalid. Please capture again.")
    limit = max_bytes or settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if not image_bytes or len(image_bytes) > limit:
        raise FaceRecognitionError("invalid_image", "The image is empty or exceeds the upload size limit.")
    return image_bytes


def _image_array(image: bytes | BinaryIO | np.ndarray) -> np.ndarray:
    if cv2 is None:
        raise FaceRecognitionError("backend_unavailable", "OpenCV is not installed on the server.")
    if isinstance(image, np.ndarray):
        array = image
    else:
        if isinstance(image, bytes):
            raw = image
        else:
            try:
                image.seek(0)
                raw = image.read()
                image.seek(0)
            except (AttributeError, OSError):
                raise FaceRecognitionError("invalid_image", "The image could not be read.")
        if not raw:
            raise FaceRecognitionError("invalid_image", "The image is empty.")
        buffer = np.frombuffer(raw, dtype=np.uint8)
        array = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if array is None or array.ndim != 3 or array.shape[2] != 3:
        raise FaceRecognitionError("invalid_image", "The image is invalid or uses an unsupported format.")
    height, width = array.shape[:2]
    if width < 64 or height < 64 or width > 6000 or height > 6000:
        raise FaceRecognitionError("invalid_image", "The image dimensions are outside the supported range.")
    return cv2.cvtColor(array, cv2.COLOR_BGR2RGB)


def detect_face(image: bytes | BinaryIO | np.ndarray) -> list[tuple[int, int, int, int]]:
    """Return OpenCV face boxes in face_recognition order: (top, right, bottom, left)."""
    if cv2 is None:
        raise FaceRecognitionError("backend_unavailable", "OpenCV is not installed on the server.")
    rgb = _image_array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.equalizeHist(gray)
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    if detector.empty():
        logger.error("OpenCV Haar cascade could not be loaded from %s", cascade_path)
        raise FaceRecognitionError("backend_unavailable", "Face detection is temporarily unavailable.")
    # Ignore small background patterns that Haar cascades sometimes misclassify as faces.
    boxes = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(100, 100))
    return [(int(y), int(x + width), int(y + height), int(x)) for x, y, width, height in boxes]


def generate_face_encoding(image: bytes | BinaryIO | np.ndarray) -> np.ndarray:
    """Validate exactly one OpenCV face, then generate a real 128-value dlib encoding."""
    face_boxes = detect_face(image)
    if len(face_boxes) == 0:
        raise FaceRecognitionError(
            "no_face", "No face detected. Please position your face clearly in front of the camera."
        )
    if len(face_boxes) > 1:
        raise FaceRecognitionError(
            "multiple_faces", "Multiple faces detected. Please make sure only one student is visible."
        )
    if face_recognition is None:
        raise FaceRecognitionError("backend_unavailable", "The face-recognition library is not installed on the server.")
    rgb = _image_array(image)
    encodings = face_recognition.face_encodings(rgb, known_face_locations=face_boxes, num_jitters=1)
    if not encodings:
        raise FaceRecognitionError("no_face", "No clear face detected. Please position your face clearly and try again.")
    return np.asarray(encodings[0], dtype=np.float64)


def compare_faces(known_encodings: list[list[float]], candidate: np.ndarray, tolerance: float | None = None) -> tuple[int | None, float | None]:
    """Return the nearest encoding index only when it is within a conservative distance."""
    if not known_encodings:
        return None, None
    limit = settings.FACE_RECOGNITION_TOLERANCE if tolerance is None else tolerance
    if not 0.30 <= limit <= 0.60:
        logger.warning("Recognition tolerance %.2f is outside the safe range; using 0.48", limit)
        limit = 0.48
    if face_recognition is not None:
        distances = face_recognition.face_distance(np.asarray(known_encodings, dtype=np.float64), candidate)
    else:
        distances = np.linalg.norm(np.asarray(known_encodings, dtype=np.float64) - candidate, axis=1)
    if not len(distances):
        return None, None
    best_index = int(np.argmin(distances))
    best_distance = float(distances[best_index])
    if best_distance <= limit:
        return best_index, best_distance
    return None, best_distance


def recognize_face(image: bytes | BinaryIO | np.ndarray, students) -> tuple[object | None, float | None]:
    """Encode one face and compare it against each registered student's stored encoding."""
    candidate = generate_face_encoding(image)
    known_encodings: list[list[float]] = []
    known_students = []
    for student in students:
        try:
            values = json.loads(student.face_encoding)
            vector = np.asarray(values, dtype=np.float64)
            if vector.shape != (128,) or not np.isfinite(vector).all():
                continue
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("Skipping invalid stored face vector for student id=%s", student.pk)
            continue
        known_encodings.append(vector.tolist())
        known_students.append(student)
    index, distance = compare_faces(known_encodings, candidate)
    if index is None:
        return None, distance
    return known_students[index], distance
