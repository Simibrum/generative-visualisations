"""
Neon Creatures — Ambient Generative Visualisation for Raspberry Pi
===================================================================
Jellyfish/plankton boids that flock, drift on Perlin noise, and react
to microphone audio in real time.

Controls:
    ESC / Q  — quit
    D        — toggle demo mode (random noise, no mic required)
    F        — toggle FPS display

Requirements: pygame, pyaudio, numpy, opensimplex
"""

from __future__ import annotations

import math
import random
import sys
import threading
import time
from typing import Optional

import numpy as np
import pygame
import pygame.gfxdraw

# opensimplex is lightweight and pure-Python — works fine on Pi
try:
    from opensimplex import OpenSimplex
    _HAS_OPENSIMPLEX = True
except ImportError:
    _HAS_OPENSIMPLEX = False
    print("[warn] opensimplex not found — using fallback noise")

try:
    import pyaudio
    _HAS_PYAUDIO = True
except ImportError:
    _HAS_PYAUDIO = False
    print("[warn] pyaudio not found — running in demo mode")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TARGET_FPS = 30
NUM_CREATURES = 40          # tweak 30–50

# Boid steering weights
W_SEPARATION = 1.8
W_ALIGNMENT  = 1.0
W_COHESION   = 1.0

NEIGHBOR_RADIUS   = 120.0   # px — neighbourhood for alignment + cohesion
SEPARATION_RADIUS = 50.0    # px — minimum personal space

MAX_SPEED   = 2.5           # px/frame (before audio modulation)
MAX_FORCE   = 0.08          # steering force clamp

# Neon palette — (R, G, B)
PALETTE = [
    (  0, 255, 255),   # cyan
    (255,   0, 255),   # magenta
    (  0, 102, 255),   # electric blue
    (  0, 255, 102),   # lime green
    (153,  51, 255),   # soft purple
    (255, 102,   0),   # warm orange
]

# Audio capture settings
AUDIO_RATE        = 44100
AUDIO_CHUNK       = 1024
AUDIO_CHANNELS    = 1
AUDIO_FORMAT_PA   = None      # set after pyaudio import
AUDIO_EMA_ALPHA   = 0.15      # exponential moving average smoothing

# Frequency band boundaries (Hz)
FREQ_SUBBASS  = (20,   60)
FREQ_BASS     = (60,  250)
FREQ_MIDS     = (250, 2000)
FREQ_TREBLE   = (2000, 20000)

# Trail overlay alpha (0–255): lower = longer trails
TRAIL_BASE_ALPHA  = 15        # quiet/demo
TRAIL_LOUD_ALPHA  = 45        # loud audio

# ---------------------------------------------------------------------------
# Simple fallback noise when opensimplex is unavailable
# ---------------------------------------------------------------------------

def _fbm_fallback(x: float, y: float, t: float) -> float:
    """Cheap pseudo-noise from trig; not true Perlin but visually adequate."""
    return (
        math.sin(x * 0.03 + t) * 0.5 +
        math.sin(y * 0.04 + t * 1.3) * 0.3 +
        math.sin((x + y) * 0.02 + t * 0.7) * 0.2
    )


# ---------------------------------------------------------------------------
# Noise helper — wraps opensimplex or fallback uniformly
# ---------------------------------------------------------------------------

class NoiseField:
    """2D + time noise field, returns values in roughly [-1, 1]."""

    def __init__(self, seed: int = 0) -> None:
        if _HAS_OPENSIMPLEX:
            self._gen = OpenSimplex(seed=seed)
        else:
            self._gen = None

    def sample(self, x: float, y: float, t: float) -> float:
        if self._gen is not None:
            # Stack two octaves for richer movement
            return (
                self._gen.noise3(x * 0.004, y * 0.004, t * 0.5) * 0.7 +
                self._gen.noise3(x * 0.009 + 100, y * 0.009 + 100, t * 0.8) * 0.3
            )
        return _fbm_fallback(x, y, t)


# ---------------------------------------------------------------------------
# Audio Analyser
# ---------------------------------------------------------------------------

class AudioAnalyzer:
    """
    Captures audio from the default input device in a background daemon thread.
    Computes FFT and extracts energy in four frequency bands.
    All public attributes are safe to read from the main thread.
    """

    def __init__(self, demo_mode: bool = False) -> None:
        self.demo_mode = demo_mode or not _HAS_PYAUDIO

        # Smoothed band energies (0.0–1.0)
        self.sub_bass: float = 0.0
        self.bass:     float = 0.0
        self.mids:     float = 0.0
        self.treble:   float = 0.0
        self.rms:      float = 0.0

        # Internal raw (pre-smooth) values
        self._raw_sub_bass: float = 0.0
        self._raw_bass:     float = 0.0
        self._raw_mids:     float = 0.0
        self._raw_treble:   float = 0.0
        self._raw_rms:      float = 0.0

        self._lock   = threading.Lock()
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._stream = None
        self._pa     = None

        # Simulate time for demo oscillations
        self._demo_t: float = 0.0

        if not self.demo_mode:
            self._try_open_stream()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _try_open_stream(self) -> None:
        global AUDIO_FORMAT_PA
        try:
            self._pa = pyaudio.PyAudio()
            AUDIO_FORMAT_PA = pyaudio.paFloat32
            self._stream = self._pa.open(
                format=AUDIO_FORMAT_PA,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                input=True,
                frames_per_buffer=AUDIO_CHUNK,
            )
            print("[audio] Microphone opened successfully")
        except Exception as exc:
            print(f"[audio] Could not open microphone: {exc}")
            print("[audio] Falling back to demo mode")
            self._cleanup_pa()
            self.demo_mode = True

    def _cleanup_pa(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    def _hz_to_bin(self, hz: float) -> int:
        """Convert Hz to FFT bin index for AUDIO_CHUNK at AUDIO_RATE."""
        return max(0, min(AUDIO_CHUNK // 2, int(hz * AUDIO_CHUNK / AUDIO_RATE)))

    def _band_energy(self, magnitudes: np.ndarray, lo_hz: float, hi_hz: float) -> float:
        lo = self._hz_to_bin(lo_hz)
        hi = self._hz_to_bin(hi_hz)
        if hi <= lo:
            return 0.0
        return float(np.mean(magnitudes[lo:hi]))

    def _ema(self, current: float, target: float) -> float:
        return current * (1.0 - AUDIO_EMA_ALPHA) + target * AUDIO_EMA_ALPHA

    def _process_audio_frame(self, data: bytes) -> None:
        try:
            samples = np.frombuffer(data, dtype=np.float32)
        except ValueError:
            return

        # RMS amplitude
        rms_raw = float(np.sqrt(np.mean(samples ** 2)))

        # FFT magnitude (one-sided)
        windowed = samples * np.hanning(len(samples))
        fft_raw  = np.abs(np.fft.rfft(windowed))
        # Normalise by chunk size
        fft_norm = fft_raw / (AUDIO_CHUNK / 2)

        sb = self._band_energy(fft_norm, *FREQ_SUBBASS)
        b  = self._band_energy(fft_norm, *FREQ_BASS)
        m  = self._band_energy(fft_norm, *FREQ_MIDS)
        tr = self._band_energy(fft_norm, *FREQ_TREBLE)

        # Scale to roughly 0–1 with reasonable ceilings
        # These divisors are empirical — tune for your environment
        sb_n  = min(1.0, sb  / 0.15)
        b_n   = min(1.0, b   / 0.12)
        m_n   = min(1.0, m   / 0.08)
        tr_n  = min(1.0, tr  / 0.05)
        rms_n = min(1.0, rms_raw / 0.3)

        with self._lock:
            self._raw_sub_bass = sb_n
            self._raw_bass     = b_n
            self._raw_mids     = m_n
            self._raw_treble   = tr_n
            self._raw_rms      = rms_n

    def _capture_loop(self) -> None:
        while self._active:
            if self.demo_mode:
                # Generate slow oscillating pseudo-audio for demo
                t = self._demo_t
                self._demo_t += 0.02
                with self._lock:
                    self._raw_sub_bass = (math.sin(t * 0.7) + 1) * 0.35
                    self._raw_bass     = (math.sin(t * 1.1 + 1) + 1) * 0.3
                    self._raw_mids     = (math.sin(t * 2.3 + 2) + 1) * 0.25
                    self._raw_treble   = (math.sin(t * 3.7 + 0.5) + 1) * 0.2
                    self._raw_rms      = (math.sin(t * 0.9) + 1) * 0.3
                time.sleep(AUDIO_CHUNK / AUDIO_RATE)
            else:
                try:
                    data = self._stream.read(AUDIO_CHUNK, exception_on_overflow=False)
                    self._process_audio_frame(data)
                except Exception as exc:
                    print(f"[audio] Read error: {exc}")
                    time.sleep(0.05)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._active = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def update(self) -> None:
        """
        Pump EMA smoothing on the main thread. Call once per frame.
        Reads raw values written by the capture thread (lock-protected)
        and applies exponential moving average in-place.
        """
        with self._lock:
            raw_sb  = self._raw_sub_bass
            raw_b   = self._raw_bass
            raw_m   = self._raw_mids
            raw_tr  = self._raw_treble
            raw_rms = self._raw_rms

        self.sub_bass = self._ema(self.sub_bass, raw_sb)
        self.bass     = self._ema(self.bass,     raw_b)
        self.mids     = self._ema(self.mids,     raw_m)
        self.treble   = self._ema(self.treble,   raw_tr)
        self.rms      = self._ema(self.rms,      raw_rms)

    def stop(self) -> None:
        self._active = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._cleanup_pa()

    @property
    def mode_label(self) -> str:
        return "DEMO" if self.demo_mode else "MIC"


# ---------------------------------------------------------------------------
# Tentacle segment
# ---------------------------------------------------------------------------

class TentacleSegment:
    """A single node in a tentacle chain, following its parent with damped spring."""

    SPRING_K  = 0.18   # spring stiffness
    DAMPING   = 0.72   # velocity damping (0 = overdamped, 1 = undamped)
    RADIUS    = 3.0    # base draw radius

    def __init__(self, x: float, y: float) -> None:
        self.x   = x
        self.y   = y
        self.vx  = 0.0
        self.vy  = 0.0

    def update(
        self,
        parent_x: float,
        parent_y: float,
        wiggle_offset: float,
        wiggle_amp: float,
    ) -> None:
        # Spring pull toward parent (offset laterally by wiggle)
        target_x = parent_x + math.cos(wiggle_offset) * wiggle_amp
        target_y = parent_y + math.sin(wiggle_offset) * wiggle_amp

        ax = (target_x - self.x) * self.SPRING_K
        ay = (target_y - self.y) * self.SPRING_K

        self.vx = (self.vx + ax) * self.DAMPING
        self.vy = (self.vy + ay) * self.DAMPING
        self.x += self.vx
        self.y += self.vy

    def draw(
        self,
        surface: pygame.Surface,
        colour: tuple[int, int, int],
        alpha: int,
        radius: float,
    ) -> None:
        r = max(1, int(radius))
        try:
            pygame.gfxdraw.filled_circle(
                surface, int(self.x), int(self.y), r,
                (*colour, alpha)
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Creature (jellyfish / plankton boid)
# ---------------------------------------------------------------------------

class Creature:
    """
    A single boid with a glowing elliptical body and 2–4 tentacle chains.
    Velocity is stored as a 2-element numpy array for vector maths convenience.
    """

    BODY_RADIUS_BASE = 8.0     # px
    GLOW_LAYERS      = 3       # number of concentric glow rings
    TENTACLE_SPACING = 10.0    # px — gap between tentacle segment parents
    TENTACLE_COUNT_RANGE = (2, 4)

    def __init__(
        self,
        x: float,
        y: float,
        colour: tuple[int, int, int],
        noise_field: NoiseField,
        noise_offset: float = 0.0,
    ) -> None:
        self.pos    = np.array([x, y], dtype=float)
        speed_init  = random.uniform(0.5, MAX_SPEED)
        angle_init  = random.uniform(0, 2 * math.pi)
        self.vel    = np.array([
            math.cos(angle_init) * speed_init,
            math.sin(angle_init) * speed_init,
        ])
        self.acc    = np.zeros(2)

        self.base_colour = colour
        self.colour      = colour            # modulated each frame

        self._noise   = noise_field
        self._n_off   = noise_offset         # unique per-creature noise offset

        # Tentacle chains
        n_tentacles = random.randint(*self.TENTACLE_COUNT_RANGE)
        self.tentacles: list[list[TentacleSegment]] = []
        for _ in range(n_tentacles):
            chain_len = random.randint(3, 6)
            chain = [TentacleSegment(x, y) for _ in range(chain_len)]
            self.tentacles.append(chain)

        self._wiggle_phase  = random.uniform(0, 2 * math.pi)
        self._wiggle_speed  = random.uniform(0.06, 0.12)

    # ------------------------------------------------------------------
    # Steering helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _limit(v: np.ndarray, mag: float) -> np.ndarray:
        n = np.linalg.norm(v)
        return v * (mag / n) if n > mag else v

    def _steer_toward(self, target_vel: np.ndarray) -> np.ndarray:
        desired = self._limit(target_vel, MAX_SPEED)
        steer   = desired - self.vel
        return self._limit(steer, MAX_FORCE)

    # ------------------------------------------------------------------
    # Boid rule helpers (called by Flock)
    # ------------------------------------------------------------------

    def apply_force(self, force: np.ndarray) -> None:
        self.acc += force

    # ------------------------------------------------------------------
    # Per-frame update
    # ------------------------------------------------------------------

    def update(
        self,
        width: int,
        height: int,
        t: float,
        audio: AudioAnalyzer,
    ) -> None:
        # --- Perlin noise drift ---
        nx = self._noise.sample(self.pos[0] + self._n_off, self.pos[1], t)
        ny = self._noise.sample(self.pos[0], self.pos[1] + self._n_off + 50, t + 5)
        noise_force = np.array([nx, ny]) * 0.04
        self.acc += noise_force

        # --- Speed modulation from bass ---
        speed_scale = 1.0 + audio.bass * 1.5
        max_speed   = MAX_SPEED * speed_scale

        # --- Integrate ---
        self.vel += self.acc
        self.vel  = self._limit(self.vel, max_speed)
        self.pos += self.vel
        self.acc *= 0.0        # reset accumulator

        # --- Toroidal wrapping ---
        self.pos[0] %= width
        self.pos[1] %= height

        # --- Colour modulation from treble (brightness) ---
        bright = 1.0 + audio.treble * 0.6
        r = min(255, int(self.base_colour[0] * bright))
        g = min(255, int(self.base_colour[1] * bright))
        b = min(255, int(self.base_colour[2] * bright))
        self.colour = (r, g, b)

        # --- Tentacle update ---
        self._wiggle_phase += self._wiggle_speed
        wiggle_amp  = 6.0 + audio.mids * 14.0   # mids → wider wiggle
        for i, chain in enumerate(self.tentacles):
            angle_offset = (2 * math.pi / len(self.tentacles)) * i
            for j, seg in enumerate(chain):
                if j == 0:
                    parent_x = self.pos[0]
                    parent_y = self.pos[1]
                else:
                    parent_x = chain[j - 1].x
                    parent_y = chain[j - 1].y
                phase = self._wiggle_phase + angle_offset + j * 0.4
                seg.update(parent_x, parent_y, phase, wiggle_amp)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(
        self,
        surface: pygame.Surface,
        audio: AudioAnalyzer,
    ) -> None:
        px, py = int(self.pos[0]), int(self.pos[1])

        # Body size pulse from sub-bass
        body_r = self.BODY_RADIUS_BASE * (1.0 + audio.sub_bass * 0.8)

        # Draw tentacles first (behind body)
        for i, chain in enumerate(self.tentacles):
            for j, seg in enumerate(chain):
                fade = 1.0 - j / (len(chain) + 1)   # fade toward tip
                alpha = max(20, int(180 * fade))
                radius = max(1.0, (TentacleSegment.RADIUS + 1) * fade)
                seg.draw(surface, self.colour, alpha, radius)

        # Glow layers (largest → most transparent, smallest → most opaque)
        for layer in range(self.GLOW_LAYERS, 0, -1):
            scale = 1.0 + (layer - 1) * 0.6
            alpha = max(10, int(90 / layer))
            r = int(body_r * scale)
            if r < 1:
                continue
            # Ellipse (slightly wider than tall like a jellyfish bell)
            rect = pygame.Rect(px - int(r * 1.3), py - r, int(r * 2.6), r * 2)
            glow_surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.ellipse(
                glow_surf,
                (*self.colour, alpha),
                glow_surf.get_rect(),
            )
            surface.blit(glow_surf, rect.topleft, special_flags=pygame.BLEND_ADD)

        # Solid core
        core_r = max(2, int(body_r * 0.55))
        core_alpha = 200
        try:
            pygame.gfxdraw.filled_ellipse(
                surface, px, py, core_r + 2, core_r,
                (*self.colour, core_alpha),
            )
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Flock
# ---------------------------------------------------------------------------

class Flock:
    """Container for all creatures. Applies boid rules each frame."""

    def __init__(
        self,
        count: int,
        width: int,
        height: int,
        noise_field: NoiseField,
    ) -> None:
        self.creatures: list[Creature] = []
        for i in range(count):
            colour = random.choice(PALETTE)
            x = random.uniform(0, width)
            y = random.uniform(0, height)
            offset = i * 37.1   # unique noise offset per creature
            self.creatures.append(Creature(x, y, colour, noise_field, offset))

    def apply_rules(self) -> None:
        """
        Compute separation, alignment, cohesion for each creature and
        apply the resulting steering forces. O(n²) — fine for n ≤ 50.
        """
        positions = np.array([c.pos for c in self.creatures])   # (N, 2)
        velocities = np.array([c.vel for c in self.creatures])  # (N, 2)

        for i, creature in enumerate(self.creatures):
            # Vectorised distance computation to all others
            diffs = positions - creature.pos          # (N, 2)
            dists = np.linalg.norm(diffs, axis=1)     # (N,)
            dists[i] = 1e9                             # exclude self

            # --- Separation (avoid crowding) ---
            sep_mask  = dists < SEPARATION_RADIUS
            sep_force = np.zeros(2)
            if sep_mask.any():
                close_diffs = positions[sep_mask] - creature.pos
                # Weight inversely by distance
                close_dists = dists[sep_mask, np.newaxis]
                repel = -close_diffs / (close_dists ** 2 + 1e-6)
                sep_force = repel.mean(axis=0)
                sep_force = creature._steer_toward(sep_force * MAX_SPEED)

            # --- Alignment (match velocity of neighbours) ---
            ali_mask  = (dists < NEIGHBOR_RADIUS) & ~sep_mask
            ali_force = np.zeros(2)
            if ali_mask.any():
                avg_vel   = velocities[ali_mask].mean(axis=0)
                ali_force = creature._steer_toward(avg_vel)

            # --- Cohesion (move toward centre of neighbours) ---
            coh_force = np.zeros(2)
            if ali_mask.any():
                avg_pos   = positions[ali_mask].mean(axis=0)
                desired   = avg_pos - creature.pos
                coh_force = creature._steer_toward(desired)

            # Apply weighted forces
            creature.apply_force(sep_force * W_SEPARATION)
            creature.apply_force(ali_force * W_ALIGNMENT)
            creature.apply_force(coh_force * W_COHESION)

    def update(self, width: int, height: int, t: float, audio: AudioAnalyzer) -> None:
        self.apply_rules()
        for creature in self.creatures:
            creature.update(width, height, t, audio)

    def draw(self, surface: pygame.Surface, audio: AudioAnalyzer) -> None:
        for creature in self.creatures:
            creature.draw(surface, audio)


# ---------------------------------------------------------------------------
# Trail surface helper
# ---------------------------------------------------------------------------

def make_trail_surface(width: int, height: int) -> pygame.Surface:
    """Return a black surface with per-pixel alpha for trail overlay."""
    s = pygame.Surface((width, height), pygame.SRCALPHA)
    s.fill((0, 0, 0, 0))
    return s


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ---- Pygame init ----
    pygame.init()
    pygame.display.set_caption("Neon Creatures")
    pygame.mouse.set_visible(False)

    info   = pygame.display.Info()
    WIDTH  = info.current_w
    HEIGHT = info.current_h
    screen = pygame.display.set_mode(
        (WIDTH, HEIGHT),
        pygame.FULLSCREEN | pygame.HWSURFACE | pygame.DOUBLEBUF,
    )
    clock  = pygame.time.Clock()

    # ---- Off-screen composite surface (supports per-pixel alpha) ----
    canvas = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 255))

    # ---- Noise ----
    noise = NoiseField(seed=42)

    # ---- Flock ----
    flock = Flock(NUM_CREATURES, WIDTH, HEIGHT, noise)

    # ---- Audio ----
    demo_mode  = not _HAS_PYAUDIO   # force demo if pyaudio missing
    audio      = AudioAnalyzer(demo_mode=demo_mode)
    audio.start()

    # ---- State ----
    show_fps   = False
    font       = pygame.font.SysFont("monospace", 18)
    t          = 0.0
    frame      = 0
    running    = True

    print(f"[main] Running {WIDTH}×{HEIGHT}  mode={audio.mode_label}  creatures={NUM_CREATURES}")
    print("[main] Controls: ESC/Q=quit  D=toggle demo  F=toggle FPS")

    while running:
        dt = clock.tick(TARGET_FPS)   # ms; also caps FPS

        # ---- Events ----
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                elif event.key == pygame.K_d:
                    # Toggle demo mode
                    audio.stop()
                    audio = AudioAnalyzer(demo_mode=not audio.demo_mode)
                    audio.start()
                    print(f"[main] Switched to {audio.mode_label}")
                elif event.key == pygame.K_f:
                    show_fps = not show_fps

        # ---- Audio update (EMA on main thread) ----
        audio.update()

        # ---- Trail overlay ----
        # RMS drives how quickly old frames fade:
        #   quiet  → low alpha → slow fade → long trails
        #   loud   → high alpha → fast fade → short snappy trails
        trail_alpha = int(
            TRAIL_BASE_ALPHA + (TRAIL_LOUD_ALPHA - TRAIL_BASE_ALPHA) * audio.rms
        )
        trail_alpha = max(5, min(80, trail_alpha))

        # Fill canvas with semi-transparent black to create motion blur effect
        canvas.fill((0, 0, 0, trail_alpha))
        screen.blit(canvas, (0, 0))
        # Reset canvas to fully transparent for this frame's drawing
        canvas.fill((0, 0, 0, 0))

        # ---- Update + draw ----
        t += 0.016   # ~1/60 s per frame, independent of actual dt
        flock.update(WIDTH, HEIGHT, t, audio)
        flock.draw(canvas, audio)

        # Blit creature layer onto screen with additive blending for glow
        screen.blit(canvas, (0, 0), special_flags=pygame.BLEND_ADD)

        # ---- HUD ----
        if show_fps:
            fps_surf = font.render(
                f"FPS:{clock.get_fps():.0f}  {audio.mode_label}"
                f"  sb={audio.sub_bass:.2f} b={audio.bass:.2f}"
                f"  m={audio.mids:.2f} tr={audio.treble:.2f}",
                True, (100, 100, 100),
            )
            screen.blit(fps_surf, (10, 10))

        pygame.display.flip()
        frame += 1

    # ---- Cleanup ----
    audio.stop()
    pygame.quit()
    sys.exit(0)


if __name__ == "__main__":
    main()
