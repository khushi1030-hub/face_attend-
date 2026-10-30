"""Forms keep user-entered student data validated before it reaches the database."""
from PIL import Image, UnidentifiedImageError
from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import Student


class StudentForm(forms.ModelForm):
    # Webcam frames arrive through the normal CSRF-protected form as a data URL.
    webcam_image = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "webcam-image", "autocomplete": "off"}),
    )

    class Meta:
        model = Student
        fields = ("name", "roll_number", "branch", "semester", "email", "profile_image")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "e.g. Aisha Mehta", "autocomplete": "name"}),
            "roll_number": forms.TextInput(attrs={"placeholder": "e.g. 23CSE101", "autocomplete": "off"}),
            "branch": forms.TextInput(attrs={"placeholder": "e.g. Computer Science"}),
            "semester": forms.NumberInput(attrs={"min": 1, "max": 12, "placeholder": "1–12"}),
            "email": forms.EmailInput(attrs={"placeholder": "student@college.edu", "autocomplete": "email"}),
            "profile_image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        }

    def clean_name(self):
        value = self.cleaned_data["name"].strip()
        if len(value) < 2:
            raise ValidationError("Enter the student's full name.")
        return value

    def clean_roll_number(self):
        value = self.cleaned_data["roll_number"].strip().upper()
        if not value:
            raise ValidationError("Roll number is required.")
        duplicate = Student.objects.filter(roll_number__iexact=value)
        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise ValidationError("A student with this roll number is already registered.")
        return value

    def clean_branch(self):
        value = self.cleaned_data["branch"].strip()
        if not value:
            raise ValidationError("Enter the student's branch or course.")
        return value

    def clean_semester(self):
        value = self.cleaned_data["semester"]
        if value < 1 or value > 12:
            raise ValidationError("Semester must be between 1 and 12.")
        return value

    def clean_profile_image(self):
        image = self.cleaned_data.get("profile_image")
        if not image:
            return image
        if image.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise ValidationError(f"Choose an image smaller than {settings.MAX_UPLOAD_SIZE_MB} MB.")
        try:
            image.seek(0)
            with Image.open(image) as opened:
                image_format = (opened.format or "").upper()
                width, height = opened.size
                opened.verify()
            image.seek(0)
        except (UnidentifiedImageError, OSError, ValueError):
            raise ValidationError("The uploaded file is not a valid image.")
        if image_format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("Upload a JPEG, PNG or WebP image.")
        if width < 64 or height < 64 or width > 6000 or height > 6000:
            raise ValidationError("Image dimensions must be between 64 and 6000 pixels on each side.")
        return image

    def clean_webcam_image(self):
        value = self.cleaned_data.get("webcam_image", "").strip()
        if value and len(value) > 6 * 1024 * 1024:
            raise ValidationError("The webcam image is too large. Please capture again.")
        return value

    def clean(self):
        cleaned = super().clean()
        uploaded = cleaned.get("profile_image")
        webcam = cleaned.get("webcam_image")
        if uploaded and webcam:
            self.add_error("webcam_image", "Use either the uploaded photo or webcam capture, not both.")
        elif not uploaded and not webcam and not self.instance.pk:
            self.add_error("profile_image", "Upload a profile photo or capture the student's face with the webcam.")
        return cleaned
