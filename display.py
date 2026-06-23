"""Display — the pygame stimulus screen.

This is the rendering half of the original screen.py, refactored into a class
the experiment drives directly (instead of over a serial SHOW/BLACK/CHOICE
protocol). It keeps the same behaviour: two figures side by side, a fig3
overlay highlighting the chosen side for `highlight_ms`, fullscreen with
Windows multi-monitor support, and ESC to quit.

CSV logging has moved out of here and into experiment.py, since the experiment
now owns the authoritative trial data.

The experiment calls:
    display.start()
    display.show(left_fig, right_fig)   # FIG codes 1/2
    display.choice("LEFT" | "RIGHT")    # overlay fig3 on the chosen side
    display.black()
    display.update()                    # pump every loop; returns False on ESC/quit
    display.close()

If pygame is missing or `enabled=False`, every method is a safe no-op and the
experiment still runs from the terminal (stimulus side is printed there).
"""

import ctypes
import os
import sys

try:
    import pygame
except ImportError:
    pygame = None

from config import ORIENT_HORIZONTAL, DEFAULT_HIGHLIGHT_MS


def _info(msg):
    print(f"[display] {msg}", flush=True)


def _windows_display_geometries():
    """Return [(left, top, w, h), ...] for each monitor on Windows, else []."""
    if not sys.platform.startswith("win"):
        return []
    try:
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        monitors = []

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
            ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

        def _cb(hMonitor, hdc, lprc, data):
            r = lprc.contents
            monitors.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
            return True

        if not user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0):
            return []
        return monitors
    except Exception:
        return []


class Display:
    def __init__(self, fig1="fig1.png", fig2="fig2.png", fig3="fig3.png",
                 fig_incorrect=None, screen_index=None, windowed=False,
                 highlight_ms=DEFAULT_HIGHLIGHT_MS, enabled=True):
        # screen_index None = auto (prefer external/HDMI display, else primary).
        self.fig1_path = fig1
        self.fig2_path = fig2
        self.fig3_path = fig3
        self.fig_incorrect_path = fig_incorrect
        self.screen_index = screen_index
        self.windowed = windowed
        self.highlight_ms = highlight_ms
        self.enabled = enabled and (pygame is not None)
        if enabled and pygame is None:
            _info("pygame not installed -> display disabled (terminal-only).")

        self._screen = None
        self._fig = {}
        self._fig3 = None
        self._fig_incorrect = None
        self._cur_l = None
        self._cur_r = None
        self._overlay_side = None       # "L" / "R" / None
        self._overlay_until = 0
        self._pending_black = False

    # ---- setup --------------------------------------------------------------
    def start(self):
        """Open the window and load assets. Disables itself on any failure so
        the experiment can keep running from the terminal."""
        if not self.enabled:
            return False
        try:
            self._open_window()
            self._fig[1] = self._load(self.fig1_path)
            self._fig[2] = self._load(self.fig2_path)
            self._fig3 = self._load(self.fig3_path)
            if self.fig_incorrect_path:
                try:
                    self._fig_incorrect = self._load(self.fig_incorrect_path)
                except Exception:
                    self._fig_incorrect = None
            self._set_black()
            return True
        except Exception as e:
            _info(f"could not start display ({e}) -> disabled (terminal-only).")
            self.enabled = False
            try:
                if pygame.get_init():
                    pygame.quit()
            except Exception:
                pass
            return False

    def _open_window(self):
        pygame.init()
        pygame.display.init()

        # How many monitors are there?
        sizes = []
        if hasattr(pygame.display, "get_desktop_sizes"):
            sizes = pygame.display.get_desktop_sizes()
        ndisp = max(len(sizes), 1)

        # Resolve the target monitor. screen_index None = "auto": prefer the
        # external/HDMI screen (index 1) when present, else fall back to 0.
        if self.screen_index is None:
            self.screen_index = 1 if ndisp >= 2 else 0
            _info(f"auto-selected display {self.screen_index} of {ndisp}"
                  + ("" if ndisp >= 2 else " (no external display; using primary)"))
        elif self.screen_index >= ndisp:
            _info(f"display {self.screen_index} not present ({ndisp} detected); "
                  f"falling back to 0.")
            self.screen_index = 0

        rects = _windows_display_geometries()
        rect = rects[self.screen_index] if 0 <= self.screen_index < len(rects) else None

        if rect is not None and not self.windowed:
            left, top, w, h = rect
            os.environ["SDL_VIDEO_WINDOW_POS"] = f"{left},{top}"
            self._screen = pygame.display.set_mode((w, h), pygame.NOFRAME)
            _info(f"borderless window at {left},{top} {w}x{h}")
        elif self.windowed:
            self._screen = pygame.display.set_mode((1280, 720))
            _info("windowed 1280x720")
        else:
            size = sizes[self.screen_index] if 0 <= self.screen_index < len(sizes) else (0, 0)
            self._screen = pygame.display.set_mode(size, pygame.FULLSCREEN,
                                                   display=self.screen_index)
            _info(f"fullscreen on display {self.screen_index} {size}")
        pygame.display.set_caption("CHOP Task Screen")
        pygame.mouse.set_visible(False)

    def _load(self, path):
        resolved = path
        if not os.path.isabs(path) and not os.path.exists(path):
            here = os.path.dirname(os.path.abspath(__file__))
            cand = os.path.join(here, path)
            if os.path.exists(cand):
                resolved = cand
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"missing image: {path}")
        return pygame.image.load(resolved).convert_alpha()

    # ---- commands -----------------------------------------------------------
    def show(self, left_fig, right_fig):
        if not self.enabled:
            return
        self._cur_l = self._fig.get(left_fig)
        self._cur_r = self._fig.get(right_fig)
        self._overlay_side = None
        self._pending_black = False
        self._render(self._cur_l, self._cur_r)

    def choice(self, side, correct=True):
        if not self.enabled:
            return
        self._overlay_side = "L" if str(side).upper() == "LEFT" else "R"
        overlay = self._fig3 if correct else (self._fig_incorrect or self._fig3)
        self._overlay_until = pygame.time.get_ticks() + self.highlight_ms
        self._render(self._cur_l, self._cur_r, overlay, self._overlay_side)

    def black(self):
        if not self.enabled:
            return
        # If an overlay is up, defer going black until it expires (matches the
        # original pending_black behaviour).
        if self._overlay_side:
            self._pending_black = True
        else:
            self._set_black()
            self._cur_l = self._cur_r = None

    def update(self):
        """Pump events + manage overlay timing. Returns False on ESC / window close."""
        if not self.enabled:
            return True
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False

        now = pygame.time.get_ticks()
        if self._overlay_side and now >= self._overlay_until:
            self._overlay_side = None
            if self._pending_black:
                self._set_black()
                self._pending_black = False
                self._cur_l = self._cur_r = None
            elif self._cur_l is not None and self._cur_r is not None:
                self._render(self._cur_l, self._cur_r)
        return True

    def close(self):
        if self.enabled:
            try:
                pygame.quit()
            except Exception:
                pass

    # ---- rendering ----------------------------------------------------------
    def _set_black(self):
        self._screen.fill((0, 0, 0))
        pygame.display.flip()

    def _render(self, img_left, img_right, overlay=None, overlay_side=None):
        # A side whose image is None stays blank; only when BOTH are None is the
        # whole screen black.
        if img_left is None and img_right is None:
            self._set_black()
            return
        sw, sh = self._screen.get_size()
        self._screen.fill((0, 0, 0))

        gap = int(sw * 0.04)
        half_w = (sw - gap) // 2
        max_h = int(sh * 0.9)
        cy = sh // 2

        def fit(img):
            iw, ih = img.get_size()
            scale = min(half_w / iw, max_h / ih)
            return pygame.transform.smoothscale(img, (int(iw * scale), int(ih * scale)))

        if img_left is not None:
            left_scaled = fit(img_left)
            left_rect = left_scaled.get_rect(center=(half_w // 2, cy))
            self._screen.blit(left_scaled, left_rect)
            if overlay is not None and overlay_side == "L":
                ov = pygame.transform.smoothscale(overlay, left_scaled.get_size())
                self._screen.blit(ov, left_rect)

        if img_right is not None:
            right_scaled = fit(img_right)
            right_rect = right_scaled.get_rect(center=(half_w + gap + half_w // 2, cy))
            self._screen.blit(right_scaled, right_rect)
            if overlay is not None and overlay_side == "R":
                ov = pygame.transform.smoothscale(overlay, right_scaled.get_size())
                self._screen.blit(ov, right_rect)

        pygame.display.flip()
