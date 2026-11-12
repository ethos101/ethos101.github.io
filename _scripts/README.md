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

## Scheduling

A user systemd timer is installed and enabled:

```bash
systemctl --user list-timers skycheck.timer
systemctl --user start skycheck.service   # run now
journalctl --user -u skycheck.service -n 50
```

The timer runs daily at 05:00 America/Chicago with `Persistent=true`, so a run
missed because the machine was asleep happens after the next boot.

Unit files live in `systemd/` and are installed in
`~/.config/systemd/user/`. Linger is enabled so the user timer runs while logged
out. The old crontab entry has been removed.

## What gets written

| Path | Committed? | Purpose |
| --- | --- | --- |
| `_scripts/month.html` | no (ignored) | Intermediate render |
| `_scripts/month_<mon>.png` | no (ignored) | Generated graphic |
| `_scripts/out.log` | no (ignored) | Last run log |
| `images/month.png` | yes | Image shown on the post |
| `_includes/forecast_status.html` | yes | Text summary shown on the post |
| `~/.local/share/skycheck/history/*.json` | no | Local history for later forecast-vs-actual checks |

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
