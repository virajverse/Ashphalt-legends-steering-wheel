import cv2
import mediapipe as mp
import numpy as np
import math
import time
import platform
import threading
from pynput.keyboard import Key, Controller

CAMERA_INDEX       = 0
DEAD_ZONE_DEG      = 15
RELEASE_ZONE_DEG   = 8
SOFT_ZONE_DEG      = 30
FLIP_CAMERA        = True
SHOW_ANGLE         = True
MIN_DETECTION_CONF = 0.7
MIN_TRACKING_CONF  = 0.5
GRACE_FRAMES       = 8
STEERING_EXPONENT  = 1.5
TRANSPARENT_HUD    = True

CLR_WHEEL   = (80, 200, 255)
CLR_LEFT    = (60, 120, 255)
CLR_RIGHT   = (50, 220, 140)
CLR_NEUTRAL = (200, 200, 200)
CLR_TEXT    = (255, 255, 255)
CLR_ACCENT  = (0, 180, 255)
CLR_HAND_L  = (255, 130, 60)
CLR_HAND_R  = (60, 230, 130)

keyboard   = Controller()
mp_hands   = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils


class ThreadedCamera:
    def __init__(self, src=CAMERA_INDEX, width=640, height=480, fps=60):
        self.src = src
        self.width = width
        self.height = height
        self.fps = fps
        
        backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(self.src, backend)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(self.src)
            
        # Fallback loop: if the configured camera index cannot be opened,
        # automatically try other common camera indices.
        if not self.cap.isOpened():
            for alt_src in [0, 1, 2]:
                if alt_src == self.src:
                    continue
                self.cap = cv2.VideoCapture(alt_src, backend)
                if not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(alt_src)
                if self.cap.isOpened():
                    self.src = alt_src
                    print(f"[INFO] Camera index {src} failed. Fell back to camera index {alt_src}.")
                    break
            
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            self.cap.set(cv2.CAP_PROP_FPS, self.fps)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
        self.grabbed = False
        self.frame = None
        self.started = False
        self.read_lock = threading.Lock()
        self.thread = None

    def start(self):
        if self.started:
            return self
        self.started = True
        self.thread = threading.Thread(target=self.update, args=(), daemon=True)
        self.thread.start()
        return self

    def update(self):
        while self.started:
            if not self.cap.isOpened():
                time.sleep(0.01)
                continue
            grabbed, frame = self.cap.read()
            if grabbed:
                with self.read_lock:
                    self.grabbed = grabbed
                    self.frame = frame
            else:
                time.sleep(0.001)

    def read(self):
        with self.read_lock:
            if self.frame is None:
                return False, None
            # Return direct reference to avoid array copying overhead
            return self.grabbed, self.frame

    def is_opened(self):
        return self.cap.isOpened()

    def release(self):
        self.started = False
        if self.thread is not None:
            self.thread.join(timeout=1.0)
        if self.cap.isOpened():
            self.cap.release()


class SteeringController:
    def __init__(self):
        self.keys_held     = {Key.left: False, Key.right: False, Key.down: False, 'w': False, Key.space: False}
        self.angle_history = []
        self.HISTORY_LEN   = 5

    def _press(self, key):
        if not self.keys_held[key]:
            keyboard.press(key)
            self.keys_held[key] = True

    def _release(self, key):
        if self.keys_held[key]:
            keyboard.release(key)
            self.keys_held[key] = False

    def release_all(self):
        for key in list(self.keys_held.keys()):
            try:
                keyboard.release(key)
            except Exception:
                pass
            self.keys_held[key] = False
        self.angle_history.clear()

    def smooth_angle(self, raw_angle: float) -> float:
        self.angle_history.append(raw_angle)
        if len(self.angle_history) > self.HISTORY_LEN:
            self.angle_history.pop(0)
        return sum(self.angle_history) / len(self.angle_history)

    def update(self, left_wrist, right_wrist, left_fist=False, right_fist=False):
        dx = right_wrist[0] - left_wrist[0]
        dy = right_wrist[1] - left_wrist[1]

        raw_angle_rad = math.atan2(dy, dx)
        raw_angle_deg = math.degrees(raw_angle_rad)
        angle = self.smooth_angle(raw_angle_deg)

        direction = "STRAIGHT"
        if angle < -DEAD_ZONE_DEG:
            direction = "LEFT"
        elif angle > DEAD_ZONE_DEG:
            direction = "RIGHT"
        elif self.keys_held[Key.left] and angle > -RELEASE_ZONE_DEG:
            direction = "STRAIGHT"
        elif self.keys_held[Key.right] and angle < RELEASE_ZONE_DEG:
            direction = "STRAIGHT"

        # Brake control (Left fist) - releases acceleration 'w' and presses down arrow key
        brake_active = left_fist
        if brake_active:
            self._release('w')
            self._press(Key.down)
        else:
            self._release(Key.down)
            self._press('w')

        # Nitro control (Right fist) - presses spacebar
        nitro_active = right_fist
        if nitro_active:
            self._press(Key.space)
        else:
            self._release(Key.space)

        strength = 0.0
        if direction == "LEFT":
            strength = min(1.0, (abs(angle) - DEAD_ZONE_DEG) / (SOFT_ZONE_DEG - DEAD_ZONE_DEG))
            strength = strength ** STEERING_EXPONENT
            self._press(Key.left)
            self._release(Key.right)
        elif direction == "RIGHT":
            strength = min(1.0, (abs(angle) - DEAD_ZONE_DEG) / (SOFT_ZONE_DEG - DEAD_ZONE_DEG))
            strength = strength ** STEERING_EXPONENT
            self._press(Key.right)
            self._release(Key.left)
        else:
            self._release(Key.left)
            self._release(Key.right)

        return angle, direction, strength, nitro_active, brake_active

    def decay_steering(self):
        # Centering the wheel: slowly decay angle towards 0
        if self.angle_history:
            self.angle_history = [a * 0.75 for a in self.angle_history]
            angle = sum(self.angle_history) / len(self.angle_history)
        else:
            angle = 0.0

        direction = "STRAIGHT"
        if angle < -DEAD_ZONE_DEG:
            direction = "LEFT"
        elif angle > DEAD_ZONE_DEG:
            direction = "RIGHT"

        # Keep auto-acceleration active during brief glitch/grace frames
        self._press('w')
        self._release(Key.space)
        self._release(Key.down)

        strength = 0.0
        if direction == "LEFT":
            strength = min(1.0, (abs(angle) - DEAD_ZONE_DEG) / (SOFT_ZONE_DEG - DEAD_ZONE_DEG))
            strength = strength ** STEERING_EXPONENT
            self._press(Key.left)
            self._release(Key.right)
        elif direction == "RIGHT":
            strength = min(1.0, (abs(angle) - DEAD_ZONE_DEG) / (SOFT_ZONE_DEG - DEAD_ZONE_DEG))
            strength = strength ** STEERING_EXPONENT
            self._press(Key.right)
            self._release(Key.left)
        else:
            self._release(Key.left)
            self._release(Key.right)

        return angle, direction, strength, False, False

    def emergency_brake(self):
        # Realign steering to straight during emergency brake
        self.angle_history.clear()
        self._release('w')
        self._release(Key.space)
        self._release(Key.left)
        self._release(Key.right)
        self._press(Key.down) # Apply brake
        return 0.0, "STRAIGHT", 0.0, False, True


def make_window_transparent(window_name):
    if platform.system() == "Windows":
        try:
            import ctypes
            hwnd = ctypes.windll.user32.FindWindowW(None, window_name)
            if hwnd != 0:
                style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
                # WS_EX_LAYERED = 0x00080000, WS_EX_TRANSPARENT = 0x00000020, WS_EX_TOPMOST = 0x00000008, WS_EX_NOACTIVATE = 0x08000000
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00080000 | 0x00000020 | 0x00000008 | 0x08000000)
                ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 0, 1)  # LWA_COLORKEY = 1
                return True
        except Exception:
            pass
    return False


def restore_and_shrink_window(window_name):
    if platform.system() == "Windows":
        try:
            import ctypes
            hwnd = ctypes.windll.user32.FindWindowW(None, window_name)
            if hwnd != 0:
                if ctypes.windll.user32.IsZoomed(hwnd):
                    ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE = 9
        except Exception:
            pass
    cv2.resizeWindow(window_name, 320, 240)


def maximize_window(window_name):
    if platform.system() == "Windows":
        try:
            import ctypes
            hwnd = ctypes.windll.user32.FindWindowW(None, window_name)
            if hwnd != 0:
                ctypes.windll.user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE = 3
                return True
        except Exception:
            pass
    cv2.resizeWindow(window_name, 1280, 960)
    return False


def draw_card_bg(frame, x, y, w, h, opacity=0.65):
    # Crop sub-region to avoid full-frame copy
    sub = frame[y:y+h, x:x+w]
    overlay = sub.copy()
    cv2.rectangle(overlay, (0, 0), (w, h), (15, 15, 25), -1)
    cv2.addWeighted(overlay, opacity, sub, 1 - opacity, 0, sub)
    cv2.rectangle(frame, (x, y), (x+w, y+h), (70, 70, 80), 1)


def draw_target_crosshair(frame, center, color):
    cx, cy = center
    cv2.circle(frame, (cx, cy), 4, color, -1)
    cv2.circle(frame, (cx, cy), 12, color, 1)
    # Target reticle lines
    cv2.line(frame, (cx - 16, cy), (cx - 8, cy), color, 1)
    cv2.line(frame, (cx + 8, cy), (cx + 16, cy), color, 1)
    cv2.line(frame, (cx, cy - 16), (cx, cy - 8), color, 1)
    cv2.line(frame, (cx, cy + 8), (cx, cy + 16), color, 1)


def draw_steering_wheel(frame, center, angle_deg, direction, strength):
    h, w = frame.shape[:2]
    radius = int(min(w, h) * 0.08)
    cx, cy = center

    color = CLR_NEUTRAL
    if direction == "LEFT":
        color = CLR_LEFT
    elif direction == "RIGHT":
        color = CLR_RIGHT

    # Outer double ring for tech look
    cv2.circle(frame, (cx, cy), radius, (20, 20, 30), -1)
    cv2.circle(frame, (cx, cy), radius, color, 1)
    cv2.circle(frame, (cx, cy), radius - 4, color, 1)

    # Rotate 3-spoke wheel design
    for sa in [0, 120, 240]:
        rad = math.radians(sa - angle_deg)
        x1 = int(cx + (radius - 12) * math.cos(rad))
        y1 = int(cy - (radius - 12) * math.sin(rad))
        x2 = int(cx + (radius - 4) * math.cos(rad))
        y2 = int(cy - (radius - 4) * math.sin(rad))
        cv2.line(frame, (x1, y1), (x2, y2), color, 1)

    # Center core
    cv2.circle(frame, (cx, cy), 5, color, -1)


def draw_hud(frame, angle, direction, strength, both_hands_visible, fps, nitro_active=False, brake_active=False):
    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX

    # 1. Sleek Top Status Cards (Pill shape)
    # Top-Left: System Status
    draw_card_bg(frame, 12, 12, 175, 28, opacity=0.7)
    status_str = "SYSTEM: READY" if both_hands_visible else "STATUS: STANDBY"
    status_clr = (60, 220, 60) if both_hands_visible else (80, 130, 255)
    cv2.circle(frame, (22, 26), 4, status_clr, -1)
    cv2.putText(frame, status_str, (34, 30), font, 0.4, CLR_TEXT, 1)

    # Top-Right: Frame Rate & Performance status
    draw_card_bg(frame, w - 82, 12, 70, 28, opacity=0.7)
    cv2.putText(frame, f"{fps:.0f} FPS", (w - 72, 30), font, 0.4, CLR_ACCENT, 1)

    # 2. Centered Dashboard Telemetry Card
    card_w, card_h = 320, 64
    card_x = (w - card_w) // 2
    card_y = h - card_h - 15

    # Crop and blend centered card to reduce memory copies and speed up CPU execution
    roi = frame[card_y:card_y+card_h, card_x:card_x+card_w]
    overlay = roi.copy()
    cv2.rectangle(overlay, (0, 0), (card_w, card_h), (12, 12, 18), -1)
    cv2.addWeighted(overlay, 0.75, roi, 0.25, 0, roi)
    cv2.rectangle(frame, (card_x, card_y), (card_x+card_w, card_y+card_h), (60, 60, 70), 1)

    # Slider Track (centered in the card)
    track_w = 220
    track_h = 4
    track_x = card_x + (card_w - track_w) // 2
    track_y = card_y + 20
    # Draw track background
    cv2.rectangle(frame, (track_x, track_y), (track_x + track_w, track_y + track_h), (50, 50, 60), -1)
    # Center notch
    mid_x = track_x + track_w // 2
    cv2.line(frame, (mid_x, track_y - 3), (mid_x, track_y + track_h + 3), (120, 120, 130), 1)

    # Calculate active slider dot coordinate
    offset = int((track_w // 2) * strength)
    slider_x = mid_x
    slider_color = CLR_NEUTRAL
    if direction == "LEFT":
        slider_x = mid_x - offset
        slider_color = CLR_LEFT
        # Draw active line
        cv2.rectangle(frame, (slider_x, track_y), (mid_x, track_y + track_h), CLR_LEFT, -1)
    elif direction == "RIGHT":
        slider_x = mid_x + offset
        slider_color = CLR_RIGHT
        # Draw active line
        cv2.rectangle(frame, (mid_x, track_y), (slider_x, track_y + track_h), CLR_RIGHT, -1)

    # Glowing slider dot
    cv2.circle(frame, (slider_x, track_y + track_h // 2), 6, slider_color, -1)
    cv2.circle(frame, (slider_x, track_y + track_h // 2), 8, slider_color, 1)

    # Bottom labels inside card
    # Direction Text
    dir_color = CLR_LEFT if direction == "LEFT" else (CLR_RIGHT if direction == "RIGHT" else CLR_NEUTRAL)
    cv2.putText(frame, direction, (mid_x - 30, card_y + 44), font, 0.45, dir_color, 1)

    # Steer Angle (left side)
    if SHOW_ANGLE:
        # Move angle text slightly down to accommodate the Brake badge if active
        cv2.putText(frame, f"{angle:+.1f} deg", (card_x + 12, card_y + 54), font, 0.4, CLR_TEXT, 1)

    # Brake Indicator (left side)
    if brake_active:
        # Red glow badge for brake
        badge_x = card_x + 12
        badge_y = card_y + 30
        cv2.rectangle(frame, (badge_x, badge_y), (badge_x + 53, badge_y + 16), (20, 20, 120), -1)
        cv2.rectangle(frame, (badge_x, badge_y), (badge_x + 53, badge_y + 16), (50, 50, 240), 1)
        cv2.putText(frame, "BRAKE", (badge_x + 8, badge_y + 12), font, 0.35, (80, 80, 255), 1)

    # Nitro Indicator (right side)
    if nitro_active:
        # Glow badge
        badge_x = card_x + card_w - 65
        badge_y = card_y + 30
        cv2.rectangle(frame, (badge_x, badge_y), (badge_x + 53, badge_y + 16), (30, 40, 150), -1)
        cv2.rectangle(frame, (badge_x, badge_y), (badge_x + 53, badge_y + 16), (80, 100, 255), 1)
        cv2.putText(frame, "NITRO", (badge_x + 8, badge_y + 12), font, 0.35, (80, 120, 255), 1)

    # Steering Wheel Graphic (rendered at bottom-right corner)
    draw_steering_wheel(frame, (w - 55, h - 50), angle, direction, strength)

    # Watermark
    cv2.putText(frame, "Created by VirajVerse", (15, h - 15), font, 0.35, (120, 120, 130), 1)


def draw_hand_connection(frame, lw, rw):
    lx, ly = lw
    rx, ry = rw
    # Glowing neon connector line
    cv2.line(frame, (lx, ly), (rx, ry), (25, 45, 65), 5)
    cv2.line(frame, (lx, ly), (rx, ry), CLR_ACCENT, 1)
    
    # Midpoint of the hands connection
    mx = (lx + rx) // 2
    my = (ly + ry) // 2
    cv2.circle(frame, (mx, my), 5, CLR_WHEEL, -1)
    cv2.circle(frame, (mx, my), 9, CLR_WHEEL, 1)

    # Advanced crosshairs instead of solid circles
    draw_target_crosshair(frame, (lx, ly), CLR_HAND_L)
    draw_target_crosshair(frame, (rx, ry), CLR_HAND_R)


def is_fist(hand_landmarks) -> bool:
    # Check index, middle, ring, pinky tips vs pip joints
    # y increases downwards in image coordinates, so tip.y > pip.y means finger is bent/folded.
    folded = 0
    # Index: tip (8), pip (6)
    if hand_landmarks.landmark[8].y > hand_landmarks.landmark[6].y:
        folded += 1
    # Middle: tip (12), pip (10)
    if hand_landmarks.landmark[12].y > hand_landmarks.landmark[10].y:
        folded += 1
    # Ring: tip (16), pip (14)
    if hand_landmarks.landmark[16].y > hand_landmarks.landmark[14].y:
        folded += 1
    # Pinky: tip (20), pip (18)
    if hand_landmarks.landmark[20].y > hand_landmarks.landmark[18].y:
        folded += 1
    return folded >= 3


def main():
    window_name = "Virtual Steering Wheel"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 320, 240)  # Start with a small, neat size
    cv2.setWindowProperty(window_name, cv2.WND_PROP_TOPMOST, 1)

    cap = ThreadedCamera(CAMERA_INDEX).start()
    if not cap.is_opened():
        print("[ERROR] Cannot open camera.")
        print("  -> On macOS: System Settings > Privacy & Security > Camera")
        return

    controller = SteeringController()

    hands = mp_hands.Hands(
        static_image_mode=False,
        max_num_hands=2,
        model_complexity=0,
        min_detection_confidence=MIN_DETECTION_CONF,
        min_tracking_confidence=MIN_TRACKING_CONF,
    )

    conn_style     = mp_drawing.DrawingSpec(color=(80, 80, 100), thickness=1)
    landmark_style = mp_drawing.DrawingSpec(color=(200, 200, 255), thickness=1, circle_radius=2)

    prev_time    = time.time()
    angle        = 0.0
    direction    = "STRAIGHT"
    strength     = 0.0
    nitro_active = False
    brake_active = False
    lost_frames  = 0

    print("=" * 60)
    print("  Virtual Steering Wheel  |  Press Q to quit, M to maximize")
    print("  -> Auto-acceleration ('w') is enabled when hands are detected.")
    print("  -> Nitro (Spacebar) is triggered by making a fist with EITHER hand.")
    print("  -> Press M to maximize / restore (toggle) the window.")
    print("=" * 60)

    frame_count = 0
    win_w, win_h = 320, 240
    transparency_applied = False
    blank_frame = np.zeros((480, 640, 3), dtype=np.uint8) if TRANSPARENT_HUD else None

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                time.sleep(0.001)
                continue

            frame_count += 1

            if FLIP_CAMERA:
                frame = cv2.flip(frame, 1)

            h, w = frame.shape[:2]

            # Use pre-allocated canvas for zero-allocation transparent rendering
            if TRANSPARENT_HUD:
                blank_frame.fill(0)
                display_frame = blank_frame
            else:
                display_frame = frame

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = hands.process(rgb)
            rgb.flags.writeable = True

            both_visible = False

            if results.multi_hand_landmarks and results.multi_handedness:
                hand_data = {}
                fist_status = {}

                for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                    label = handedness.classification[0].label

                    # Draw on the display canvas instead of camera feed
                    mp_drawing.draw_landmarks(display_frame, hand_landmarks, mp_hands.HAND_CONNECTIONS, landmark_style, conn_style)

                    # Check if the hand is making a fist
                    fist_status[label] = is_fist(hand_landmarks)

                    wrist = hand_landmarks.landmark[0]
                    wx    = int(wrist.x * w)
                    wy    = int(wrist.y * h)
                    hand_data[label] = (wrist.x, wrist.y, wx, wy)

                if "Left" in hand_data and "Right" in hand_data:
                    both_visible = True
                    lost_frames  = 0
                    lx_n, ly_n, lx_px, ly_px = hand_data["Left"]
                    rx_n, ry_n, rx_px, ry_px = hand_data["Right"]

                    draw_hand_connection(display_frame, (lx_px, ly_px), (rx_px, ry_px))
                    
                    left_fist = fist_status.get("Left", False)
                    right_fist = fist_status.get("Right", False)
                    angle, direction, strength, nitro_active, brake_active = controller.update(
                        (lx_n, ly_n), (rx_n, ry_n), left_fist, right_fist
                    )
                else:
                    lost_frames += 1
                    if lost_frames < GRACE_FRAMES:
                        angle, direction, strength, nitro_active, brake_active = controller.decay_steering()
                    elif lost_frames < GRACE_FRAMES + 30:
                        angle, direction, strength, nitro_active, brake_active = controller.emergency_brake()
                    else:
                        controller.release_all()
                        angle, direction, strength, nitro_active, brake_active = 0.0, "STRAIGHT", 0.0, False, False
            else:
                lost_frames += 1
                if lost_frames < GRACE_FRAMES:
                    angle, direction, strength, nitro_active, brake_active = controller.decay_steering()
                elif lost_frames < GRACE_FRAMES + 30:
                    angle, direction, strength, nitro_active, brake_active = controller.emergency_brake()
                else:
                    controller.release_all()
                    angle, direction, strength, nitro_active, brake_active = 0.0, "STRAIGHT", 0.0, False, False

            now       = time.time()
            fps       = 1.0 / max(now - prev_time, 1e-6)
            prev_time = now

            draw_hud(display_frame, angle, direction, strength, both_visible, fps, nitro_active, brake_active)

            # Check window size only once every 15 frames to reduce OS-level blocking query latency
            if frame_count % 15 == 0:
                try:
                    rect = cv2.getWindowImageRect(window_name)
                    if rect is not None and len(rect) == 4:
                        _, _, win_w, win_h = rect
                except Exception:
                    pass

            # Only resize if the window dimensions differ from the frame dimensions
            if win_w > 10 and win_h > 10 and (win_w != w or win_h != h):
                display_frame = cv2.resize(display_frame, (win_w, win_h), interpolation=cv2.INTER_LINEAR)

            cv2.imshow(window_name, display_frame)

            # Set transparency after the window has been displayed at least once
            if TRANSPARENT_HUD and not transparency_applied:
                transparency_applied = make_window_transparent(window_name)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord('q'), ord('Q'), 27):
                break
            elif key in (ord('m'), ord('M')):
                # Detect if window is currently large (either maximized or manually resized)
                is_currently_large = False
                if platform.system() == "Windows":
                    try:
                        import ctypes
                        hwnd = ctypes.windll.user32.FindWindowW(None, window_name)
                        if hwnd != 0 and ctypes.windll.user32.IsZoomed(hwnd):
                            is_currently_large = True
                    except Exception:
                        pass
                
                if win_w > 350 or win_h > 270:
                    is_currently_large = True

                if is_currently_large:
                    print("[INFO] Shortcut: Shrinking window.")
                    restore_and_shrink_window(window_name)
                    win_w, win_h = 320, 240
                else:
                    print("[INFO] Shortcut: Maximizing window.")
                    maximize_window(window_name)
                    win_w, win_h = 1280, 960

    finally:
        controller.release_all()
        hands.close()
        cap.release()
        cv2.destroyAllWindows()
        print("\n[INFO] Stopped. All keys released.")


if __name__ == "__main__":
    main()
