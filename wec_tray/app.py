"""Tray icon + detail window front end (Windows; works with any pystray backend).

Threads: Tk owns the main thread, pystray runs its own message loop
(run_detached), and a worker thread does the network refreshes. Anything that
touches Tk is posted to `ui_queue` and run from the Tk loop.
"""

from __future__ import annotations

import copy
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pystray

from . import core
from .icon import make_icon
from .window import DetailWindow

SITE_URL = core.CALENDAR_URL
APP_NAME = "Windows WEC"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "WindowsWEC"
BACKGROUND_FLAG = "--background"


# ------------------------------------------------------------------- cache

def _data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / "windows-wec"


def _cache_path() -> Path:
    return _data_dir() / "cache.json"


def _settings_path() -> Path:
    return _data_dir() / "settings.json"


def _races_to_json(races: list[core.Race]) -> list[dict]:
    return [
        {
            "name": r.name, "date": r.date, "slug": r.slug, "country": r.country,
            "venue": r.venue, "location": r.location,
            "sessions": [{"name": s.name, "start": s.start.isoformat(), "status": s.status}
                         for s in r.sessions],
        }
        for r in races
    ]


def _races_from_json(data: list[dict]) -> list[core.Race]:
    races = []
    for r in data:
        sessions = []
        for s in r.get("sessions", []):
            start = core._parse_iso(s.get("start", ""))
            if start is not None:
                sessions.append(core.Session(s.get("name", ""), start, s.get("status", "")))
        races.append(core.Race(r["name"], r["date"], r.get("slug", ""), sessions,
                               r.get("country", ""), r.get("venue", ""), r.get("location", "")))
    return races


def load_cache() -> tuple[list[core.Race], float]:
    try:
        raw = json.loads(_cache_path().read_text(encoding="utf-8"))
        races = _races_from_json(raw["races"])
        if races:
            return races, float(raw.get("updated", 0))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return core.fallback_races(), 0.0


def save_cache(races: list[core.Race], updated: float) -> None:
    try:
        path = _cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"updated": updated, "races": _races_to_json(races)}),
                        encoding="utf-8")
    except OSError:
        pass  # the cache is best-effort


def load_settings() -> dict:
    try:
        data = json.loads(_settings_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    try:
        path = _settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings), encoding="utf-8")
    except OSError:
        pass


# ----------------------------------------------------------------- startup

def _startup_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {BACKGROUND_FLAG}'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else exe}" -m wec_tray {BACKGROUND_FLAG}'


def startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_VALUE)
        return True
    except OSError:
        return False


def set_startup(enabled: bool) -> None:
    if sys.platform != "win32":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE)
            except OSError:
                pass


# ------------------------------------------------------------ win32 helpers

def _enable_dpi_awareness() -> None:
    """Keep the Tk window sharp on scaled displays. Must run before Tk starts."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _already_running() -> bool:
    """True if another Windows WEC holds the per-user mutex (Windows only)."""
    if sys.platform != "win32":
        return False
    import ctypes
    kernel32 = ctypes.windll.kernel32
    # The handle is intentionally never closed: it lives as long as the process.
    _already_running.handle = kernel32.CreateMutexW(None, False, "Local\\WindowsWEC")
    return kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS


# --------------------------------------------------------------------- app

class WecApp:
    def __init__(self, show_window: bool = True) -> None:
        self.races, self.updated = load_cache()
        self.settings = load_settings()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.force = False
        self._badge: tuple[str, str] | None = None
        self._show_on_start = show_window

        _enable_dpi_awareness()
        self.root = tk.Tk()
        self.root.withdraw()
        self.ui_queue: queue.Queue[Callable[[], None]] = queue.Queue()
        self.window = DetailWindow(self.root, self)

        text, state = self._current_badge()
        self.icon = pystray.Icon("windows-wec", make_icon(text, state), APP_NAME,
                                 menu=self._build_menu())

    # -- shared state (any thread)
    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def snapshot(self) -> tuple[list[core.Race], float]:
        with self.lock:
            return copy.deepcopy(self.races), self.updated

    def _current_badge(self) -> tuple[str, str]:
        with self.lock:
            return core.icon_badge(self.races, self._now())

    def _status(self) -> str:
        with self.lock:
            return core.tooltip(self.races, self._now())

    def updated_text(self) -> str:
        if not self.updated:
            return "built-in schedule (not yet updated)"
        return "updated " + datetime.fromtimestamp(self.updated).strftime("%d %b, %H:%M")

    def call_ui(self, fn: Callable[[], None]) -> None:
        """Run `fn` on the Tk thread."""
        self.ui_queue.put(fn)

    # -- actions
    def open_window(self, *_a) -> None:
        self.call_ui(self.window.show)

    def refresh_now(self, *_a) -> None:
        self.force = True
        self.wake.set()

    def _open_site(self, *_a) -> None:
        webbrowser.open(SITE_URL)

    def startup_enabled(self) -> bool:
        return startup_enabled()

    def toggle_startup(self, *_a) -> None:
        try:
            set_startup(not startup_enabled())
        except OSError:
            pass
        self.call_ui(self.window.refresh)

    def toggle_setting(self, key: str) -> None:
        self.settings[key] = not self.settings.get(key, True)
        save_settings(self.settings)

    def quit(self, *_a) -> None:
        self.stop.set()
        self.wake.set()
        self.icon.stop()
        self.call_ui(self.root.quit)

    def _build_menu(self) -> pystray.Menu:
        item = pystray.MenuItem
        items = [
            item(lambda _i: self._status(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            item("Open WEC window", self.open_window, default=True),
            item("Refresh now", self.refresh_now),
            item("Open fiawec.com", self._open_site),
        ]
        if sys.platform == "win32":
            items += [
                pystray.Menu.SEPARATOR,
                item("Start with Windows", self.toggle_startup,
                     checked=lambda _i: startup_enabled()),
            ]
        items += [pystray.Menu.SEPARATOR, item("Quit", self.quit)]
        return pystray.Menu(*items)

    # -- network refresh (worker thread)
    def _refresh_calendar(self) -> None:
        html = core.fetch(core.CALENDAR_URL)
        parsed = core.parse_calendar(html) if html else []
        if not parsed:
            return
        with self.lock:
            # Keep weekend details already fetched for races still on the calendar.
            known = {r.slug: r for r in self.races if r.slug}
            for race in parsed:
                old = known.get(race.slug)
                if old is not None:
                    race.sessions, race.venue, race.location = old.sessions, old.venue, old.location
            self.races = parsed
            self.updated = time.time()
            snapshot = list(self.races)
        save_cache(snapshot, self.updated)

    def _refresh_weekend(self) -> None:
        with self.lock:
            race = core.next_race(self.races, self._now())
            slug = race.slug if race else ""
            race_copy = core.Race(race.name, race.date, race.slug) if race else None
        if not slug or race_copy is None:
            return
        html = core.fetch(core.RACE_URL + slug)
        if not html:
            return
        sessions = core.parse_weekend(html, race_copy)
        venue, location = core.parse_venue(html)
        with self.lock:
            for r in self.races:
                if r.slug == slug:
                    if sessions:
                        r.sessions = sessions
                    if venue:
                        r.venue, r.location = venue, location
            snapshot = list(self.races)
        save_cache(snapshot, self.updated)

    def _update_tray(self) -> None:
        # Windows truncates tooltips at 127 characters.
        self.icon.title = self._status()[:127]
        badge = self._current_badge()
        if badge != self._badge:
            self.icon.icon = make_icon(*badge)
            self._badge = badge
        self.icon.update_menu()

    def _worker(self) -> None:
        last_calendar = last_weekend = 0.0
        last_slug = ""
        while not self.stop.is_set():
            now = time.time()
            forced, self.force = self.force, False
            if forced or now - last_calendar >= 3600:
                self._refresh_calendar()
                last_calendar = time.time()
            with self.lock:
                race = core.next_race(self.races, self._now())
                interval = core.weekend_refresh_interval_s(self.races, self._now())
                slug = race.slug if race else ""
            if forced or slug != last_slug or now - last_weekend >= interval:
                self._refresh_weekend()
                last_weekend, last_slug = time.time(), slug
            self._update_tray()
            self.call_ui(self.window.refresh)
            self.wake.wait(60)
            self.wake.clear()

    # -- Tk loop (main thread)
    def _pump(self) -> None:
        while True:
            try:
                fn = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except tk.TclError:
                pass  # window already gone during shutdown
        if not self.stop.is_set():
            self.root.after(100, self._pump)

    def run(self) -> None:
        threading.Thread(target=self._worker, daemon=True, name="wec-refresh").start()
        self.icon.run_detached()
        if self._show_on_start:
            self.root.after(0, self.window.show)
        self.root.after(100, self._pump)
        self.root.mainloop()
        if not self.stop.is_set():
            self.quit()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if _already_running():
        return
    WecApp(show_window=BACKGROUND_FLAG not in args).run()
