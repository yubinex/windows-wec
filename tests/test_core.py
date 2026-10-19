"""Unit tests for wec_tray.core.

The HTML fixtures are synthetic: they are shaped to match what the parsers
expect (ported from omarchy-wec), not captured from fiawec.com. Replace them
with real saved pages in tests/fixtures/ to validate against the live site.
"""

import json
import unittest
from datetime import datetime, timedelta, timezone

from wec_tray import core

UTC = timezone.utc

CALENDAR_HTML = """
<nav>
 <a href="/en/race/6-hours-of-fuji-2026"><span class="flag:JP"></span>
   <div><strong class="d"> 27 </strong><small> Sep </small></div></a>
 <a href="/en/race/official-prologue-qatar-2027"><span class="flag:QA"></span>
   <div><strong>1</strong><small>Mar</small></div></a>
 <a href="/en/race/6-hours-of-barcelona-2026"><span class="flag:ES"></span>
   <div><strong>18</strong><small>Oct</small></div></a>
</nav>
<!-- mobile duplicate -->
<a href="/en/race/6-hours-of-barcelona-2026"><span class="flag:ES"></span>
   <div><strong>18</strong><small>Oct</small></div></a>
"""


def weekend_json(statuses):
    names = ["Free Practice 1", "Qualifying", "Race"]
    starts = ["2026-10-17T10:00:00+02:00", "2026-10-17T15:00:00+02:00", "2026-10-18T12:00:00+02:00"]
    return json.dumps({
        "@type": "SportsEvent",
        "location": {"name": "Circuit", "address": "Barcelona, Spain"},
        "subEvent": [
            {"name": f"{n} - 6 Hours of Barcelona", "startDate": s,
             "eventStatus": f"https://schema.org/{st}"}
            for n, s, st in zip(names, starts, statuses)
        ],
    })


def weekend_html(statuses):
    return f'<html><script type="application/ld+json">{weekend_json(statuses)}</script></html>'


class CalendarTests(unittest.TestCase):
    def test_parses_sorts_dedupes_and_skips_prologue(self):
        races = core.parse_calendar(CALENDAR_HTML)
        self.assertEqual([(r.name, r.date, r.slug) for r in races], [
            ("6 Hours of Fuji", "2026-09-27", "6-hours-of-fuji-2026"),
            ("6 Hours of Barcelona", "2026-10-18", "6-hours-of-barcelona-2026"),
        ])

    def test_garbage_returns_empty(self):
        self.assertEqual(core.parse_calendar("<html>nothing</html>"), [])


class WeekendTests(unittest.TestCase):
    race = core.Race("6 Hours of Barcelona", "2026-10-18", "6-hours-of-barcelona-2026")

    def test_structured_sessions_strip_suffix_and_status(self):
        s = core.parse_weekend(weekend_html(["EventCompleted", "EventScheduled", "EventScheduled"]), self.race)
        self.assertEqual([x.name for x in s], ["Free Practice 1", "Qualifying", "Race"])
        self.assertEqual(s[0].status, "EventCompleted")
        self.assertEqual(s[2].start, datetime(2026, 10, 18, 10, 0, tzinfo=UTC))

    def test_fallback_html_sessions(self):
        ts = int(datetime(2026, 10, 18, 10, 0, tzinfo=UTC).timestamp())
        html = (f'<div class="fw-bold lh-sm text">Race</div><p><span data-local="12:00 PM" '
                f'data-timestamp="{ts}"></span></p>')
        s = core.parse_weekend(html, self.race)
        self.assertEqual(len(s), 1)
        self.assertEqual((s[0].name, int(s[0].start.timestamp())), ("Race", ts))

    def test_no_sessions(self):
        self.assertEqual(core.parse_weekend("<html></html>", self.race), [])


class StateTests(unittest.TestCase):
    def race_with(self, statuses):
        race = core.Race("6 Hours of Barcelona", "2026-10-18", "6-hours-of-barcelona-2026")
        race.sessions = core.parse_weekend(weekend_html(statuses), race)
        return race

    def test_session_short(self):
        self.assertEqual(core.session_short("Free Practice 2"), "FP2")
        self.assertEqual(core.session_short("Hyperpole"), "HYPER")
        self.assertEqual(core.session_short("Qualifying"), "QUAL")
        self.assertEqual(core.session_short("Race"), "RACE")

    def test_upcoming_then_live(self):
        race = self.race_with(["EventScheduled"] * 3)
        before = datetime(2026, 10, 17, 7, 15, tzinfo=UTC)  # FP1 is 08:00 UTC
        ns = core.next_session(race, before)
        self.assertFalse(ns.live)
        self.assertEqual(core.session_countdown(ns, before), "IN 45M")
        during = datetime(2026, 10, 17, 8, 30, tzinfo=UTC)
        self.assertTrue(core.next_session(race, during).live)
        self.assertTrue(core.is_live([race], during))
        self.assertIn("FP1 LIVE", core.tooltip([race], during))

    def test_completed_sessions_are_skipped(self):
        race = self.race_with(["EventCompleted", "EventScheduled", "EventScheduled"])
        ns = core.next_session(race, datetime(2026, 10, 17, 9, 0, tzinfo=UTC))
        self.assertEqual(ns.session.name, "Qualifying")

    def test_round_advances_only_after_final_session_completed(self):
        done = self.race_with(["EventCompleted"] * 3)
        nxt = core.Race("6 Hours of Monza", "2026-11-08")
        after = datetime(2026, 10, 18, 20, 0, tzinfo=UTC)
        self.assertIs(core.next_race([done, nxt], after), nxt)
        not_done = self.race_with(["EventCompleted", "EventCompleted", "EventScheduled"])
        self.assertIs(core.next_race([not_done, nxt], after), not_done)

    def test_fallback_race_end_is_day_after_date(self):
        race = core.Race("X", "2026-11-08")
        self.assertEqual(core.race_end(race), datetime(2026, 11, 9, 0, 0, tzinfo=UTC))

    def test_countdown_text(self):
        now = datetime(2026, 10, 19, 12, 0, tzinfo=UTC).astimezone()
        mk = lambda d: core.Race("X", d)
        self.assertEqual(core.race_countdown(mk("2026-10-19"), now), "today")
        self.assertEqual(core.race_countdown(mk("2026-10-20"), now), "in 1 day")
        self.assertEqual(core.race_countdown(mk("2026-10-25"), now), "in 6 days")
        self.assertEqual(core.race_countdown(mk("2026-11-08"), now), "in 2 weeks, 6 days")
        self.assertEqual(core.race_countdown(mk("2026-11-02"), now), "in 2 weeks")

    def test_no_upcoming_race(self):
        self.assertEqual(core.tooltip([core.Race("Old", "2020-01-01")],
                                      datetime(2026, 1, 1, tzinfo=UTC)), "No upcoming WEC race")

    def test_refresh_interval(self):
        race = self.race_with(["EventScheduled"] * 3)
        self.assertEqual(core.weekend_refresh_interval_s([race], datetime(2026, 10, 10, tzinfo=UTC)), 3600)
        near = race.sessions[0].start - timedelta(minutes=90)
        self.assertEqual(core.weekend_refresh_interval_s([race], near), 300)

    def test_icon_badge(self):
        race = self.race_with(["EventScheduled"] * 3)  # FP1 08:00 UTC on 17 Oct
        self.assertEqual(core.icon_badge([race], datetime(2026, 10, 17, 7, 15, tzinfo=UTC)), ("45m", "soon"))
        self.assertEqual(core.icon_badge([race], datetime(2026, 10, 17, 3, 0, tzinfo=UTC)), ("5h", "idle"))
        self.assertEqual(core.icon_badge([race], datetime(2026, 10, 17, 8, 5, tzinfo=UTC)), ("LIVE", "live"))
        self.assertEqual(core.icon_badge([core.Race("X", "2027-06-12")],
                                         datetime(2026, 11, 1, 12, tzinfo=UTC)), ("31w", "idle"))
        self.assertEqual(core.icon_badge([], datetime(2026, 1, 1, tzinfo=UTC)), ("", "none"))

    def test_round_number_needs_official_calendar(self):
        races = core.parse_calendar(CALENDAR_HTML)
        self.assertEqual(core.round_number(races, races[1]), 2)
        self.assertEqual(races[1].country, "ES")
        self.assertIsNone(core.round_number(core.fallback_races(), core.fallback_races()[0]))

    def test_parse_venue(self):
        self.assertEqual(core.parse_venue(weekend_html(["EventScheduled"] * 3)),
                         ("Circuit", "Barcelona, Spain"))
        self.assertEqual(core.parse_venue("<html></html>"), ("", ""))

    def test_fetch_rejects_non_https(self):
        self.assertIsNone(core.fetch("http://www.fiawec.com/en/"))


if __name__ == "__main__":
    unittest.main()
