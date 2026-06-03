# ✋ Gesture PowerPoint Controller

A real-time, webcam-based hand gesture controller for PowerPoint presentations — built with Python, MediaPipe, and PyQt6. Navigate slides, start and exit presentations, and toggle control entirely hands-free.

---

## 📸 Preview

The application opens a live camera feed with hand landmark overlays. Detected gestures are displayed in an on-screen action banner and logged with timestamps in the activity panel.

<table>
  <tr>
    <td><img src="Img/Screenshot 2026-06-02 233841.png" width="400"></td>
    <td><img src="Img/Screenshot 2026-06-02 233905.png" width="400"></td>
  </tr>
</table>

---
# Download the EXE file from here

<a href="https://drive.google.com/file/d/1uffsTdqVwEEUQYVL8o7QIuogMmcoIq2A/view?usp=sharing">
    <img src="https://img.shields.io/badge/Download-Project-blue?style=for-the-badge" alt="Download Project">
</a>

---
## 🚀 Features

- **Real-time hand tracking** using MediaPipe Hands
- **Chirality-aware thumb detection** — works correctly for both left and right hands
- **Gesture stabilisation** — a gesture must be held for a set number of frames before firing, preventing accidental triggers
- **Cooldown system** — prevents rapid re-triggering of the same action
- **Toggle on/off** — full palm gesture enables or disables slide control without closing the app
- **Live activity log** with timestamps
- **Gesture reference panel** built into the UI
- **Dark, professional PyQt6 UI** with status badges and stat cards

---

## 🖐 Gesture Map

| Fingers | Gesture | Action |
|---------|---------|--------|
| ☝ 1 | Index finger | Next Slide → |
| ✌ 2 | Two fingers | ← Previous Slide |
| 🤟 3 | Three fingers | Start Presentation (F5) |
| 🖖 4 | Four fingers | Exit Presentation (ESC) |
| 🖐 5 | Open palm | Toggle Control ON / OFF |

> **Note:** Hold each gesture steady for ~8 frames before it fires. This prevents accidental triggers from transitional hand positions.

---

## 🛠 Requirements

### Python Version

```
Python 3.10
```

### Dependencies

| Library | Version | Purpose |
|---------|---------|---------|
| `mediapipe` | 0.10.9 | Hand landmark detection and tracking |
| `opencv-python` | ≥ 4.8.0 | Camera capture and frame processing |
| `PyQt6` | ≥ 6.5.0 | GUI framework (window, widgets, threading) |
| `numpy` | ≥ 1.24.0 | Frame array manipulation |
| `keyboard` | ≥ 0.13.5 | Sending keystrokes to the OS |

---

## 📦 Installation

### 1. Clone or download the project

```bash
git clone https://github.com/your-username/gesture-ppt-controller.git
cd gesture-ppt-controller
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install mediapipe==0.10.9 opencv-python PyQt6 numpy keyboard
```

Or using the provided requirements file:

```bash
pip install -r requirements.txt
```

#### `requirements.txt`

```
mediapipe==0.10.9
opencv-python>=4.8.0
PyQt6>=6.5.0
numpy>=1.24.0
keyboard>=0.13.5
```

---

## ▶ Running the App

> ⚠ **The `keyboard` module requires administrator / root privileges to send keystrokes.**

### Windows

Run your terminal as **Administrator**, then:

```bash
python gesture_controller.py
```

### macOS / Linux

```bash
sudo python gesture_controller.py
```

> If you run without elevated privileges, the camera feed and gesture detection will still work, but no keystrokes will be sent to PowerPoint. A warning will appear in the activity log.

---

## 🖥 How to Use

1. **Open your PowerPoint presentation** before or after launching the app.
2. Click **▶ Start Camera** in the app.
3. Show an **open palm (5 fingers)** to the camera to **enable gesture control**. The status badge will turn green and show `● CONTROL ON`.
4. Use the gestures from the table above to control your slides.
5. Show an **open palm** again at any time to **disable control** without closing the app.
6. Click **■ Stop Camera** or close the window to exit.

---

## ⚙ Configuration

The following constants at the top of `gesture_controller.py` can be tuned to your preference:

| Constant | Default | Description |
|----------|---------|-------------|
| `STABLE_NEEDED` | `8` | Frames a gesture must be held before firing |
| `COOLDOWN_ACTION` | `1.8` s | Minimum time between slide actions |
| `COOLDOWN_TOGGLE` | `2.0` s | Minimum time between enable/disable toggles |
| `min_detection_confidence` | `0.85` | MediaPipe detection sensitivity |
| `min_tracking_confidence` | `0.85` | MediaPipe tracking sensitivity |

Lowering `STABLE_NEEDED` makes gestures trigger faster but increases accidental activations. Raise the confidence values if you get false detections in bright or cluttered backgrounds.

---

## 🔍 Troubleshooting

| Problem | Solution |
|---------|----------|
| `❌ Cannot open camera` | Check that no other app is using the webcam. Try changing `cv2.VideoCapture(0)` to `(1)` or `(2)`. |
| Keystrokes not working | Run the terminal / script as Administrator (Windows) or with `sudo` (macOS/Linux). |
| `keyboard` module not found | Install it: `pip install keyboard` |
| Gestures trigger too easily | Increase `STABLE_NEEDED` (e.g. to `12`) in the constants section. |
| Hand not detected | Ensure good lighting. Keep your hand within 40–70 cm of the camera. |
| Laggy camera feed | Lower the camera resolution via `cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)`. |
| PyQt6 import error | Ensure you installed `PyQt6`, not `PyQt5`: `pip install PyQt6` |

---

## 📁 Project Structure

```
gesture-ppt-controller/
│
├── gesture_controller.py   # Main application file
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

---

## 🧠 How It Works

1. **Camera thread** (`CameraThread`) runs independently from the UI thread to avoid blocking.
2. Each frame is flipped horizontally and passed to **MediaPipe Hands**, which returns 21 3D landmarks per detected hand.
3. **Finger counting** checks whether each fingertip landmark is above its corresponding PIP (proximal interphalangeal) joint. The thumb uses the X-axis instead of Y, and is corrected for hand chirality (left vs right).
4. A **stability accumulator** increments each frame the same finger count is seen. Once it reaches `STABLE_NEEDED`, the gesture fires — then the counter resets to prevent re-firing.
5. Fired gestures call `keyboard.send()` with the appropriate key, which is picked up by whichever window is in focus (e.g. PowerPoint).
6. The UI updates via **Qt signals/slots** emitted from the camera thread — frame, finger count, action name, and log messages are all signal-driven.

---

## 📄 License

Licensed by Abdullah Zahid  — free to use, modify, and distribute.

---

## 🙌 Acknowledgements

- [MediaPipe](https://developers.google.com/mediapipe) by Google for the hand landmark model
- [OpenCV](https://opencv.org/) for camera and image processing
- [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) for the desktop GUI framework
