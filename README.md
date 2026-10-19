# Windows WEC

A small Windows tray app for the FIA World Endurance Championship.
It is the light Windows companion to [omarchy-wec](https://github.com/yubinex/omarchy-wec).

The tray icon is a countdown badge: `18d` until the next session, `5h` on the
day, an amber `45m` when it is close, and a red `LIVE` while a session is on.
Click it to open the WEC window.

## The WEC window

A small dark window above the notification area, modelled on the omarchy-wec panel:

- **Header:** next round, venue, round number, next session and race start, with a countdown
- **Race weekend:** timetable grouped by day in your local time (the current day
  opens by default), with LIVE and soon markers, then the next three races
- **Standings:** Hypercar and LMGT3 championship tables. These are a **snapshot
  (4 Sep 2026)**, not live data, and the window labels them that way.
- **Settings:** show/hide completed sessions, start with Windows, refresh, quit

Closing the window keeps the app running in the tray. Right-click the icon for
refresh, fiawec.com, start with Windows, and quit.

The calendar refreshes hourly. The weekend timetable refreshes hourly, and every
5 minutes from two hours before the next session. The last data is cached in
`%LOCALAPPDATA%\windows-wec`, so the app starts offline.

## Give it to someone

```powershell
powershell -ExecutionPolicy Bypass -File build.ps1
```

This builds `dist\WindowsWEC.exe`, one file with no Python needed. Send that file.
On first launch it opens the window. With "Start with Windows" on, it starts
quietly in the tray (`--background`). Running it again while it is already
open does nothing.

Unsigned .exe files get a SmartScreen warning ("More info" → "Run anyway").
Only code signing removes that.

## Run from source

Requires Python 3.10+.

```powershell
pip install -r requirements.txt
python -m wec_tray
```

## Tests

```powershell
python -m unittest discover -s tests
```

The parsers are ported from omarchy-wec and scrape fiawec.com, so a change to
the site's HTML can break them. The test fixtures are synthetic; add saved real
pages under `tests/fixtures/` to guard against that.

## Data sources

Calendar and event data come from [FIA WEC](https://www.fiawec.com/). The app
makes only bounded HTTPS requests to that site.

Flag images in `wec_tray/flags/` are from [Twemoji](https://github.com/jdecked/twemoji)
(© Twitter, Inc. and other contributors), licensed under
[CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/). Windows has no emoji
flag glyphs, so the app ships them as images. To add a country, drop in
`<ISO code>.png`; without one, the window shows the country code instead.

## Trademark notice

FIA WEC and the WEC logo are trademarks of their respective owners. This
unofficial app is not affiliated with or endorsed by the FIA, the ACO, or Le
Mans Endurance Management. The tray icon is a generic badge and does not use
the WEC logo. Event data is fetched directly from fiawec.com and belongs to its
owners.

## License

[MIT](LICENSE)
