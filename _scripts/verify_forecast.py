#!/usr/bin/env python3
"""Compare archived skycheck forecasts with Open-Meteo's historical actuals.

Reads the local history written by skycheck.py, fetches ERA5 archive data for
nights that are old enough, and writes accuracy.json + accuracy.html (with an
inline SVG chart) next to the history.

Usage: ./verify_forecast.py [--history-dir DIR] [--out-dir DIR]

No third-party packages required.
"""
import argparse
import datetime as dt
import glob
import json
import os
import urllib.request
from zoneinfo import ZoneInfo

LAT, LON = "46.72", "-94.40"
TZ_NAME = "America/Chicago"
MAX_CLOUD, MAX_WIND, MAX_GUST = 30, 10, 20
ARCHIVE_DELAY_DAYS = 5  # ERA5 archive typically lags ~5 days


def fetch_json(url, tries=3, timeout=30):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last = e
            if i + 1 < tries:
                import time
                time.sleep(5 * (i + 1))
    raise RuntimeError(f"fetch failed after {tries} tries: {last}")


def load_history(history_dir):
    runs = []
    for path in sorted(glob.glob(os.path.join(history_dir, "*.json"))):
        if os.path.basename(path) in ("accuracy.json",):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            run_date = dt.date.fromisoformat(os.path.basename(path)[:10])
        except Exception:
            continue
        runs.append((run_date, data))
    return runs


def fetch_actuals(start, end):
    if start > end:
        return {}
    url = (
        f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}"
        f"&start_date={start.isoformat()}&end_date={end.isoformat()}"
        f"&hourly=cloud_cover,wind_speed_10m,wind_gusts_10m"
        f"&wind_speed_unit=mph&timezone={TZ_NAME}"
    )
    hourly = fetch_json(url)["hourly"]
    out = {}
    for i, t in enumerate(hourly["time"]):
        d = dt.datetime.fromisoformat(t)
        if 18 <= d.hour <= 23:
            out.setdefault(d.date(), []).append(dict(
                hour=d.hour,
                cloud=hourly["cloud_cover"][i],
                wind=hourly["wind_speed_10m"][i],
                gust=hourly["wind_gusts_10m"][i],
            ))
    return out


def summarize(hours):
    if not hours or any(h.get(k) is None for h in hours for k in ("cloud", "wind", "gust")):
        return None
    cloud = sum(h["cloud"] for h in hours) / len(hours)
    wind = max(h["wind"] for h in hours)
    gust = max(h["gust"] for h in hours)
    return dict(
        cloud=round(cloud, 1), wind=round(wind, 1), gust=round(gust, 1),
        green=cloud <= MAX_CLOUD and wind < MAX_WIND and gust < MAX_GUST,
    )


def build_report(runs, actuals):
    samples = []
    for run_date, data in runs:
        for night in data.get("nights", []):
            try:
                night_date = dt.date.fromisoformat(night["date"])
            except Exception:
                continue
            lead = (night_date - run_date).days
            if lead < 0 or lead > 10 or night_date not in actuals:
                continue
            fc_hours = night.get("evening") or []
            if len(fc_hours) < 6 or any(h.get("cloud") is None for h in fc_hours):
                continue
            fc = summarize(fc_hours)
            ac = summarize(actuals[night_date])
            if not fc or not ac:
                continue
            samples.append(dict(
                run_date=run_date.isoformat(), date=night_date.isoformat(), lead=lead,
                forecast=fc, actual=ac,
                forecast_rating=night.get("rating", "?"),
                cloud_error=round(ac["cloud"] - fc["cloud"], 1),
                abs_cloud_error=round(abs(ac["cloud"] - fc["cloud"]), 1),
                green_correct=fc["green"] == ac["green"],
                go_correct=(night.get("rating") == "GO") == ac["green"],
            ))

    # One row per night in the detail table: use the shortest lead available.
    by_night = {}
    for s in samples:
        cur = by_night.get(s["date"])
        if cur is None or s["lead"] < cur["lead"]:
            by_night[s["date"]] = s
    recent = sorted(by_night.values(), key=lambda s: s["date"], reverse=True)[:30]

    leads = []
    for lead in range(0, 11):
        rows = [s for s in samples if s["lead"] == lead]
        if rows:
            leads.append(dict(
                lead=lead, n=len(rows),
                cloud_mae=round(sum(s["abs_cloud_error"] for s in rows) / len(rows), 1),
                green_accuracy=round(100 * sum(1 for s in rows if s["green_correct"]) / len(rows)),
            ))

    go_rows = [s for s in samples if s["forecast_rating"] == "GO"]
    overall = dict(
        samples=len(samples), nights=len(by_night),
        cloud_mae=round(sum(s["abs_cloud_error"] for s in samples) / len(samples), 1) if samples else None,
        green_accuracy=round(100 * sum(1 for s in samples if s["green_correct"]) / len(samples)) if samples else None,
        go_nights=len(go_rows),
        go_precision=round(100 * sum(1 for s in go_rows if s["actual"]["green"]) / len(go_rows)) if go_rows else None,
    )
    return dict(
        generated=dt.datetime.now(ZoneInfo(TZ_NAME)).isoformat(timespec="seconds"),
        criteria=dict(max_cloud=MAX_CLOUD, max_wind=MAX_WIND, max_gust=MAX_GUST),
        overall=overall, by_lead=leads, recent=recent,
    )


def svg_chart(leads):
    width, height, pad = 720, 240, 36
    if not leads:
        return f'<p class="muted">No verified nights yet. Archive data usually lags {ARCHIVE_DELAY_DAYS} days.</p>'
    max_mae = max(20.0, max(x["cloud_mae"] for x in leads))
    n = len(leads)
    bw = (width - 2 * pad) / n
    bars = []
    for i, x in enumerate(leads):
        h = (height - 2 * pad) * (x["cloud_mae"] / max_mae)
        bx = pad + i * bw + bw * 0.2
        by = height - pad - h
        bars.append(
            f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bw*0.6:.1f}" height="{h:.1f}" rx="4" fill="#3fa7f5"/>'
            f'<text x="{bx + bw*0.3:.1f}" y="{by - 6:.1f}" fill="#e8ecff" font-size="13" text-anchor="middle">{x["cloud_mae"]:.0f}</text>'
            f'<text x="{bx + bw*0.3:.1f}" y="{height - pad + 20:.1f}" fill="#9fb0e6" font-size="13" text-anchor="middle">{x["lead"]}d</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="Mean absolute cloud error by forecast lead time">'
        f'<line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#3a4a85"/>'
        f'<text x="{pad}" y="20" fill="#9fb0e6" font-size="13">Mean absolute cloud-cover error (%) by lead time</text>'
        + "".join(bars) + "</svg>"
    )


def write_html(path, report):
    o = report["overall"]
    summary = (
        f'{o["samples"]} forecasts over {o["nights"]} nights · '
        f'cloud MAE {o["cloud_mae"]}% · green accuracy {o["green_accuracy"]}%'
        if o["samples"] else
        "No verified nights yet — archive data usually lags about 5 days."
    )
    go = (f'{o["go_nights"]} GO forecasts, {o["go_precision"]}% were actually green.'
          if o["go_nights"] else "No GO forecasts verified yet.")
    rows = "".join(
        f'<tr><td>{r["date"]}</td><td>{r["lead"]}</td>'
        f'<td>{r["forecast"]["cloud"]:.0f}% / {r["forecast"]["wind"]:.0f} / {r["forecast"]["gust"]:.0f}</td>'
        f'<td>{r["actual"]["cloud"]:.0f}% / {r["actual"]["wind"]:.0f} / {r["actual"]["gust"]:.0f}</td>'
        f'<td>{"✅" if r["green_correct"] else "❌"}</td>'
        f'<td>{r["forecast_rating"]}</td><td>{r["cloud_error"]:+.0f}</td></tr>'
        for r in report["recent"]
    )
    lead_rows = "".join(
        f'<tr><td>{x["lead"]} day{"s" if x["lead"] != 1 else ""}</td><td>{x["n"]}</td>'
        f'<td>{x["cloud_mae"]}%</td><td>{x["green_accuracy"]}%</td></tr>'
        for x in report["by_lead"]
    )
    chart = svg_chart(report["by_lead"])
    doc = f'''<!doctype html><html><head><meta charset="utf-8">
<title>Forecast accuracy</title>
<style>
body{{margin:0;background:#070b1f;color:#e8ecff;font-family:Inter,Helvetica,Arial,sans-serif}}
.w{{max-width:820px;margin:0 auto;padding:36px 24px}}
h1{{font-size:34px;margin:0 0 4px}} h2{{font-size:22px;color:#ffd36b;margin:30px 0 8px}}
.muted{{color:#9fb0e6}} .card{{background:#18224a;border-radius:14px;padding:16px 20px;margin:14px 0}}
table{{width:100%;border-collapse:collapse;font-size:14px}} th,td{{text-align:left;padding:7px 8px;border-bottom:1px solid #26315e}}
th{{color:#9fb0e6;font-weight:600}}
</style></head><body><div class="w">
<h1>Forecast accuracy</h1>
<div class="muted">Generated {report["generated"]} · green = 6–11 PM average cloud ≤{MAX_CLOUD}%, wind &lt;{MAX_WIND}, gust &lt;{MAX_GUST}</div>
<div class="card"><strong>{summary}</strong><br><span class="muted">{go}</span></div>
<h2>Skill by lead time</h2>
<div class="card">{chart}</div>
<table><tr><th>Lead</th><th>Nights</th><th>Cloud MAE</th><th>Green accuracy</th></tr>{lead_rows}</table>
<h2>Recent nights</h2>
<div class="card"><table><tr><th>Night</th><th>Lead</th><th>Forecast (cloud/wind/gust)</th><th>Actual</th><th>Green?</th><th>GO call</th><th>Cloud error</th></tr>{rows}</table></div>
</div></body></html>'''
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    default_hist = os.path.expanduser("~/.local/share/skycheck/history")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--history-dir", default=default_hist)
    ap.add_argument("--out-dir", default=None, help="defaults to --history-dir")
    args = ap.parse_args()
    out_dir = args.out_dir or args.history_dir
    os.makedirs(out_dir, exist_ok=True)

    runs = load_history(args.history_dir)
    if not runs:
        print(f"No history in {args.history_dir}")
        return

    nights = []
    for _, data in runs:
        for n in data.get("nights", []):
            try:
                nights.append(dt.date.fromisoformat(n["date"]))
            except Exception:
                pass

    today = dt.datetime.now(ZoneInfo(TZ_NAME)).date()
    end = today - dt.timedelta(days=ARCHIVE_DELAY_DAYS)
    start = min(nights) if nights else end
    if start > end:
        print(f"Nothing old enough to verify yet (need archive through {end}).")
        actuals = {}
    else:
        actuals = fetch_actuals(start, min(end, max(nights)))

    report = build_report(runs, actuals)
    json_path = os.path.join(out_dir, "accuracy.json")
    html_path = os.path.join(out_dir, "accuracy.html")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    write_html(html_path, report)

    o = report["overall"]
    if o["samples"]:
        print(f"Verified {o['samples']} forecasts over {o['nights']} nights.")
        print(f"Cloud MAE {o['cloud_mae']}% · green accuracy {o['green_accuracy']}% · GO precision {o['go_precision']}%")
    else:
        print("No verified nights yet (archive data lags ~5 days).")
    print(f"Report: {html_path}")


if __name__ == "__main__":
    main()
