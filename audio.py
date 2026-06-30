"""Ambient — host-side looping background sound (computer / attached speaker).

Plays a chosen waveform on a loop while an experiment waits for the shrew to
initiate at the centre port. It is independent of the Arduino buzzer (Tone) —
this comes out of the computer's audio device via pygame.mixer.

The waveform is SYNTHESISED on the fly (stdlib only) from a few knobs, so the
sound, pitch, and speed are all adjustable:

    kind  : "noise"  – soft low-passed hiss (pitch/speed ignored)
            "sine"   – steady tone at `pitch` Hz (speed = tremolo rate, Hz)
            "rising" – repeating upward sweep from pitch -> 2*pitch
                       (speed = sweeps per second)
            "pulse"  – repeating beep at `pitch` Hz (speed = beeps per second)

Everything is best-effort: if pygame / the mixer is unavailable (head-less, or
SDL_AUDIODRIVER=dummy) every method is a safe no-op and the rig runs silently.

    amb = Ambient(kind="sine", pitch=300, speed=2.0, volume=0.3)
    amb.start();  amb.stop();  amb.close()
"""

import io
import math
import os
import random
import struct
import wave

try:
    import pygame
except ImportError:                      # pygame optional -> silent
    pygame = None

_SR = 44100            # sample rate
_LOOP_SECONDS = 2.0    # loop length; patterns are tiled to it for seamless looping
_AMP = 0.5             # synthesis amplitude (0..1); loudness set via Sound volume


def _synth_wav(kind, pitch, speed, seconds=_LOOP_SECONDS):
    """Return an in-memory WAV (BytesIO) of the requested waveform."""
    n = max(1, int(_SR * seconds))
    pitch = max(1.0, float(pitch))
    speed = max(0.0, float(speed))
    samples = [0.0] * n

    if kind == "sine":
        # integer number of cycles over the loop -> seamless
        cycles = max(1, round(pitch * seconds))
        freq = cycles / seconds
        trem = speed                       # tremolo rate (Hz); 0 = none
        for i in range(n):
            t = i / _SR
            a = 1.0
            if trem > 0:
                a = 0.5 + 0.5 * math.sin(2 * math.pi * trem * t)
            samples[i] = a * math.sin(2 * math.pi * freq * t)

    elif kind == "rising":
        sweeps = max(1, round((speed or 1.0) * seconds))
        period = seconds / sweeps
        for i in range(n):
            t = i / _SR
            frac = (t % period) / period       # 0..1 within each sweep
            freq = pitch * (1.0 + frac)         # pitch -> 2*pitch
            samples[i] = math.sin(2 * math.pi * freq * t)

    elif kind == "pulse":
        pulses = max(1, round((speed or 1.0) * seconds))
        period = seconds / pulses
        for i in range(n):
            t = i / _SR
            on = (t % period) < (period * 0.5)  # 50% duty
            samples[i] = math.sin(2 * math.pi * pitch * t) if on else 0.0

    else:  # "noise" (default): one-pole low-passed white noise
        prev = 0.0
        for i in range(n):
            prev = prev * 0.88 + random.uniform(-1.0, 1.0) * 0.12
            samples[i] = max(-1.0, min(1.0, prev * 4.0))

    frames = bytearray()
    for s in samples:
        frames += struct.pack("<h", int(max(-1.0, min(1.0, s)) * _AMP * 32767))

    bio = io.BytesIO()
    with wave.open(bio, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_SR)
        w.writeframes(frames)
    bio.seek(0)
    return bio


class Ambient:
    def __init__(self, kind="noise", pitch=220.0, speed=1.0, volume=0.3, fade_ms=200):
        self.kind = kind
        self.pitch = pitch
        self.speed = speed
        self.volume = max(0.0, min(1.0, float(volume)))
        self.fade_ms = int(fade_ms)
        self._sound = None
        self._ok = False
        self._playing = False
        self._tried = False     # mixer init + synth deferred until first start()

    # ---- lifecycle ---------------------------------------------------------
    def _ensure(self):
        if self._tried:
            return self._ok
        self._tried = True
        if pygame is None or os.environ.get("SDL_AUDIODRIVER") == "dummy":
            return False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=_SR, channels=1)
            self._sound = pygame.mixer.Sound(file=_synth_wav(self.kind, self.pitch, self.speed))
            self._sound.set_volume(self.volume)
            self._ok = True
        except Exception:
            self._ok = False
        return self._ok

    def start(self):
        if self._playing:
            return
        if not self._ensure():
            return
        try:
            self._sound.play(loops=-1, fade_ms=self.fade_ms)
            self._playing = True
        except Exception:
            pass

    def stop(self):
        if not self._playing or not self._ok:
            self._playing = False
            return
        try:
            self._sound.fadeout(max(1, self.fade_ms // 2))
        except Exception:
            pass
        self._playing = False

    def set_volume(self, volume):
        self.volume = max(0.0, min(1.0, float(volume)))
        if self._sound is not None:
            try:
                self._sound.set_volume(self.volume)
            except Exception:
                pass

    def close(self):
        self.stop()
