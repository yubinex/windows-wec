# Windows WEC

A small Windows tray app for the FIA World Endurance Championship.
It is the light Windows companion to [omarchy-wec](https://github.com/yubinex/omarchy-wec).

The tray icon is a countdown badge: `18d` until the next session, `5h` on the
day, an amber `45m` when it is close, and a red `LIVE` while a session is on.
Click it to open the WEC window.

## Download

Get `WindowsWEC.exe` from the [latest release](https://github.com/yubinex/windows-wec/releases/latest)
and run it. There is nothing to install and no Python needed (Windows 10/11, 64-bit).

- The .exe is not code-signed yet, so Windows SmartScreen may say "Windows
  protected your PC". Click **More info → Run anyway**.
- On Windows 11, new tray icons start in the overflow menu (`^`). Drag the
  icon onto the taskbar to keep the countdown visible.
- Each release lists the file's SHA-256. To check your download, run
  `Get-FileHash WindowsWEC.exe` in PowerShell and compare.

## The WEC window

A small dark window above the notification area, modelled on the omarchy-wec panel:

- **Header:** next round, venue, round number, next session and race start, with a countdown
- **Race weekend:** timetable grouped by day in your local time (the current day
  opens by default), with LIVE and soon markers, then the next three races
- **Settings:** race flags, completed sessions, start with Windows, refresh, quit
- **Standings ↗:** opens the official championship tables on fiawec.com

Closing the window keeps the app running in the tray. Right-click the icon for
refresh, fiawec.com, start with Windows, and quit.

The calendar refreshes hourly. The weekend timetable refreshes hourly, and every
5 minutes from two hours before the next session. The last data is cached in
`%LOCALAPPDATA%\windows-wec`, so the app starts offline.

On first launch it opens the window. With "Start with Windows" on, it starts
quietly in the tray (`--background`). Running it again while it is already
open does nothing.

## Releasing

Push a version tag and GitHub Actions builds the .exe and publishes the release:

```powershell
git tag v0.2.0
git push origin v0.2.0
```

To build locally instead, run `powershell -ExecutionPolicy Bypass -File build.ps1`,
which produces `dist\WindowsWEC.exe`.

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
flag glyphs, so the app ships them as images: every country flag Twemoji has
(258, about 140 KB), so venues added in future seasons show their flag too.

## Trademark notice

FIA WEC and the WEC logo are trademarks of their respective owners. This
unofficial app is not affiliated with or endorsed by the FIA, the ACO, or Le
Mans Endurance Management. The tray icon is a generic badge and does not use
the WEC logo. Event data is fetched directly from fiawec.com and belongs to its
owners.

## License

[MIT](LICENSE)
