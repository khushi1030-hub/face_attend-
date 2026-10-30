(() => {
  const csrf = () => window.getCookie?.('csrftoken') || document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || document.querySelector('meta[name="csrf-token"]')?.content || '';
  const setStatus = (element, kind, title, detail) => {
    if (!element) return;
    element.className = `recognition-status status-${kind}`;
    element.replaceChildren();
    const indicator = document.createElement('span');
    indicator.className = 'status-indicator';
    const content = document.createElement('div');
    const heading = document.createElement('strong');
    heading.textContent = title;
    const description = document.createElement('p');
    description.textContent = detail;
    content.append(heading, description);
    element.append(indicator, content);
  };
  const cameraError = (error) => {
    if (error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError') return 'Unable to access camera. Please allow camera permission and try again.';
    if (error?.name === 'NotFoundError') return 'No camera found. Connect a camera and try again.';
    if (error?.name === 'NotReadableError') return 'The camera is busy in another application. Close it and try again.';
    if (error?.message?.includes('not supported')) return error.message;
    return 'Camera unavailable. Check your browser and camera connection, then try again.';
  };
  const getCamera = async () => {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('WebRTC camera access is not supported by this browser.');
    return navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false });
  };

  const attendanceVideo = document.getElementById('attendance-video');
  const startAttendance = document.getElementById('camera-start');
  if (attendanceVideo && startAttendance) {
    const stop = document.getElementById('camera-stop');
    const placeholder = document.getElementById('attendance-placeholder');
    const state = document.getElementById('camera-state');
    const status = document.getElementById('recognition-status');
    const canvas = document.getElementById('attendance-capture');
    const count = document.getElementById('scan-count');
    let stream = null, timer = null, busy = false, scans = 0;
    const stopCamera = () => {
      if (timer) window.clearInterval(timer);
      timer = null;
      stream?.getTracks().forEach((track) => track.stop());
      stream = null; attendanceVideo.srcObject = null;
      startAttendance.classList.remove('hidden'); stop?.classList.add('hidden'); placeholder?.classList.remove('hidden');
      state?.classList.remove('active'); state?.classList.add('off'); if (state) state.innerHTML = '<i></i> CAMERA OFF';
      setStatus(status, 'idle', 'Camera paused', 'Start the camera to begin scanning.');
    };
    const scan = async () => {
      if (busy || !stream || attendanceVideo.readyState < 2) return;
      busy = true; setStatus(status, 'scanning', 'Scanning face…', 'Comparing against verified student profiles.');
      canvas.width = attendanceVideo.videoWidth || 640; canvas.height = attendanceVideo.videoHeight || 480;
      canvas.getContext('2d').drawImage(attendanceVideo, 0, 0, canvas.width, canvas.height);
      try {
        const response = await fetch('/attendance/recognize/', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf(), 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify({ image: canvas.toDataURL('image/jpeg', .82) }) });
        const payload = await response.json();
        const detail = [payload.message, payload.roll_number, payload.date, payload.time].filter(Boolean).join(' · ');
        if (payload.recognized && payload.attendance_marked) {
          scans += 1; if (count) count.textContent = scans;
          setStatus(status, 'success', `✓ ${payload.student_name}`, detail);
        } else if (payload.recognized) {
          setStatus(status, 'warning', 'Attendance already marked today.', `${payload.student_name || 'Student'} · ${payload.roll_number || ''} · ${payload.date || ''} ${payload.time || ''}`);
        } else if (payload.message?.toLowerCase().includes('no face')) setStatus(status, 'warning', 'No face detected.', 'Please position your face inside the detection frame.');
        else if (payload.message?.toLowerCase().includes('multiple')) setStatus(status, 'warning', 'Multiple faces detected.', 'Please make sure only one student is visible.');
        else setStatus(status, response.ok ? 'warning' : 'error', payload.message || 'Student not recognized.', 'Try again with one face clearly inside the guide.');
      } catch (error) { setStatus(status, 'error', 'Frame processing error', 'The server could not process this frame. Please try again.'); }
      finally { busy = false; }
    };
    startAttendance.addEventListener('click', async () => {
      try {
        stream = await getCamera(); attendanceVideo.srcObject = stream; await attendanceVideo.play(); placeholder?.classList.add('hidden'); startAttendance.classList.add('hidden'); stop?.classList.remove('hidden'); state?.classList.add('active'); state?.classList.remove('off'); if (state) state.innerHTML = '<i></i> CAMERA ACTIVE'; setStatus(status, 'scanning', 'Camera active', 'Keep one face centered in the detection frame.'); timer = window.setInterval(scan, 3000); scan();
      } catch (error) { setStatus(status, 'error', 'Unable to access camera', cameraError(error)); }
    });
    stop?.addEventListener('click', stopCamera);
    window.addEventListener('pagehide', stopCamera);
  }

  const registrationVideo = document.getElementById('registration-video');
  if (registrationVideo) {
    const start = document.querySelector('[data-action="start-registration-camera"]');
    const capture = document.querySelector('[data-action="capture-student-face"]');
    const status = document.getElementById('registration-camera-status');
    const placeholder = document.getElementById('registration-placeholder');
    const canvas = document.getElementById('registration-capture');
    const input = document.getElementById('webcam-image');
    const preview = document.getElementById('capture-preview');
    const upload = document.getElementById('id_profile_image');
    let stream = null;
    const stopRegistrationCamera = () => {
      stream?.getTracks().forEach((track) => track.stop());
      stream = null; registrationVideo.srcObject = null; placeholder?.classList.remove('hidden');
      if (capture) capture.disabled = true;
      if (start) start.textContent = 'Start camera';
      if (status) status.textContent = 'Camera not started';
    };
    start?.addEventListener('click', async () => {
      if (stream) { stopRegistrationCamera(); return; }
      try { stream = await getCamera(); registrationVideo.srcObject = stream; await registrationVideo.play(); placeholder?.classList.add('hidden'); capture.disabled = false; status.textContent = 'Camera active — ready to capture'; start.textContent = 'Stop camera'; }
      catch (error) { status.textContent = cameraError(error); }
    });
    capture?.addEventListener('click', () => {
      if (!stream) return;
      canvas.width = registrationVideo.videoWidth || 640; canvas.height = registrationVideo.videoHeight || 480; canvas.getContext('2d').drawImage(registrationVideo, 0, 0, canvas.width, canvas.height); input.value = canvas.toDataURL('image/jpeg', .9); preview?.classList.remove('hidden'); status.textContent = 'Face captured — submit to validate'; capture.disabled = true;
    });
    document.querySelector('[data-action="retake-student-photo"]')?.addEventListener('click', () => { input.value = ''; preview?.classList.add('hidden'); capture.disabled = !stream; status.textContent = stream ? 'Camera active — ready to capture' : 'Camera not started'; });
    document.querySelectorAll('[data-photo-mode]').forEach((tab) => tab.addEventListener('click', () => {
      document.querySelectorAll('[data-photo-mode]').forEach((item) => item.classList.toggle('active', item === tab));
      document.querySelectorAll('[data-photo-panel]').forEach((panel) => panel.classList.toggle('hidden', panel.dataset.photoPanel !== tab.dataset.photoMode));
      if (tab.dataset.photoMode === 'camera') { if (upload) upload.value = ''; }
      else { input.value = ''; preview?.classList.add('hidden'); if (stream) stopRegistrationCamera(); }
    }));
    window.addEventListener('pagehide', stopRegistrationCamera);
  }
})();
