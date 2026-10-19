"""Calendar scraping and countdown logic for the WEC tray app.

This is a Python port of the logic in omarchy-wec's BarWidget.qml. It has no
GUI or Windows-specific dependencies, so it can be tested anywhere.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

BASE_URL = "https://www.fiawec.com"
CALENDAR_URL = BASE_URL + "/en/"
RACE_URL = BASE_URL + "/en/race/"
STANDINGS_URL = BASE_URL + "/en/page/manufacturers-classification"
MAX_BYTES = 1024 * 1024  # same 1 MiB bound as the Omarchy plugin
TIMEOUT_S = 15

# Offline fallback, used until the first successful fetch of the official page.
FALLBACK_RACES = [
    ("Lone Star Le Mans", "2026-09-06", "US"),
    ("6 Hours of Fuji", "2026-09-27", "JP"),
    ("6 Hours of Barcelona", "2026-10-18", "ES"),
    ("6 Hours of Monza", "2026-11-08", "IT"),
    ("Qatar 1812km", "2027-03-27", "QA"),
    ("6 Hours of Imola", "2027-04-11", "IT"),
    ("6 Hours of Silverstone", "2027-04-25", "GB"),
    ("6 Hours of Spa-Francorchamps", "2027-05-15", "BE"),
    ("24 Hours of Le Mans", "2027-06-12", "FR"),
    ("Rolex 6 Hours of São Paulo", "2027-07-11", "BR"),
    ("Lone Star Le Mans", "2027-09-12", "US"),
    ("6 Hours of Fuji", "2027-09-26", "JP"),
    ("8 Hours of Bahrain", "2027-11-06", "BH"),
]

SLUG_TITLES = {
    "lone-star-le-mans": "Lone Star Le Mans",
    "6-hours-of-fuji": "6 Hours of Fuji",
    "6-hours-of-barcelona": "6 Hours of Barcelona",
    "6-hours-of-monza": "6 Hours of Monza",
    "qatar-1812km": "Qatar 1812km",
    "6-hours-of-imola": "6 Hours of Imola",
    "6-hours-of-silverstone": "6 Hours of Silverstone",
    "totalenergies-6-hours-of-spa-francorchamps": "TotalEnergies 6 Hours of Spa-Francorchamps",
    "24-hours-of-le-mans": "24 Hours of Le Mans",
    "rolex-6-hours-of-sao-paulo": "Rolex 6 Hours of São Paulo",
    "bapco-energies-8-hours-of-bahrain": "Bapco Energies 8 Hours of Bahrain",
}

MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

COMPLETED = "EventCompleted"


@dataclass
class Session:
    name: str
    start: datetime  # timezone-aware
    status: str = ""

    @property
    def short(self) -> str:
        return session_short(self.name)


@dataclass
class Race:
    name: str
    date: str  # YYYY-MM-DD, as listed on the official calendar
    slug: str = ""
    sessions: list[Session] = field(default_factory=list)
    country: str = ""  # ISO 3166 alpha-2, from the calendar's flag marker
    venue: str = ""  # e.g. "Monza", from the race page
    location: str = ""  # e.g. "Monza, ITA"


# ---------------------------------------------------------------- fetching

def fetch(url: str) -> Optional[str]:
    """Fetch a page over HTTPS with a size and time bound. None on any failure."""
    if not url.startswith("https://"):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "windows-wec (unofficial)"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = resp.read(MAX_BYTES + 1)
    except Exception:
        return None
    if len(data) > MAX_BYTES:
        return None
    return data.decode("utf-8", errors="replace")


# ----------------------------------------------------------------- parsing

def title_from_slug(slug: str) -> str:
    return SLUG_TITLES.get(slug) or slug.replace("-", " ")


_CALENDAR_RE = re.compile(
    r'href="/en/race/([a-z0-9-]+)-(20\d{2})"[\s\S]{0,500}?flag:([A-Z]{2})'
    r'[\s\S]{0,900}?<strong[^>]*>\s*(\d{1,2})\s*</strong>\s*<small[^>]*>\s*([A-Za-z]{3})'
)


def parse_calendar(html: str) -> list[Race]:
    parsed: list[Race] = []
    seen: set[str] = set()
    for m in _CALENDAR_RE.finditer(html):
        base, year, country, day_s, mon_s = m.groups()
        if base.startswith("official-prologue-"):
            continue
        month = MONTHS.get(mon_s)
        if month is None:
            continue
        day = int(day_s)
        if not 1 <= day <= 31:
            continue
        date = f"{year}-{month:02d}-{day:02d}"
        key = f"{base}:{date}"
        # The page lists the calendar in both desktop and mobile navigation.
        if key in seen:
            continue
        seen.add(key)
        parsed.append(Race(name=title_from_slug(base), date=date, slug=f"{base}-{year}",
                           country=country))
    parsed.sort(key=lambda r: r.date)
    return parsed


def _plain_text(html: str) -> str:
    text = re.sub(r"<[^>]*>", " ", str(html))
    text = text.replace("&amp;", "&").replace("&#x27;", "'").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


_LD_JSON_RE = re.compile(
    r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', re.I)


def _strip_suffix(name: str, race_name: str) -> str:
    suffix = " - " + race_name
    return name[: -len(suffix)] if name.endswith(suffix) else name


def _structured_sessions(html: str, race: Race) -> list[Session]:
    for m in _LD_JSON_RE.finditer(html):
        try:
            event = json.loads(m.group(1))
        except ValueError:
            continue
        if not isinstance(event, dict) or not event.get("subEvent") or not event.get("location"):
            continue
        sessions: list[Session] = []
        for sub in event["subEvent"]:
            if not isinstance(sub, dict) or not sub.get("name") or not sub.get("startDate"):
                continue
            start = _parse_iso(sub["startDate"])
            if start is None:
                continue
            status = str(sub.get("eventStatus") or "").split("/")[-1]
            sessions.append(Session(_strip_suffix(sub["name"], race.name), start, status))
        if sessions:
            sessions.sort(key=lambda s: s.start)
            return sessions
    return []


_STATUS_RE = re.compile(
    r'"@id"\s*:\s*"[^"]+#[^"]+",\s*"name"\s*:\s*"([^"]+)"[\s\S]{0,300}?"eventStatus"\s*:\s*"[^"]*/([^"]+)"')
_FALLBACK_SESSION_RE = re.compile(
    r'<div[^>]*class="(?=[^"]*\bfw-bold\b)(?=[^"]*\blh-sm\b)[^"]*"[^>]*>\s*([^<]+)\s*</div>'
    r'[\s\S]{0,800}?data-local="([^"]+)"[^>]*data-timestamp="(\d+)"')


def parse_venue(html: str) -> tuple[str, str]:
    """Return (venue, location) from the race page's event data, or empty strings."""
    for m in _LD_JSON_RE.finditer(html):
        try:
            event = json.loads(m.group(1))
        except ValueError:
            continue
        loc = event.get("location") if isinstance(event, dict) else None
        if not isinstance(loc, dict):
            continue
        address = loc.get("address")
        if isinstance(address, dict):
            parts = (address.get("addressLocality"), address.get("addressCountry"))
            address = ", ".join(str(p) for p in parts if p)
        return str(loc.get("name") or ""), str(address or "")
    return "", ""


def parse_weekend(html: str, race: Race) -> list[Session]:
    """Return the weekend's sessions, sorted by start time (empty if not found)."""
    sessions = _structured_sessions(html, race)
    if sessions:
        return sessions
    statuses = {_strip_suffix(n, race.name): s for n, s in _STATUS_RE.findall(html)}
    for m in _FALLBACK_SESSION_RE.finditer(html):
        name = _plain_text(m.group(1))
        start = datetime.fromtimestamp(int(m.group(3)), tz=timezone.utc)
        sessions.append(Session(name, start, statuses.get(name, "")))
    sessions.sort(key=lambda s: s.start)
    return sessions


# ------------------------------------------------------------------- state

def session_short(name: str) -> str:
    if name == "Race":
        return "RACE"
    if name.startswith("Free Practice"):
        return "FP" + re.sub(r"\D", "", name)
    if name.startswith("Hyperpole"):
        return "HYPER"
    if name.startswith("Qualifying"):
        return "QUAL"
    return name.upper()


def _date_noon_utc(iso: str) -> datetime:
    y, m, d = (int(p) for p in iso.split("-"))
    return datetime(y, m, d, 12, tzinfo=timezone.utc)


def race_end(race: Race) -> datetime:
    """When to advance to the next round (mirrors raceEnd() in the QML)."""
    if race.sessions:
        final = race.sessions[-1]
        # Official status, not a guessed duration, decides when a round is over.
        if final.status != COMPLETED:
            return datetime.max.replace(tzinfo=timezone.utc)
        return final.start
    return _date_noon_utc(race.date) + timedelta(hours=12)


def next_race(races: list[Race], now: datetime) -> Optional[Race]:
    for race in races:
        if race_end(race) >= now:
            return race
    return None


@dataclass
class NextSession:
    session: Session
    live: bool


def next_session(race: Optional[Race], now: datetime) -> Optional[NextSession]:
    if race is None:
        return None
    for s in race.sessions:
        if s.status == COMPLETED:
            continue
        return NextSession(s, live=now >= s.start)
    return None


def race_start(race: Race) -> Optional[datetime]:
    for s in race.sessions:
        if s.name == "Race":
            return s.start
    return None


def calendar_days_until(race: Race, today: datetime) -> int:
    y, m, d = (int(p) for p in race.date.split("-"))
    from datetime import date
    return max(0, (date(y, m, d) - today.date()).days)


def race_countdown(race: Race, now: datetime) -> str:
    start = race_start(race)
    if start is not None:
        remaining = start - now
        if remaining <= timedelta(0):
            return "live"
        if remaining < timedelta(days=1):
            minutes = -(-int(remaining.total_seconds()) // 60)  # ceil
            return f"in {minutes // 60}h {minutes % 60}m"
    days = calendar_days_until(race, now.astimezone())
    if days == 0:
        return "today"
    if days == 1:
        return "in 1 day"
    if days < 14:
        return f"in {days} days"
    weeks, rem = divmod(days, 7)
    out = f"in {weeks} week{'' if weeks == 1 else 's'}"
    if rem:
        out += f", {rem} day{'' if rem == 1 else 's'}"
    return out


def session_countdown(ns: NextSession, now: datetime) -> str:
    if ns.live:
        return "LIVE"
    minutes = max(0, -(-int((ns.session.start - now).total_seconds()) // 60))
    if minutes < 60:
        return f"IN {minutes}M"
    return f"IN {minutes // 60}H {minutes % 60}M"


def display_date(iso: str) -> str:
    d = _date_noon_utc(iso)
    return f"{d:%a} {d.day} {d:%b %Y}"


def tooltip(races: list[Race], now: datetime) -> str:
    race = next_race(races, now)
    if race is None:
        return "No upcoming WEC race"
    ns = next_session(race, now)
    if ns is not None:
        return f"{race.name} · {ns.session.short} {session_countdown(ns, now)}"
    return f"{race.name} · {display_date(race.date)} · {race_countdown(race, now)}"


def is_live(races: list[Race], now: datetime) -> bool:
    ns = next_session(next_race(races, now), now)
    return bool(ns and ns.live)


def icon_badge(races: list[Race], now: datetime) -> tuple[str, str]:
    """Short tray-icon label and state ("live", "soon", "idle" or "none").

    Counts down to the next session when the weekend timetable is known, else
    to the race date: "LIVE", "45m", "5h", "12d", or weeks ("16w") past 99 days.
    """
    race = next_race(races, now)
    if race is None:
        return "", "none"
    ns = next_session(race, now)
    if ns is not None and ns.live:
        return "LIVE", "live"
    if ns is not None:
        minutes = max(0, -(-int((ns.session.start - now).total_seconds()) // 60))
        state = "soon" if minutes <= 120 else "idle"
        if minutes < 60:
            return f"{minutes}m", state
        if minutes < 24 * 60:
            return f"{minutes // 60}h", state
        days = max(1, (ns.session.start.astimezone().date() - now.astimezone().date()).days)
    else:
        days = calendar_days_until(race, now.astimezone())
        if days == 0:
            return "RACE", "soon"
    return (f"{days}d" if days < 100 else f"{days // 7}w"), "idle"


def round_number(races: list[Race], race: Race) -> Optional[int]:
    """1-based round within the race's season, if the full official calendar is known."""
    if not race.slug:
        return None  # the built-in fallback list is not a complete season
    season = [r for r in races if r.date[:4] == race.date[:4]]
    for i, r in enumerate(season, 1):
        if r.slug == race.slug:
            return i
    return None


def fallback_races() -> list[Race]:
    return [Race(name=n, date=d, country=c) for n, d, c in FALLBACK_RACES]


def weekend_refresh_interval_s(races: list[Race], now: datetime) -> int:
    """Poll every 5 min from two hours before the next active session, else hourly."""
    race = next_race(races, now)
    if race is None or not race.sessions:
        return 3600
    for s in race.sessions:
        if s.status == COMPLETED:
            continue
        return 300 if now >= s.start - timedelta(hours=2) else 3600
    return 3600
