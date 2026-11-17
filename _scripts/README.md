# skycheck

Generates the "Coming up" stargazing forecast: a daily GO/NO-GO check plus the
month graphic published at `/images/month.png`.

## Run it manually

```bash
./skycheck.py            # 7 nights, 30° target cutoff
./skycheck.py 10 25      # 10 nights, 25° cutoff
```

The script bootstraps `~/.skycheck-venv` from `requirements.txt` on first run.

To do the full update (publish the image, refresh the post summary and date):

```bash
./run_skycheck.sh
```

## Targets

The target list lives in `../_data/targets.json`:

```json
{"name": "M57 Ring Nebula", "ra": "18:53:35", "dec": "33:01:45", "fun": 5, "moon_ok": true}
```

- `ra`/`dec` are J2000 coordinates (`HH:MM:SS`, `DD:MM:SS`).
- `fun` is 1–5 and controls the top-5 ordering.
- `moon_ok` means the target is still worthwhile with the moon up.

Edit that file and commit it; the next run picks it up. No code changes needed.

## Cloud and smoke

The forecast asks Open-Meteo for cloud cover split into low, mid, and high
layers. A single number hides the difference between a solid low deck and thin
cirrus, so the script uses a weighted value for its GO decision and calendar
colours:

```text
effective = max(low, 0.8 × mid, 0.4 × high, 0.6 × total)
```

Low cloud counts fully, mid cloud loses 20%, high cirrus loses 60%, and the
total sets a floor so an overcast high deck can't look clear. The graphic shows
this weighted percentage.

It also fetches PM2.5 and aerosol optical depth from Open-Meteo's air-quality
API (up to 7 days). A night is marked smoky when either exceeds its threshold:

- PM2.5 > 35 µg/m³
- AOD > 0.4

Both layers and smoke data are optional: if the API is unavailable, the script
falls back to total cloud and no smoke signal. History records keep the raw
layers, PM2.5, AOD, and the weighted value so the accuracy report can compare
like with like.

## Scheduling

Scheduling is handled by the user crontab. Check it with:

```bash
crontab -l
```

The active entries are:

```cron
SKYCHECK_CHROME=/home/user/.local/bin/skycheck-chrome
0 2 * * * /home/user/ethos101.github.io/_scripts/run_skycheck.sh >> /home/user/ethos101.github.io/_scripts/out.log 2>&1
0 3 * * 0 /usr/bin/python3 /home/user/ethos101.github.io/_scripts/verify_forecast.py >> /home/user/.local/share/skycheck/verify.log 2>&1
```

- The daily job runs at 02:00 America/Chicago via `run_skycheck.sh`, which
  generates the forecast, publishes the image/summary, commits, and pushes.
  Its output and any warnings are appended to `out.log`.
- The weekly job runs Sunday at 03:00 and rebuilds the accuracy report; errors
  are appended to `verify.log`.
- `SKYCHECK_CHROME` points at the Playwright Chromium used to render the
  graphic (the distro Chrome is not installed).
- Email notifications are not sent; failures are recorded in the log files.

Adjust the times with `crontab -e`. The wrapper uses `flock`, so an overlapping
manual run is skipped rather than corrupting the output.

The optional systemd units in `systemd/` are kept for reference but are not
installed. If you prefer timers later, copy them to `~/.config/systemd/user/`,
enable them, and remove the cron entries so the job doesn't run twice.

## Forecast accuracy

`verify_forecast.py` compares the saved forecasts with Open-Meteo's archive
(ERA5, which typically lags about 5 days). It writes:

- `~/.local/share/skycheck/history/accuracy.json` — raw comparisons
- `~/.local/share/skycheck/history/accuracy.html` — chart + table

Run it manually with:

```bash
./verify_forecast.py
# or point at a test directory:
./verify_forecast.py --history-dir /tmp/skycheck-test
```

The report shows weighted cloud-cover error and green/no-green accuracy by
forecast lead time, plus GO-call precision and a recent-nights table. The
archive is also split into low/mid/high layers and weighted the same way, so the
comparison is consistent with the forecast.

## What gets written

| Path | Committed? | Purpose |
| --- | --- | --- |
| `_scripts/month.html` | no (ignored) | Intermediate render |
| `_scripts/month_<mon>.png` | no (ignored) | Generated graphic |
| `_scripts/out.log` | no (ignored) | Last run log |
| `images/month.png` | yes | Image shown on the post |
| `_includes/forecast_status.html` | yes | Text summary shown on the post |
| `_posts/1900-01-01-about.md` | yes | Post date refreshed on each run |
| `~/.local/share/skycheck/history/*.json` | no | Forecast history (one file per run) |
| `~/.local/share/skycheck/history/accuracy.{json,html}` | no | Forecast-vs-actual report |

## Environment overrides

`run_skycheck.sh` accepts:

- `GIT_SSH_COMMAND` — override the SSH command used for `git push`
- `SKYCHECK_CHROME` — path to the Chrome/Chromium binary (default
  `/usr/bin/google-chrome`)

## Notes

- The main forecast is Open-Meteo's `best_match` model. A second request checks
  ECMWF/GFS/ICON spread; if the models disagree, the calendar shows "iffy"
  instead of green and the text summary says "models disagree".
- Weather data: Open-Meteo (CC BY 4.0).
