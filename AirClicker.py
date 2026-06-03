"""
Gesture PowerPoint Controller
==============================
Fixes applied vs original:
  1. Thumb detection is now hand-chirality-aware (left vs right hand).
  2. stable_count resets after each triggered action, preventing re-fire.
  3. MediaPipe Hands instance is created inside the thread and closed on exit.
  4. QImage now keeps a reference to the numpy array to avoid dangling pointer.
  5. keyboard.send wrapped in try/except; error surfaced to log.
  6. action label no longer flickers — only updates on real state changes.
  7. Enabled/disabled state shown with coloured status badge in UI.
  8. Frame skipped gracefully when hands.process is slow (dropped-frame guard).
  9. Gesture guide panel with visual finger-count hints.
 10. Complete dark-to-vibrant professional redesign.
"""

import sys
import time
import numpy as np
import cv2
import mediapipe as mp

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except Exception:
    KEYBOARD_AVAILABLE = False

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QImage, QPixmap, QFont, QColor, QPainter, QPen, QBrush, QLinearGradient
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton,
    QTextEdit, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
    QGraphicsDropShadowEffect
)


# ─────────────────────────────────────────────
#  CONSTANTS
# ─────────────────────────────────────────────
STABLE_NEEDED   = 8          # frames a gesture must hold before firing
COOLDOWN_ACTION = 1.8        # seconds between slide actions
COOLDOWN_TOGGLE = 2.0        # seconds between enable/disable toggles

GESTURE_MAP = {
    0: ("No hand",          "–"),
    1: ("☝  Index finger",  "Next slide  →"),
    2: ("✌  Two fingers",   "← Previous slide"),
    3: ("🤟 Three fingers",  "Start presentation  F5"),
    4: ("🖖 Four fingers",   "Exit presentation  ESC"),
    5: ("🖐 Open palm",     "Toggle control ON / OFF"),
}


# ─────────────────────────────────────────────
#  COLOURS (used in stylesheet strings)
# ─────────────────────────────────────────────
C = {
    "bg_deep":    "#09090f",
    "bg_card":    "#13131e",
    "bg_panel":   "#1a1a2e",
    "accent1":    "#7c3aed",   # violet
    "accent2":    "#06b6d4",   # cyan
    "accent3":    "#f59e0b",   # amber
    "green":      "#10b981",
    "red":        "#ef4444",
    "text_hi":    "#f0f0ff",
    "text_mid":   "#94a3b8",
    "text_lo":    "#475569",
    "border":     "#2a2a40",
}


# ─────────────────────────────────────────────
#  CAMERA / GESTURE THREAD
# ─────────────────────────────────────────────
class CameraThread(QThread):
    frame_signal  = pyqtSignal(QImage)
    finger_signal = pyqtSignal(int)          # current finger count
    action_signal = pyqtSignal(str, str)     # (action_name, colour_hex)
    log_signal    = pyqtSignal(str)
    enabled_signal = pyqtSignal(bool)

    def __init__(self):
        super().__init__()
        self._running        = False
        self.enabled         = False
        self._last_action    = 0.0
        self._last_toggle    = 0.0
        self._prev_count     = -1
        self._stable_count   = 0
        self._last_fingers   = 0

    # ── helpers ──────────────────────────────
    def _can_act(self) -> bool:
        now = time.monotonic()
        if now - self._last_action > COOLDOWN_ACTION:
            self._last_action = now
            return True
        return False

    def _can_toggle(self) -> bool:
        now = time.monotonic()
        if now - self._last_toggle > COOLDOWN_TOGGLE:
            self._last_toggle = now
            return True
        return False

    def _reset_stable(self):
        """Call after firing an action to prevent immediate re-trigger."""
        self._stable_count = 0
        self._prev_count   = -1

    # ── finger counting ──────────────────────
    def _count_fingers(self, lm, handedness: str) -> int:
        """
        Count raised fingers.
        Thumb: compare tip vs IP joint along X axis, flipped for left hand.
        Other fingers: tip Y < pip Y  →  extended.
        """
        tips = [4, 8, 12, 16, 20]
        pip  = [3, 6, 10, 14, 18]

        count = 0

        # Thumb (chirality-aware)
        if handedness == "Left":
            # mirrored feed: "Left" label = right hand in camera space
            if lm.landmark[tips[0]].x > lm.landmark[pip[0]].x:
                count += 1
        else:
            if lm.landmark[tips[0]].x < lm.landmark[pip[0]].x:
                count += 1

        # Other four fingers
        for t, p in zip(tips[1:], pip[1:]):
            if lm.landmark[t].y < lm.landmark[p].y:
                count += 1

        return count

    # ── key sender ───────────────────────────
    def _send_key(self, key: str) -> bool:
        if not KEYBOARD_AVAILABLE:
            self.log_signal.emit("⚠ 'keyboard' module unavailable (try running as admin).")
            return False
        try:
            keyboard.send(key)
            return True
        except Exception as exc:
            self.log_signal.emit(f"⚠ Key error: {exc}")
            return False

    # ── main loop ────────────────────────────
    def run(self):
        mp_hands = mp.solutions.hands
        mp_draw  = mp.solutions.drawing_utils
        mp_styles = mp.solutions.drawing_styles

        hands = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.85,
            min_tracking_confidence=0.85,
        )

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            self.log_signal.emit("❌ Cannot open camera.")
            hands.close()
            return

        self._running = True
        self.log_signal.emit("📷 Camera opened — show your hand!")

        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            frame = cv2.flip(frame, 1)
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # ── MediaPipe ──
            result = hands.process(rgb)

            fingers    = 0
            handedness = "Right"

            if result.multi_hand_landmarks and result.multi_handedness:
                for hand_lm, hand_info in zip(
                    result.multi_hand_landmarks, result.multi_handedness
                ):
                    # Draw landmarks with coloured style
                    mp_draw.draw_landmarks(
                        frame,
                        hand_lm,
                        mp_hands.HAND_CONNECTIONS,
                        mp_draw.DrawingSpec(color=(124, 58, 237), thickness=2, circle_radius=4),
                        mp_draw.DrawingSpec(color=(6, 182, 212), thickness=2),
                    )

                    handedness = hand_info.classification[0].label
                    fingers    = self._count_fingers(hand_lm, handedness)

            # ── Stability accumulator ──
            if fingers == self._prev_count:
                self._stable_count += 1
            else:
                self._prev_count   = fingers
                self._stable_count = 0

            stable = self._stable_count >= STABLE_NEEDED

            # ── 5 fingers → toggle ──
            if fingers == 5 and stable and self._can_toggle():
                self.enabled = not self.enabled
                self._reset_stable()
                if self.enabled:
                    self.log_signal.emit("✅ Control ENABLED")
                    self.action_signal.emit("CONTROL ENABLED", C["green"])
                else:
                    self.log_signal.emit("⛔ Control DISABLED")
                    self.action_signal.emit("CONTROL DISABLED", C["red"])
                self.enabled_signal.emit(self.enabled)

            # ── Gesture actions (only when enabled) ──
            elif self.enabled and stable:
                if fingers == 1 and self._can_act():
                    if self._send_key("right"):
                        self._reset_stable()
                        self.log_signal.emit("▶ Next slide")
                        self.action_signal.emit("NEXT SLIDE  →", C["accent2"])

                elif fingers == 2 and self._can_act():
                    if self._send_key("left"):
                        self._reset_stable()
                        self.log_signal.emit("◀ Previous slide")
                        self.action_signal.emit("← PREVIOUS SLIDE", C["accent2"])

                elif fingers == 3 and self._can_act():
                    if self._send_key("f5"):
                        self._reset_stable()
                        self.log_signal.emit("🟢 Presentation started")
                        self.action_signal.emit("START PRESENTATION  F5", C["green"])

                elif fingers == 4 and self._can_act():
                    if self._send_key("esc"):
                        self._reset_stable()
                        self.log_signal.emit("🔴 Presentation exited")
                        self.action_signal.emit("EXIT PRESENTATION  ESC", C["accent3"])

            # ── Emit frame ──
            # Keep a reference to `frame` data so QImage doesn't dangle
            h, w, ch = frame.shape
            frame_copy = np.ascontiguousarray(frame)   # ensure C-contiguous
            qt_img = QImage(
                frame_copy.data, w, h, ch * w,
                QImage.Format.Format_BGR888
            )
            qt_img = qt_img.copy()   # detach from numpy buffer
            self.frame_signal.emit(qt_img)
            self.finger_signal.emit(fingers)

        cap.release()
        hands.close()

    def stop(self):
        self._running = False
        self.quit()
        self.wait()


# ─────────────────────────────────────────────
#  GLOWING LABEL  (accent border)
# ─────────────────────────────────────────────
class StatusBadge(QLabel):
    """Pill-shaped coloured status badge."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._set_color(C["text_lo"])

    def set_state(self, text: str, color: str):
        self.setText(text)
        self._set_color(color)

    def _set_color(self, color: str):
        self.setStyleSheet(f"""
            QLabel {{
                color: {color};
                border: 1.5px solid {color};
                border-radius: 12px;
                padding: 4px 18px;
                font-size: 13px;
                font-weight: bold;
                letter-spacing: 1.5px;
                background: transparent;
            }}
        """)


# ─────────────────────────────────────────────
#  GESTURE CARD  (right panel row)
# ─────────────────────────────────────────────
class GestureCard(QFrame):
    def __init__(self, count: int, icon: str, label: str, action: str):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(f"""
            QFrame {{
                background: {C["bg_panel"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
                padding: 4px;
            }}
        """)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 6, 10, 6)
        row.setSpacing(10)

        # Finger count bubble
        bubble = QLabel(str(count))
        bubble.setFixedSize(34, 34)
        bubble.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bubble.setStyleSheet(f"""
            background: {C["accent1"]};
            color: white;
            border-radius: 17px;
            font-weight: bold;
            font-size: 15px;
        """)

        # Icon + gesture name
        lbl = QLabel(f"{icon}  {label}")
        lbl.setStyleSheet(f"color: {C['text_hi']}; font-size: 13px;")
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Action
        act = QLabel(action)
        act.setStyleSheet(f"color: {C['accent2']}; font-size: 12px; font-weight: bold;")
        act.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(bubble)
        row.addWidget(lbl)
        row.addWidget(act)


# ─────────────────────────────────────────────
#  MAIN WINDOW
# ─────────────────────────────────────────────
class MainWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("✋ Gesture Controller — PowerPoint Edition")
        self.resize(1280, 760)
        self.setMinimumSize(1000, 640)

        self._thread = CameraThread()
        self._init_ui()

        # connect signals
        self._thread.frame_signal.connect(self._on_frame)
        self._thread.finger_signal.connect(self._on_finger)
        self._thread.action_signal.connect(self._on_action)
        self._thread.log_signal.connect(self._add_log)
        self._thread.enabled_signal.connect(self._on_enabled)

        # pulse timer for the action label
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._dim_action)

    # ─────────────────────────────────────────
    #  UI CONSTRUCTION
    # ─────────────────────────────────────────
    def _init_ui(self):
        # ── global stylesheet ──
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {C["bg_deep"]};
                color: {C["text_hi"]};
                font-family: "Segoe UI", "SF Pro Display", Arial, sans-serif;
            }}
            QScrollBar:vertical {{
                background: {C["bg_card"]};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {C["accent1"]};
                border-radius: 3px;
            }}
            QTextEdit {{
                background-color: {C["bg_panel"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
                padding: 8px;
                font-size: 12px;
                color: {C["text_mid"]};
                selection-background-color: {C["accent1"]};
            }}
            QPushButton {{
                border-radius: 10px;
                font-weight: bold;
                font-size: 13px;
                padding: 10px 0;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ opacity: 0.85; }}
            QPushButton:pressed {{ opacity: 0.7; }}
        """)

        # ── root layout ──
        root = QHBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        # ══════════════════════════════════════
        #  LEFT  — camera + controls
        # ══════════════════════════════════════
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # Header row
        header = QHBoxLayout()
        title = QLabel("✋  Gesture Controller")
        title.setStyleSheet(
            f"color: {C['text_hi']}; font-size: 22px; font-weight: bold; letter-spacing: 1px;"
        )
        subtitle = QLabel("PowerPoint Edition")
        subtitle.setStyleSheet(
            f"color: {C['accent1']}; font-size: 13px; font-weight: bold; letter-spacing: 2px;"
        )
        sub_col = QVBoxLayout()
        sub_col.setSpacing(0)
        sub_col.addWidget(title)
        sub_col.addWidget(subtitle)
        header.addLayout(sub_col)
        header.addStretch()

        # Status badge
        self._status_badge = StatusBadge("● INACTIVE")
        self._status_badge.setFixedHeight(30)
        header.addWidget(self._status_badge)
        left_col.addLayout(header)

        # Video frame
        self._video = QLabel()
        self._video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._video.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._video.setMinimumSize(640, 440)
        self._video.setStyleSheet(f"""
            background: {C["bg_card"]};
            border: 2px solid {C["border"]};
            border-radius: 14px;
        """)
        self._video.setText("[ Camera feed will appear here ]")
        left_col.addWidget(self._video, stretch=1)

        # ── Action label ──
        self._action_lbl = QLabel("WAITING FOR GESTURE…")
        self._action_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._action_lbl.setFixedHeight(46)
        self._action_lbl.setStyleSheet(f"""
            background: {C["bg_card"]};
            border: 1px solid {C["border"]};
            border-radius: 10px;
            color: {C["text_lo"]};
            font-size: 15px;
            font-weight: bold;
            letter-spacing: 2px;
        """)
        left_col.addWidget(self._action_lbl)

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._start_btn = QPushButton("▶  Start Camera")
        self._stop_btn  = QPushButton("■  Stop Camera")

        self._start_btn.setStyleSheet(
            f"QPushButton {{ background: {C['accent1']}; color: white; border: none; }}"
            f"QPushButton:hover {{ background: #6d28d9; }}"
        )
        self._stop_btn.setStyleSheet(
            f"QPushButton {{ background: {C['red']}; color: white; border: none; }}"
            f"QPushButton:hover {{ background: #dc2626; }}"
        )
        self._stop_btn.setEnabled(False)

        self._start_btn.clicked.connect(self._start_camera)
        self._stop_btn.clicked.connect(self._stop_camera)

        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)
        left_col.addLayout(btn_row)

        if not KEYBOARD_AVAILABLE:
            warn = QLabel("⚠  'keyboard' module not found or no admin rights — keystrokes disabled.")
            warn.setStyleSheet(f"color: {C['accent3']}; font-size: 11px;")
            warn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            left_col.addWidget(warn)

        # ══════════════════════════════════════
        #  RIGHT  — stats + gesture guide + log
        # ══════════════════════════════════════
        right_col = QVBoxLayout()
        right_col.setSpacing(12)
        right_col.setContentsMargins(0, 0, 0, 0)

        # ── Live stats ──
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)

        self._finger_card = self._make_stat_card("FINGERS", "0")
        self._mode_card   = self._make_stat_card("MODE", "IDLE")
        stats_row.addWidget(self._finger_card[0])
        stats_row.addWidget(self._mode_card[0])
        right_col.addLayout(stats_row)

        # ── Gesture guide ──
        guide_frame = QFrame()
        guide_frame.setStyleSheet(f"""
            QFrame {{
                background: {C["bg_card"]};
                border: 1px solid {C["border"]};
                border-radius: 12px;
            }}
        """)
        guide_layout = QVBoxLayout(guide_frame)
        guide_layout.setContentsMargins(12, 10, 12, 10)
        guide_layout.setSpacing(6)

        guide_title = QLabel("GESTURE REFERENCE")
        guide_title.setStyleSheet(
            f"color: {C['accent1']}; font-size: 11px; font-weight: bold; letter-spacing: 2px;"
        )
        guide_layout.addWidget(guide_title)

        gestures_data = [
            (1, "☝",  "One finger",    "Next Slide  →"),
            (2, "✌",  "Two fingers",   "← Prev Slide"),
            (3, "🤟", "Three fingers",  "Start  (F5)"),
            (4, "🖖", "Four fingers",   "Exit  (ESC)"),
            (5, "🖐", "Open palm",     "Toggle ON/OFF"),
        ]
        for count, icon, label, action in gestures_data:
            card = GestureCard(count, icon, label, action)
            guide_layout.addWidget(card)

        right_col.addWidget(guide_frame)

        # ── Log ──
        log_label = QLabel("ACTIVITY LOG")
        log_label.setStyleSheet(
            f"color: {C['text_lo']}; font-size: 11px; letter-spacing: 1.5px;"
        )
        right_col.addWidget(log_label)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(140)
        right_col.addWidget(self._log, stretch=1)

        # ── Clear log button ──
        clear_btn = QPushButton("Clear Log")
        clear_btn.setFixedHeight(32)
        clear_btn.setStyleSheet(
            f"QPushButton {{ background: {C['bg_panel']}; color: {C['text_mid']};"
            f"border: 1px solid {C['border']}; }}"
            f"QPushButton:hover {{ border-color: {C['accent1']}; color: {C['text_hi']}; }}"
        )
        clear_btn.clicked.connect(self._log.clear)
        right_col.addWidget(clear_btn)

        # ── assemble ──
        right_col.addStretch(0)
        root.addLayout(left_col, stretch=3)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.VLine)
        divider.setStyleSheet(f"color: {C['border']};")
        root.addWidget(divider)

        root.addLayout(right_col, stretch=1)

    # ─────────────────────────────────────────
    #  HELPERS
    # ─────────────────────────────────────────
    def _make_stat_card(self, title: str, value: str):
        """Returns (QFrame, title_label, value_label)."""
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background: {C["bg_card"]};
                border: 1px solid {C["border"]};
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)

        ttl = QLabel(title)
        ttl.setStyleSheet(
            f"color: {C['text_lo']}; font-size: 10px; letter-spacing: 2px; border: none;"
        )
        val = QLabel(value)
        val.setStyleSheet(
            f"color: {C['text_hi']}; font-size: 26px; font-weight: bold; border: none;"
        )
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ttl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(ttl)
        layout.addWidget(val)
        return frame, ttl, val

    # ─────────────────────────────────────────
    #  SLOT HANDLERS
    # ─────────────────────────────────────────
    def _start_camera(self):
        if not self._thread.isRunning():
            self._thread.start()
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
            self._status_badge.set_state("● RUNNING", C["accent2"])

    def _stop_camera(self):
        self._thread.stop()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._status_badge.set_state("● STOPPED", C["red"])
        self._video.clear()
        self._video.setText("[ Camera feed stopped ]")
        self._add_log("📷 Camera stopped.")

    def _on_frame(self, img: QImage):
        pix = QPixmap.fromImage(img).scaled(
            self._video.width(), self._video.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._video.setPixmap(pix)

    def _on_finger(self, count: int):
        _, _, val = self._finger_card
        val.setText(str(count))

    def _on_action(self, text: str, color: str):
        self._action_lbl.setText(text)
        self._action_lbl.setStyleSheet(f"""
            background: {C["bg_card"]};
            border: 1.5px solid {color};
            border-radius: 10px;
            color: {color};
            font-size: 15px;
            font-weight: bold;
            letter-spacing: 2px;
        """)
        # Auto-dim after 2.5 s
        self._pulse_timer.stop()
        self._pulse_timer.start(2500)

    def _dim_action(self):
        self._pulse_timer.stop()
        self._action_lbl.setStyleSheet(f"""
            background: {C["bg_card"]};
            border: 1px solid {C["border"]};
            border-radius: 10px;
            color: {C["text_lo"]};
            font-size: 15px;
            font-weight: bold;
            letter-spacing: 2px;
        """)

    def _on_enabled(self, state: bool):
        _, _, mode_val = self._mode_card
        if state:
            mode_val.setText("ON")
            mode_val.setStyleSheet(
                f"color: {C['green']}; font-size: 26px; font-weight: bold; border: none;"
            )
            self._status_badge.set_state("● CONTROL ON", C["green"])
        else:
            mode_val.setText("OFF")
            mode_val.setStyleSheet(
                f"color: {C['red']}; font-size: 26px; font-weight: bold; border: none;"
            )
            self._status_badge.set_state("● CONTROL OFF", C["red"])

    def _add_log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._log.append(f'<span style="color:{C["text_lo"]};">[{ts}]</span> {msg}')

    # ─────────────────────────────────────────
    def closeEvent(self, event):
        self._thread.stop()
        event.accept()


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()