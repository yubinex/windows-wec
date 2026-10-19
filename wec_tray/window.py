"""Detail window: the Windows take on omarchy-wec's panel, built with tkinter.

Everything here runs on the Tk thread. The window only reads the app's latest
data snapshot; opening it never triggers a network request.
"""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PIL import Image, ImageTk

from . import core
from .icon import make_icon

if TYPE_CHECKING:
    from .app import WecApp

BG = "#0d0d0f"
FG = "#ececec"
DIM = "#8b8b90"
LINE = "#2a2a2e"
ACTIVE = "#2a2a2f"
RED = "#e10600"
AMBER = "#e0b84f"
WIDTH = 540  # logical pixels, scaled for DPI
TICK_MS = 30_000  # countdown refresh while the window is open
# Twemoji flag PNGs (CC-BY 4.0). Windows has no emoji flag glyphs, and Tk
# cannot draw colour fonts, so flags are images rather than text.
FLAG_DIR = Path(__file__).with_name("flags")


def _fmt_dt(dt: datetime) -> str:
    local = dt.astimezone()
    return f"{local:%a} {local.day} {local:%b} · {local:%H:%M}"


def _fmt_date(iso: str) -> str:
    y, m, d = (int(p) for p in iso.split("-"))
    return f"{d} {datetime(y, m, d):%b %Y}"


def session_status(s: core.Session, now: datetime) -> str:
    """DONE, LIVE, or a short marker ("3h", "45m") within 48 hours, like the panel."""
    if s.status == core.COMPLETED:
        return "DONE"
    if now >= s.start:
        return "LIVE"
    minutes = -(-int((s.start - now).total_seconds()) // 60)
    if minutes > 48 * 60:
        return ""
    if minutes >= 60:
        return f"{-(-minutes // 60)}h"
    return f"{minutes}m"


def _dark_title_bar(win: tk.Misc) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
        value = ctypes.c_int(1)
        # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 10 20H1+ and 11)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
    except Exception:
        pass


def _work_area(win: tk.Misc) -> tuple[int, int, int, int]:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            rect = wintypes.RECT()
            # SPI_GETWORKAREA: the primary screen minus the taskbar
            if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
    return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()


class DetailWindow:
    def __init__(self, root: tk.Tk, app: "WecApp") -> None:
        self.root, self.app = root, app
        self.scale = root.winfo_fpixels("1i") / 96
        self.tab = "weekend"
        self.expanded: dict[str, bool] = {}
        self._tick_job: str | None = None
        self._placed = False
        self._flags: dict[tuple[str, int], ImageTk.PhotoImage | None] = {}
        self._last_key: tuple | None = None

        families = set(tkfont.families(root))
        family = next((f for f in ("Cascadia Mono", "Consolas") if f in families), "Courier New")
        self.fonts = {
            "hero": (family, 15, "bold"),
            "title": (family, 13, "bold"),
            "body": (family, 10),
            "bold": (family, 10, "bold"),
            "small": (family, 9),
            "caption": (family, 8, "bold"),
        }

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.title("WEC")
        self.win.configure(bg=BG)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self.win.bind("<Escape>", lambda _e: self.hide())
        self._icon_img = ImageTk.PhotoImage(make_icon("WEC", "idle"))
        self.win.iconphoto(False, self._icon_img)
        self.body = tk.Frame(self.win, bg=BG, padx=self.px(20), pady=self.px(18))
        self.body.pack(fill="both", expand=True)

    # ------------------------------------------------------------ visibility

    def px(self, n: float) -> int:
        return int(round(n * self.scale))

    @property
    def visible(self) -> bool:
        return self.win.winfo_exists() and self.win.state() == "normal"

    def show(self) -> None:
        self.render()
        if not self._placed:
            self._place()
            self._placed = True
        self.win.deiconify()
        _dark_title_bar(self.win)
        # Bring it in front of the taskbar flyouts without staying on top.
        self.win.attributes("-topmost", True)
        self.win.lift()
        self.win.focus_force()
        self.win.after(300, lambda: self.win.attributes("-topmost", False))
        self._schedule_tick()

    def hide(self) -> None:
        self.win.withdraw()
        if self._tick_job:
            self.win.after_cancel(self._tick_job)
            self._tick_job = None

    def toggle(self) -> None:
        self.hide() if self.visible else self.show()

    def refresh(self) -> None:
        """Re-render if open (called after new data arrives)."""
        if self.visible:
            self.render()

    def _schedule_tick(self) -> None:
        if self._tick_job:
            self.win.after_cancel(self._tick_job)
        self._tick_job = self.win.after(TICK_MS, self._tick)

    def _tick(self) -> None:
        self._tick_job = None
        if self.visible:
            self.render()
            self._schedule_tick()

    def _place(self) -> None:
        """Open above the notification area, like a tray flyout."""
        self.win.update_idletasks()
        left, top, right, bottom = _work_area(self.win)
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        margin, title_bar = self.px(12), self.px(32)
        x = max(left, right - w - margin)
        y = max(top, bottom - h - title_bar - margin)
        self.win.geometry(f"+{x}+{y}")

    def _keep_on_screen(self) -> None:
        if not self.visible:
            return
        self.win.update_idletasks()
        _left, top, _right, bottom = _work_area(self.win)
        margin = self.px(12)
        overflow = self.win.winfo_rooty() + self.win.winfo_reqheight() - (bottom - margin)
        if overflow > 0:
            y = max(top, self.win.winfo_y() - overflow)
            self.win.geometry(f"+{self.win.winfo_x()}+{y}")

    # --------------------------------------------------------------- widgets

    def frame(self, parent: tk.Misc, **kw) -> tk.Frame:
        return tk.Frame(parent, bg=BG, **kw)

    def label(self, parent: tk.Misc, text: str, font: str = "body", fg: str = FG, **kw) -> tk.Label:
        kw.setdefault("bg", BG)
        return tk.Label(parent, text=text, font=self.fonts[font], fg=fg, **kw)

    def separator(self, pady: int = 12) -> None:
        tk.Frame(self.body, bg=LINE, height=1).pack(fill="x", pady=self.px(pady))

    def chip(self, parent: tk.Misc, text: str, active: bool = False,
             command: Callable[[], None] | None = None) -> tk.Label:
        border = FG if active else DIM
        chip = tk.Label(
            parent, text=text, font=self.fonts["caption"], fg=FG if active else DIM,
            bg=ACTIVE if active else BG, padx=self.px(9), pady=self.px(4),
            highlightthickness=1, highlightbackground=border, highlightcolor=border)
        if command is not None:
            chip.configure(cursor="hand2")
            chip.bind("<Button-1>", lambda _e: command())
        return chip

    def link(self, parent: tk.Misc, text: str, url: str) -> tk.Label:
        lbl = self.label(parent, text, "caption", cursor="hand2")
        lbl.bind("<Button-1>", lambda _e: webbrowser.open(url))
        return lbl

    def flag(self, parent: tk.Misc, code: str, size: int) -> tk.Label | None:
        """A flag image label, or None if flags are off or there is no image for `code`."""
        if not code or not self.app.settings.get("show_flags", True):
            return None
        key = (code, self.px(size))
        if key not in self._flags:
            try:
                img = Image.open(FLAG_DIR / f"{code.upper()}.png").convert("RGBA")
                img = img.resize((key[1], key[1]), Image.LANCZOS)
                self._flags[key] = ImageTk.PhotoImage(img, master=self.win)
            except (OSError, ValueError):
                self._flags[key] = None
        img = self._flags[key]
        return tk.Label(parent, image=img, bg=BG, bd=0) if img else None

    @staticmethod
    def _bind_tree(widget: tk.Misc, callback: Callable[[], None]) -> None:
        widget.bind("<Button-1>", lambda _e: callback())
        widget.configure(cursor="hand2")
        for child in widget.winfo_children():
            DetailWindow._bind_tree(child, callback)

    def _set_tab(self, tab: str) -> None:
        self.tab = tab
        self.render()

    # --------------------------------------------------------------- render

    def render(self) -> None:
        races, updated = self.app.snapshot()
        now = datetime.now(timezone.utc)
        # Everything the view depends on. Countdowns change at most once a minute,
        # so ticks and data refreshes that change nothing visible are skipped.
        key = (now.strftime("%Y%m%d%H%M"), repr(races), updated, self.tab,
               sorted(self.expanded.items()), sorted(self.app.settings.items()),
               self.app.startup_enabled() if self.tab == "settings" else None)
        if key == self._last_key and self.body.winfo_ismapped():
            return
        self._last_key = key

        # Build into a fresh frame and swap it in within the same event, so the
        # window never shows a half-built or empty state (no flicker).
        old = self.body
        self.body = tk.Frame(self.win, bg=BG, padx=self.px(20), pady=self.px(18))
        # Fixes the window width; labels are short enough not to need eliding.
        tk.Frame(self.body, bg=BG, width=self.px(WIDTH), height=0).pack()

        race = core.next_race(races, now)

        self._render_header(races, race, now)
        tabs = self.frame(self.body)
        tabs.pack(fill="x", pady=(self.px(14), self.px(12)))
        for key, text in (("weekend", "RACE WEEKEND"), ("settings", "SETTINGS")):
            self.chip(tabs, text, self.tab == key, lambda k=key: self._set_tab(k)) \
                .pack(side="left", padx=(0, self.px(8)))
        # Standings are not scraped; the official tables are one click away.
        self.chip(tabs, "STANDINGS ↗", command=lambda: webbrowser.open(core.STANDINGS_URL)) \
            .pack(side="right")

        if self.tab == "settings":
            self._render_settings()
        else:
            self._render_weekend(races, race, now)
        old.destroy()
        self.body.pack(fill="both", expand=True)
        self._keep_on_screen()

    def _render_header(self, races: list[core.Race], race: core.Race | None,
                       now: datetime) -> None:
        top = self.frame(self.body)
        top.pack(fill="x")
        if race is None:
            self.label(top, "FIA WORLD ENDURANCE CHAMPIONSHIP", "hero").pack(anchor="w")
            self.label(top, "No upcoming race on the calendar", fg=DIM).pack(anchor="w")
            return
        hero_flag = self.flag(top, race.country, 34)
        if hero_flag is not None:
            hero_flag.pack(side="left", anchor="n", padx=(0, self.px(12)))
        elif race.country:
            self.chip(top, race.country).pack(side="left", anchor="n", padx=(0, self.px(12)),
                                              pady=(self.px(3), 0))
        rnd = core.round_number(races, race)
        if rnd:
            self.label(top, f"ROUND {rnd}", "caption", DIM).pack(side="right", anchor="n",
                                                                 pady=(self.px(4), 0))
        col = self.frame(top)
        col.pack(side="left", fill="x", expand=True)
        self.label(col, race.name.upper(), "hero").pack(anchor="w")
        sub = " · ".join(p for p in (race.venue, race.location) if p)
        self.label(col, sub or core.display_date(race.date), fg=DIM).pack(anchor="w")

        tk.Frame(self.body, bg=LINE, height=1).pack(fill="x", pady=self.px(12))

        grid = self.frame(self.body)
        grid.pack(fill="x")
        grid.columnconfigure((0, 1), weight=1, uniform="half")
        ns = core.next_session(race, now)
        left, right = self.frame(grid), self.frame(grid)
        left.grid(row=0, column=0, sticky="nw")
        right.grid(row=0, column=1, sticky="nw")

        self.label(left, "NEXT ON TRACK", "caption", DIM).pack(anchor="w")
        if ns is not None:
            self.label(left, ns.session.name, "bold").pack(anchor="w")
            when = "LIVE NOW" if ns.live else _fmt_dt(ns.session.start)
            self.label(left, when, "small", RED if ns.live else DIM).pack(anchor="w")
        else:
            self.label(left, "Timetable not published", "bold").pack(anchor="w")
            self.label(left, "Check back closer to the weekend", "small", DIM).pack(anchor="w")

        start = core.race_start(race)
        countdown = core.race_countdown(race, now)
        countdown = {"live": "race live", "today": "race day"}.get(countdown, "race " + countdown)
        self.label(right, "RACE START", "caption", DIM).pack(anchor="w")
        self.label(right, _fmt_dt(start) if start else core.display_date(race.date),
                   "bold").pack(anchor="w")
        live = ns is not None and ns.live
        self.label(right, countdown.upper(), "caption", RED if live else DIM).pack(
            anchor="w", pady=(self.px(2), 0))

    def _render_weekend(self, races: list[core.Race], race: core.Race | None,
                        now: datetime) -> None:
        if race is not None:
            self._render_schedule(race, now)
            self.separator()

        self.label(self.body, "UPCOMING RACES", "caption", DIM).pack(anchor="w",
                                                                    pady=(0, self.px(6)))
        idx = races.index(race) + 1 if race in races else 0
        previous = race
        for r in races[idx: idx + 3]:
            if previous is not None and r.date[:4] != previous.date[:4]:
                self.label(self.body, f"{r.date[:4]} SEASON", "caption", DIM).pack(
                    anchor="w", pady=(self.px(6), self.px(2)))
            row = self.frame(self.body)
            row.pack(fill="x", pady=self.px(3))
            self.label(row, _fmt_date(r.date), fg=DIM, width=12, anchor="w").pack(side="left")
            row_flag = self.flag(row, r.country, 20)
            if row_flag is not None:
                row_flag.pack(side="left", padx=(0, self.px(12)))
            else:
                self.label(row, r.country, "caption", DIM, width=4, anchor="w").pack(side="left")
            self.label(row, r.name, anchor="w").pack(side="left")
            previous = r

        self.separator()
        foot = self.frame(self.body)
        foot.pack(fill="x")
        self.label(foot, "Official FIA WEC calendar · " + self.app.updated_text(), "small",
                   DIM).pack(side="left")
        self.link(foot, "OPEN FIA WEC ↗", core.CALENDAR_URL).pack(side="right")

    def _render_schedule(self, race: core.Race, now: datetime) -> None:
        self.label(self.body, "WEEKEND SCHEDULE", "caption", DIM).pack(anchor="w")
        sessions = race.sessions
        if not self.app.settings.get("show_completed", True):
            sessions = [s for s in sessions if s.status != core.COMPLETED]
        if not sessions:
            self.label(self.body, "Session times are not published yet.", "small", DIM).pack(
                anchor="w", pady=(self.px(4), 0))
            return
        tz = datetime.now().astimezone().tzname() or "local time"
        self.label(self.body, f"All times in {tz}", "small", DIM).pack(
            anchor="w", pady=(self.px(2), self.px(6)))

        days: dict[str, list[core.Session]] = {}
        for s in sessions:
            days.setdefault(s.start.astimezone().strftime("%Y-%m-%d"), []).append(s)
        ns = core.next_session(race, now)
        featured = ns.session.start.astimezone().strftime("%Y-%m-%d") if ns else ""

        for key, day in days.items():
            expanded = self.expanded.get(key, key == featured)
            local = day[0].start.astimezone()
            count = f"{len(day)} SESSION{'' if len(day) == 1 else 'S'}"
            head = self.frame(self.body)
            head.pack(fill="x", pady=(self.px(4), self.px(2)))
            self.label(head, f"{local:%A} · {local.day} {local:%B} · {count}".upper(),
                       "caption", DIM).pack(side="left")
            self.label(head, "−" if expanded else "+", "bold", DIM).pack(side="right")
            self._bind_tree(head, lambda k=key, e=expanded: self._toggle_day(k, e))
            if expanded:
                for s in day:
                    self._render_session(s, now)

    def _toggle_day(self, key: str, expanded: bool) -> None:
        self.expanded[key] = not expanded
        self.render()

    def _render_session(self, s: core.Session, now: datetime) -> None:
        status = session_status(s, now)
        done, live, is_race = status == "DONE", status == "LIVE", s.name == "Race"
        soon = not live and not done and s.start - now <= timedelta(hours=2)
        row = self.frame(self.body)
        row.pack(fill="x", pady=self.px(1))
        strong = (is_race or live) and not done
        self.label(row, s.start.astimezone().strftime("%H:%M"), "bold" if strong else "body",
                   DIM if done or not strong else FG, width=7, anchor="e").pack(side="left")
        dot = RED if live else (FG if is_race and not done else LINE if done else DIM)
        self.label(row, "●", "small", dot).pack(side="left", padx=(self.px(10), self.px(10)))
        self.label(row, s.name, "bold" if is_race else "body", DIM if done else FG,
                   anchor="w").pack(side="left")
        if status and not done:
            color = RED if live else AMBER if soon else DIM
            self.label(row, status, "caption", color).pack(side="right")

    def _render_settings(self) -> None:
        def toggle_row(title: str, desc: str, on: bool, command: Callable[[], None]) -> None:
            row = self.frame(self.body)
            row.pack(fill="x", pady=(self.px(8), 0))
            self.chip(row, " ON" if on else "OFF", on, command).pack(side="right", anchor="n")
            self.label(row, title, "bold").pack(anchor="w")
            self.label(row, desc, "small", DIM).pack(anchor="w")

        toggle_row("SHOW RACE FLAGS", "Display event-country flags in the weekend view.",
                   self.app.settings.get("show_flags", True),
                   lambda: self._settings_changed(self.app.toggle_setting, "show_flags"))
        toggle_row("SHOW COMPLETED SESSIONS",
                   "Keep finished practice and qualifying in the schedule.",
                   self.app.settings.get("show_completed", True),
                   lambda: self._settings_changed(self.app.toggle_setting, "show_completed"))
        if sys.platform == "win32":
            toggle_row("START WITH WINDOWS", "Launch quietly in the tray when you sign in.",
                       self.app.startup_enabled(),
                       lambda: self._settings_changed(self.app.toggle_startup))

        self.separator()
        row = self.frame(self.body)
        row.pack(fill="x")
        self.chip(row, "REFRESH NOW", command=self.app.refresh_now).pack(side="right")
        self.label(row, "CALENDAR", "bold").pack(anchor="w")
        self.label(row, self.app.updated_text(), "small", DIM).pack(anchor="w")

        row = self.frame(self.body)
        row.pack(fill="x", pady=(self.px(12), 0))
        self.chip(row, "QUIT", command=self.app.quit).pack(side="right")
        self.label(row, "WINDOWS WEC", "bold").pack(anchor="w")
        self.label(row, "Closing this window keeps it running in the tray.", "small",
                   DIM).pack(anchor="w")

    def _settings_changed(self, fn: Callable[..., None], *args) -> None:
        fn(*args)
        self.render()
