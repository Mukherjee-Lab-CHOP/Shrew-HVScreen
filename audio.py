"""Ambient — host-side looping background sound (computer / attached speaker).

Used to play a constant ambient hiss while an experiment waits for the shrew to
initiate at the centre port. It is intentionally independent of the Arduino
buzzer (Tone) — this comes out of the computer's audio device via pygame.mixer.

Everything is best-effort: if pygame / the mixer / the audio file is unavailable
(e.g. a head-less machine or SDL_AUDIODRIVER=dummy), every method is a safe
no-op and the experiment runs silently.

    amb = Ambient(path, volume=0.3)
    amb.start()    # begin looping (idempotent)
    amb.stop()     # fade out / stop (idempotent)
    amb.close()
"""

import os

try:
    import pygame
except ImportError:                      # pygame optional -> silent
    pygame = None


class Ambient:
    def __init__(self, path, volume=0.3, fade_ms=200):
        self.path = path
        self.volume = max(0.0, min(1.0, float(volume)))
        self.fade_ms = int(fade_ms)
        self._sound = None
        self._ok = False
        self._playing = False
        self._tried = False     # mixer init is deferred until the first start()

    # ---- lifecycle ---------------------------------------------------------
    def _ensure(self):
        """Lazily init the mixer + load the sound the first time we play, so just
        constructing an experiment (e.g. in tests) never touches the audio device."""
        if self._tried:
            return self._ok
        self._tried = True
        if pygame is None or os.environ.get("SDL_AUDIODRIVER") == "dummy":
            return False
        if not self.path or not os.path.exists(self.path):
            return False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            self._sound = pygame.mixer.Sound(self.path)
            self._sound.set_volume(self.volume)
            self._ok = True
        except Exception:
            self._ok = False
        return self._ok

    def start(self):
        """Begin (or keep) looping the ambient sound."""
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
