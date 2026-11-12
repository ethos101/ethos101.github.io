# skycheck

Generates the "Coming up" stargazing forecast: a daily GO/NO-GO check plus the
month graphic published at `/images/month.png`.

## Run it manually

```bash
./skycheck.py            # 7 nights, 30° target cutoff
./skycheck.py 10 25      # 10 nights, 25° cutoff
```

The script bootstraps `~/.skycheck-venv` from `requirements.txt` on first run.

To do the full update (publish the image, refresh the post summary, email it):

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

## Scheduling

Two user systemd timers are installed and enabled:

```bash
systemctl --user list-timers 'skycheck*'
systemctl --user start skycheck.service          # run the forecast now
systemctl --user start skycheck-verify.service   # rebuild accuracy report now
journalctl --user -u skycheck.service -n 50
```

- `skycheck.timer` runs daily at 05:00 America/Chicago with `Persistent=true`,
  so a run missed because the machine was asleep happens after the next boot.
- `skycheck-verify.timer` runs weekly on Sunday at 06:00 and rebuilds the
  accuracy report.

Unit files live in `systemd/` and are installed in
`~/.config/systemd/user/`. Linger is enabled so the timers run while logged out.
The old crontab entry has been removed.

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

The report shows cloud-cover error and green/no-green accuracy by forecast lead
time, plus GO-call precision and a recent-nights table.

## What gets written

| Path | Committed? | Purpose |
| --- | --- | --- |
| `_scripts/month.html` | no (ignored) | Intermediate render |
| `_scripts/month_<mon>.png` | no (ignored) | Generated graphic |
| `_scripts/out.log` | no (ignored) | Last run log |
| `images/month.png` | yes | Image shown on the post |
| `_includes/forecast_status.html` | yes | Text summary shown on the post |
| `~/.local/share/skycheck/history/*.json` | no | Forecast history (one file per run) |
| `~/.local/share/skycheck/history/accuracy.{json,html}` | no | Forecast-vs-actual report |

## Environment overrides

`run_skycheck.sh` accepts:

- `SKYCHECK_NO_MAIL=1` — skip email (useful for testing)
- `SKYCHECK_MAIL_TO`, `SKYCHECK_MAIL_FROM` — override recipients
- `GIT_SSH_COMMAND` — override the SSH command used for `git push`
- `SKYCHECK_CHROME` — path to the Chrome/Chromium binary (default
  `/usr/bin/google-chrome`)

## Notes

- The main forecast is Open-Meteo's `best_match` model. A second request checks
  ECMWF/GFS/ICON spread; if the models disagree, the calendar shows "iffy"
  instead of green and the text summary says "models disagree".
- Weather data: Open-Meteo (CC BY 4.0).
