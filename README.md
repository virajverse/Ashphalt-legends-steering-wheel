# 🎮 Virtual Steering Wheel — MediaPipe + Python

Control any racing game using your hands as a virtual steering wheel — no physical hardware needed! Just your webcam.

Created by **VirajVerse**.

---

## ✨ Features

- 🏎️ **Zero-Hardware Control**: Use your webcam and hands to steer, accelerate, brake, and use nitro.
- 📺 **Intelligent Auto-Scaling HUD**: The overlay window starts small (`320x240`) by default so it doesn't block your game.
- ⚡ **Instant Maximize Shortcut**: Press **`M`** (or click the maximize button) to enlarge the window to full view, which automatically shrinks back to small after **15 seconds**.
- 🌟 **Neon Tech HUD**: Includes wrist crosshairs, connecting vector line, slider telemetry, speed/FPS counters, and active status indicators.
- 🚀 **Brakes & Nitro**:
  - Make a **Fist with your Left Hand** to brake (sends `Down Arrow` key, releases `W`).
  - Make a **Fist with your Right Hand** to activate Nitro (sends `Spacebar` key).
  - Keep hands open to auto-accelerate (sends `W` key).

---

## 🛠️ Requirements

### 1. Python Version
- Recommended: **Python 3.9 to 3.11** (MediaPipe has standard pre-built wheels for these versions).
- Python 3.12+ can also be used, but ensure you have the compatible `mediapipe` version installed.
- **Download Python**: [python.org/downloads](https://www.python.org/downloads/) (Make sure to check the box **"Add Python to PATH"** during installation).

### 2. Hardware
- Any standard built-in or external USB Webcam.

---

## 🚀 Installation & Setup

### 📦 Windows Setup

1. **Install Python**: Download and run the installer. Remember to check **"Add Python to PATH"**.
2. **Open Command Prompt (CMD)** or PowerShell in this directory.
3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Alternatively, install them manually:*
   ```bash
   pip install opencv-python mediapipe pynput numpy
   ```
4. **Run the script**:
   ```bash
   python steering_wheel.py
   ```

---

### 🍎 macOS Setup & Compatibility

This project is **fully compatible with macOS** (Intel and Apple Silicon / M-series chips). 

Because macOS has strict security controls around camera access and keyboard simulation, follow these steps:

1. **Install Python**: Install Python via [python.org](https://www.python.org/downloads/) or via Homebrew (`brew install python`).
2. **Install Dependencies**:
   ```bash
   pip3 install opencv-python mediapipe pynput numpy
   ```
3. **Grant Camera Permissions**:
   When you run the script, macOS will pop up a window asking for camera access for Terminal/VSCode. If not prompted, go to **System Settings → Privacy & Security → Camera** and ensure your Terminal application is allowed.
4. **Grant Accessibility Permissions (Important for Keyboard emulation)**:
   Since the script simulates keyboard inputs using `pynput`, macOS requires Accessibility permissions:
   - Go to **System Settings → Privacy & Security → Accessibility**.
   - Click the `+` icon and add your terminal application (e.g., Terminal, iTerm2, or VS Code).
   - Toggle the switch to **On**.
5. **Run the script**:
   ```bash
   python3 steering_wheel.py
   ```

*Note: The native Win32 window transparency and window-zoom features are disabled on macOS; instead, the window safely falls back to standard scaling.*

---

## 🎮 How to Control

```
Both hands level     →   Straight (W held for auto-acceleration)
Tilt hands left      →   Steer LEFT (Left Arrow key pressed)
Tilt hands right     →   Steer RIGHT (Right Arrow key pressed)
Fist (Left hand)     →   Brake (releases W, presses Down Arrow key)
Fist (Right hand)    →   Nitro (presses Spacebar)
Drop/Remove hands    →   Emergency Brake (releases all keys instantly)
```

### ⌨️ Keyboard Shortcuts (Inside the window)
- **`M` / `m`**: Maximize the camera overlay window for 15 seconds.
- **`Q` / `q` / `ESC`**: Quit the application and release all keys safely.

---

## ⚙️ Configuration (Top of `steering_wheel.py`)

You can edit these parameters at the top of the file to tweak the steering response:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `CAMERA_INDEX` | `0` | Camera source (`0` for default webcam, `1`/`2` for external USB camera). |
| `DEAD_ZONE_DEG` | `15` | Degrees of steering tilt to ignore at the center (prevents vehicle jitter). |
| `SOFT_ZONE_DEG` | `30` | Max steering angle tilt limit. |
| `FLIP_CAMERA` | `True` | Mirrors the camera feed (selfie-mode view). |
| `TRANSPARENT_HUD`| `True` | (Windows only) Creates a futuristic borderless transparent HUD overlay on your desktop. |

---

## 📄 License

This project is licensed under the **MIT License** - see the [LICENSE](file:///e:/Taliyo%20Tech/VirajVerse/gesture%20os%20c++/virtual-steering-wheel/LICENSE) file for details.
Created with ❤️ by **VirajVerse**.
