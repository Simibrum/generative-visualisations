# Neon Creatures — Generative Visualisations

Ambient neon jellyfish-like creatures that flock, drift, and react to music in real time. Designed to run on a Raspberry Pi connected to a projector via HDMI, with a USB microphone picking up audio from Spotify playing on external speakers.

Turn the lights off. Project onto a wall. Put on some ambient music. Enjoy.

## Two Versions

### Browser Version (`/web/`)
A set of self-contained HTML files using p5.js. Open the launcher in your phone, desktop, or the Pi's Chromium browser.

```bash
# Just open the launcher
open web/index.html
# Or serve it
python -m http.server 8000 -d web/
```

Tap/click to start (required for microphone permission).

### Pi-Native Python Version (`/pi/`)
A fullscreen pygame application with pyaudio microphone capture and numpy FFT analysis. Optimised for Raspberry Pi.

```bash
# Install system deps
sudo apt-get install portaudio19-dev python3-sdl2

# Install Python deps
pip install -r pi/requirements.txt

# Run
python pi/main.py
```

See [`pi/README.md`](pi/README.md) for detailed Pi setup, USB mic configuration, systemd auto-start, and troubleshooting.

## How It Works

- **Boids Flocking**: 40 creatures follow Craig Reynolds' separation/alignment/cohesion rules
- **Perlin Noise**: Organic drifting layered on top of flocking behaviour
- **Audio Reactivity**: Microphone input is analysed via FFT into frequency bands:
  - Sub-bass (20–60 Hz) → creature size pulsing
  - Bass (60–250 Hz) → movement speed
  - Mids (250 Hz–2 kHz) → tentacle wiggle
  - Treble (2 kHz+) → colour brightness
  - Overall amplitude → trail persistence
- **Visual Design**: Neon jellyfish with trailing tentacles on pure black, additive glow blending, motion trails

## Controls

| Key | Action |
|-----|--------|
| ESC / Q | Quit |
| D | Toggle demo mode (Pi version — no mic needed) |
| F | Toggle FPS overlay (Pi version) |
| Click/Tap | Start audio (browser version) |

## Hardware Setup

```
[Spotify on speakers] → sound waves → [USB Mic] → [Raspberry Pi] → HDMI → [Projector]
```

## License

MIT
