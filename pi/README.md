# Neon Creatures — Pi-Native Python Version

Ambient generative visualisation: 30–50 jellyfish/plankton boids flock across a black screen,
reacting in real time to ambient audio from a USB microphone. Designed to run fullscreen from a
Raspberry Pi over HDMI while Spotify plays on nearby speakers.

---

## Hardware Requirements

| Component | Notes |
|-----------|-------|
| Raspberry Pi 3B+ or newer | Pi 4 / Pi 5 strongly recommended for headroom |
| USB microphone | Placed near the speakers to pick up ambient audio |
| HDMI output | To projector or TV |
| Micro-SD ≥ 16 GB | Class 10 / A1 |
| Raspberry Pi OS (Bookworm / Bullseye) | 64-bit recommended on Pi 4/5 |

---

## 1. System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
    portaudio19-dev \
    python3-pip \
    python3-dev \
    libsdl2-dev \
    libsdl2-mixer-dev \
    libsdl2-image-dev \
    libsdl2-ttf-dev \
    libatlas-base-dev \
    fonts-dejavu-core
```

`portaudio19-dev` is the C library that `pyaudio` wraps — it **must** be installed before
running `pip install pyaudio`.

---

## 2. Python Dependencies

```bash
cd /path/to/generative-visualisations
pip install -r pi/requirements.txt
```

Or with a virtual environment (recommended):

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r pi/requirements.txt
```

> **Tip:** On Pi OS Bookworm, `apt`-managed Python may block `pip install` outside a venv.
> Use `pip install --break-system-packages -r pi/requirements.txt` or create a venv.

---

## 3. Configure the USB Microphone

### List available capture devices

```bash
arecord -l
```

Example output:
```
card 1: Device [USB Audio Device], device 0: USB Audio [USB Audio]
  Subdevices: 1/1
  Subdevice #0: subdevice #0
```

### Test the microphone is working

```bash
arecord -D hw:1,0 -f S16_LE -r 44100 -c 1 -d 3 test.wav
aplay test.wav
```

### Make the USB mic the default input

Create or edit `~/.asoundrc`:

```
pcm.!default {
    type asym
    playback.pcm "plughw:0"   # keep default HDMI/headphone for playback
    capture.pcm  "plughw:1"   # USB mic for capture (adjust card number)
}

ctl.!default {
    type hw
    card 0
}
```

Replace `plughw:1` with the correct card index from `arecord -l`.

Alternatively, set the default capture device system-wide via `raspi-config`:
**System Options → Audio**.

---

## 4. Run the Visualisation

```bash
python pi/main.py
```

The script starts fullscreen automatically. It will detect the USB microphone and use it;
if no mic is found it falls back to **demo mode** with simulated audio oscillations.

### Keyboard Controls

| Key | Action |
|-----|--------|
| `ESC` or `Q` | Quit |
| `D` | Toggle demo mode (random oscillating audio, no mic) |
| `F` | Toggle FPS / audio-band readout overlay |

---

## 5. Performance Tuning

The script targets **30+ FPS** on Pi 4. If you see frame drops:

- Reduce `NUM_CREATURES` at the top of `main.py` (try 25–30).
- Reduce `GLOW_LAYERS` in `Creature` from 3 to 2.
- Reduce the number of tentacle segments per chain (`chain_len` range in `Creature.__init__`).
- On Pi OS, ensure the GPU memory split is at least 128 MB:
  ```bash
  sudo raspi-config   # Performance Options → GPU Memory → 128
  ```
- Optionally set the CPU governor to `performance`:
  ```bash
  echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
  ```

---

## 6. Auto-Start on Boot with systemd

### 6.1 Create the service file

```bash
sudo nano /etc/systemd/system/neon-creatures.service
```

Paste the following, substituting your actual paths and username:

```ini
[Unit]
Description=Neon Creatures Generative Visualisation
After=graphical.target

[Service]
Type=simple
User=pi
Environment=DISPLAY=:0
Environment=XAUTHORITY=/home/pi/.Xauthority
WorkingDirectory=/home/pi/generative-visualisations
ExecStart=/home/pi/generative-visualisations/venv/bin/python pi/main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=graphical.target
```

If you're **not** using a venv, replace `ExecStart` with:
```
ExecStart=/usr/bin/python3 /home/pi/generative-visualisations/pi/main.py
```

### 6.2 Enable and start the service

```bash
sudo systemctl daemon-reload
sudo systemctl enable neon-creatures.service
sudo systemctl start neon-creatures.service
```

### 6.3 Check status / view logs

```bash
sudo systemctl status neon-creatures.service
journalctl -u neon-creatures.service -f
```

### 6.4 Stop the service

```bash
sudo systemctl stop neon-creatures.service
```

---

## 7. Troubleshooting

### "No microphone found" / runs in demo mode

- Run `arecord -l` — if no USB device appears, try a different USB port or check
  `dmesg | grep -i audio` for detection errors.
- Check `~/.asoundrc` points to the right card number.
- Verify the mic works with `arecord -d 3 test.wav && aplay test.wav`.
- The visualisation will still run in demo mode with synthesised audio oscillations.

### pygame can't open display / black screen

- Ensure the Pi has booted to the desktop (not console-only mode).
- If running over SSH, set `DISPLAY=:0` and `XAUTHORITY=/home/pi/.Xauthority` before running.
- Try `export SDL_VIDEODRIVER=x11` before launching.
- For Pi OS Lite (no desktop), use `fbdev`: `export SDL_VIDEODRIVER=fbdev SDL_FBDEV=/dev/fb0`.

### Very low FPS

- Check CPU temperature: `vcgencmd measure_temp`. Pi 4 throttles above ~80 °C — add a heatsink
  or fan.
- Reduce `NUM_CREATURES` and `GLOW_LAYERS` as described in Section 5.
- Ensure you're running the 64-bit Pi OS image for better numpy performance.

### pyaudio install fails

```bash
sudo apt-get install -y portaudio19-dev python3-dev
pip install pyaudio
```
If still failing: `pip install --no-binary pyaudio pyaudio`.

### Tentacles look jittery / creatures spin

The spring constants (`SPRING_K`, `DAMPING` in `TentacleSegment`) may need tuning for your
target FPS. Lower `SPRING_K` towards `0.10` for softer following, or raise `DAMPING` slightly.

---

## Audio Reactivity Map

| Frequency Band | Range | Effect |
|----------------|-------|--------|
| Sub-bass | 20–60 Hz | Body size pulse |
| Bass | 60–250 Hz | Movement speed |
| Mids | 250 Hz–2 kHz | Tentacle wiggle amplitude |
| Treble | 2–20 kHz | Colour brightness |
| Overall RMS | — | Trail persistence (louder = shorter trails) |

Audio values are smoothed with an exponential moving average (α = 0.15) to prevent jittery
visual responses to transient peaks.
