#!/usr/bin/env python3
"""Go/No-Go stargazing check + month graphic, in one run.

Usage: ./skycheck.py [nights=7] [min_alt_deg=30]

Prints GO nights (personal 30° cutoff, sessions end at midnight) and
writes this month's Go/No-Go page (horizon trails, public-facing wording)
as month_<mon>.png in this folder.
"""
import os, sys, subprocess, shutil

VENV = os.path.expanduser("~/.skycheck-venv")
VENV_PY = os.path.join(VENV, "bin", "python")

def ensure_venv():
    if sys.executable.startswith(VENV + os.sep) or sys.prefix == VENV:
        return
    # Rebuild stale or partial venvs (e.g. after a system Python upgrade, or if pip is missing).
    pip_ok = os.path.exists(VENV_PY) and subprocess.run(
        [VENV_PY, "-m", "pip", "--version"], capture_output=True
    ).returncode == 0
    if not pip_ok:
        shutil.rmtree(VENV, ignore_errors=True)
        subprocess.check_call([sys.executable, "-m", "venv", VENV])
    need = subprocess.run([VENV_PY, "-c", "import ephem, playwright"], capture_output=True)
    if need.returncode != 0:
        req = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
        pkgs = ["-r", req] if os.path.exists(req) else ["ephem", "playwright"]
        subprocess.check_call([VENV_PY, "-m", "pip", "install", "--quiet", *pkgs])
    os.execv(VENV_PY, [VENV_PY, *sys.argv])

ensure_venv()

import math, json, calendar, datetime as dt, urllib.request, urllib.error, html, time
from zoneinfo import ZoneInfo
import ephem

# --- config (edit these) ---
LAT, LON = "46.72", "-94.40"
TZ_NAME = "America/Chicago"
PLACE = "Central Minnesota"
MAX_CLOUD, MAX_WIND, MAX_GUST = 30, 10, 20
MIN_VIS_M, MIN_DEW_SPREAD_F = 5000, 3
CHROME = os.environ.get("SKYCHECK_CHROME", "/usr/bin/google-chrome")
# Extra models used only to flag forecast disagreement (the main forecast stays best-match).
MODELS = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless"]
# ---------------------------

NIGHTS = int(sys.argv[1]) if len(sys.argv) > 1 else 7
MIN_ALT = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

tz = ZoneInfo(TZ_NAME)
today = dt.datetime.now(tz).date()
Y, M = today.year, today.month
LAB = calendar.month_name[M]
nd = calendar.monthrange(Y, M)[1]

# name, RA, Dec (J2000), fun 1-5, ok in moonlight
T = [
    ("M57 Ring Nebula", "18:53:35", "33:01:45", 5, 1),
    ("M27 Dumbbell Nebula", "19:59:36", "22:43:16", 5, 1),
    ("M81/M82 Bode's+Cigar", "09:55:33", "69:03:55", 5, 0),
    ("M13 Hercules Cluster", "16:41:41", "36:27:37", 5, 1),
    ("M15 Globular", "21:29:58", "12:10:01", 5, 1),
    ("M42 Orion Nebula", "05:35:17", "-05:23:28", 5, 1),
    ("M51 Whirlpool Galaxy", "13:29:53", "47:11:43", 4, 0),
    ("NGC 7662 Blue Snowball", "23:25:54", "42:32:06", 4, 1),
    ("M1 Crab Nebula", "05:34:32", "22:00:52", 4, 0),
    ("NGC 2392 Eskimo Nebula", "07:29:11", "20:54:42", 4, 1),
    ("NGC 6543 Cat's Eye", "17:58:33", "66:37:59", 4, 1),
    ("NGC 891 Edge-on Galaxy", "02:22:33", "42:20:57", 4, 0),
    ("NGC 4565 Needle Galaxy", "12:36:21", "25:59:16", 4, 0),
    ("M31 Andromeda core", "00:42:44", "41:16:09", 4, 0),
    ("M92 Globular", "17:17:07", "43:08:09", 4, 1),
    ("M3 Globular", "13:42:11", "28:22:38", 4, 1),
    ("M2 Globular", "21:33:27", "-00:49:24", 4, 1),
    ("M33 + NGC 604", "01:33:51", "30:39:37", 3, 0),
    ("NGC 7331 Galaxy", "22:37:04", "34:24:56", 3, 0),
    ("M76 Little Dumbbell", "01:42:20", "51:34:31", 3, 1),
    ("NGC 2403 Galaxy", "07:36:51", "65:36:09", 3, 0),
    ("M101 Pinwheel Galaxy", "14:03:13", "54:20:57", 3, 0),
    ("M64 Black Eye Galaxy", "12:56:44", "21:40:58", 3, 0),
    ("NGC 457 Owl Cluster", "01:19:33", "58:17:27", 3, 1),
    ("M35 Open Cluster", "06:08:56", "24:20:48", 3, 1),
    ("NGC 6946 Fireworks Galaxy", "20:34:52", "60:09:14", 2, 0),
    ("NGC 2419 Intergalactic Wanderer", "07:38:08", "38:52:55", 2, 0),
    ("IC 342 Galaxy", "03:46:49", "68:05:46", 1, 0),
]

obs = ephem.Observer()
obs.lat, obs.lon, obs.elevation = LAT, LON, 400
sun, moon = ephem.Sun(), ephem.Moon()

def alt(body, t):
    obs.date = ephem.Date(t.astimezone(dt.timezone.utc).replace(tzinfo=None))
    body.compute(obs)
    return math.degrees(body.alt)

def body(ra, de):
    b = ephem.FixedBody()
    b._ra, b._dec, b._epoch = ra, de, ephem.J2000
    return b

def fetch_json(url, tries=3, timeout=30):
    """Fetch JSON with a timeout and a few retries, so a bad network can't hang cron."""
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except Exception as e:
            last = e
            if i + 1 < tries:
                time.sleep(5 * (i + 1))
    raise SystemExit(f"ERROR: weather fetch failed after {tries} tries: {last}")

def longest_run(times, step):
    """Return (start, end) of the longest consecutive run, or None."""
    if not times:
        return None
    best = cur = [times[0]]
    for t in times[1:]:
        if t - cur[-1] == step:
            cur.append(t)
        else:
            if len(cur) > len(best):
                best = cur
            cur = [t]
    if len(cur) > len(best):
        best = cur
    return best[0], best[-1] + step

def models_disagree(w, cloud_spread=30, gust_spread=10):
    return w.get("cspread", 0) > cloud_spread or w.get("gspread", 0) > gust_spread

days = min(NIGHTS + 1, 16)
url = (
    f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
    f"&hourly=cloud_cover,wind_speed_10m,wind_gusts_10m,visibility,temperature_2m,dew_point_2m"
    f"&temperature_unit=fahrenheit&wind_speed_unit=mph&timezone={TZ_NAME}&forecast_days={days}"
)
hourly = fetch_json(url)["hourly"]
wx = {}
for i, t in enumerate(hourly["time"]):
    wx[dt.datetime.fromisoformat(t).replace(tzinfo=tz)] = dict(
        cloud=hourly["cloud_cover"][i],
        wind=hourly["wind_speed_10m"][i],
        gust=hourly["wind_gusts_10m"][i],
        vis=hourly["visibility"][i],
        temp=hourly["temperature_2m"][i],
        dew=hourly["dew_point_2m"][i],
        cspread=0.0,
        gspread=0.0,
    )

# Optional cross-model spread: keeps the best-match forecast, but flags nights
# where the big models disagree so the calendar doesn't look falsely certain.
try:
    murl = (
        f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
        f"&hourly=cloud_cover,wind_speed_10m,wind_gusts_10m&models={','.join(MODELS)}"
        f"&wind_speed_unit=mph&timezone={TZ_NAME}&forecast_days={days}"
    )
    mh = fetch_json(murl, tries=2, timeout=20)["hourly"]
    models = [m for m in MODELS if f"cloud_cover_{m}" in mh]
    if len(models) > 1:
        def spread(series):
            vals = [v for v in series if v is not None]
            return (max(vals) - min(vals)) if vals else 0.0
        for i, t in enumerate(mh["time"]):
            key = dt.datetime.fromisoformat(t).replace(tzinfo=tz)
            if key not in wx:
                continue
            cs = [mh[f"cloud_cover_{m}"][i] for m in models]
            gs = [mh[f"wind_gusts_10m_{m}"][i] for m in models]
            wx[key]["cspread"] = spread(cs)
            wx[key]["gspread"] = spread(gs)
except Exception as e:
    print(f"note: multi-model confidence unavailable ({e})", file=sys.stderr)

# --- text GO/No-Go check (30° cutoff, before midnight) ---
now = dt.datetime.now(tz)
start = now.replace(hour=12, minute=0, second=0, microsecond=0)
if now.hour < 6:
    start -= dt.timedelta(days=1)
step = dt.timedelta(minutes=10)
bodies = [(n, body(ra, de), f, mo) for n, ra, de, f, mo in T]
results = []
night_log = []
for d in range(NIGHTS):
    n0 = start + dt.timedelta(days=d)
    dark, t = [], n0
    while t < n0 + dt.timedelta(hours=20):
        if t >= now - step and alt(sun, t) < -18:
            dark.append(t)
        t += step
    if not dark:
        continue
    mid = dark[len(dark) // 2]
    obs.date = ephem.Date(mid.astimezone(dt.timezone.utc).replace(tzinfo=None))
    moon.compute(obs)
    illum = moon.moon_phase * 100
    session_end = n0 + dt.timedelta(hours=12)  # sessions end at midnight
    good, moonfree, hrs, lows = [], [], [], []
    for t in dark:
        if t >= session_end:
            break
        w = wx.get(t.replace(minute=0))
        if not w:
            continue
        hrs.append(w)
        lows.append(w["temp"])
        ok = (
            w["cloud"] <= MAX_CLOUD
            and w["wind"] < MAX_WIND
            and w["gust"] < MAX_GUST
            and (w["vis"] or 0) >= MIN_VIS_M
            and (w["temp"] - w["dew"]) >= MIN_DEW_SPREAD_F
        )
        if ok:
            good.append(t)
            if alt(moon, t) < 0 or illum < 25:
                moonfree.append(t)
    if not hrs:
        continue
    gh = len(good) * step.seconds / 3600
    rating = "GO" if gh >= 3 else ("MAYBE" if gh >= 1 else "NO")
    conf = "" if d < 3 else " (low confidence)"
    if any(models_disagree(w) for w in hrs):
        conf += " (models disagree)"
    night_log.append(dict(
        date=n0.strftime("%Y-%m-%d"), rating=rating,
        good_hours=round(gh, 1), low_f=round(min(lows)), note=conf.strip(),
        evening=[dict(time=t.strftime("%H:%M"), cloud=w["cloud"], wind=w["wind"],
                      gust=w["gust"], cloud_spread=w["cspread"], gust_spread=w["gspread"])
                 for t, w in sorted(wx.items()) if t.date() == n0.date() and 18 <= t.hour <= 23],
    ))
    if rating == "GO":
        results.append((n0, conf, good, set(moonfree), min(lows), longest_run(good, step)))

fmt = lambda t: t.strftime("%-I:%M %p").lower()
print(f"Go / No-Go · {LAB} · {PLACE}")
print(f"Clear ≤{MAX_CLOUD}% cloud, wind <{MAX_WIND} mph, gusts <{MAX_GUST}. Targets above {MIN_ALT:.0f}° before midnight.")
print("Session check uses dark hours before midnight; the calendar uses 6–11 PM averages.")
print()
if not results:
    print("No GO nights in the forecast.")
else:
    for n0, conf, good, mfree, low, win in results:
        picks = []
        for name, b, fun, moonok in bodies:
            up = [
                t
                for t in good
                if t < n0 + dt.timedelta(hours=12)
                and alt(b, t) >= MIN_ALT
                and (moonok or t in mfree)
            ]
            if up:
                peak = max(up, key=lambda t: alt(b, t))
                picks.append((fun, len(up), name, up[0], up[-1] + step, alt(b, peak), moonok))
        picks.sort(key=lambda p: (-p[0], -p[1]))
        if not picks:
            print(f"GO {n0:%a %b %-d}{conf}: (no targets above cutoff)")
            continue
        name, a, z = picks[0][2], picks[0][3], picks[0][4]
        rec = next(r for r in night_log if r["date"] == n0.strftime("%Y-%m-%d"))
        rec.update(best_target=name, window_start=fmt(win[0]), window_end=fmt(win[1]))
        window = f"longest {fmt(win[0])}-{fmt(win[1])}, " if win else ""
        print(
            f"GO {n0:%a %b %-d}{conf}: {name}, {fmt(a)}-{fmt(z)} "
            f"(clear {len(good) * step.seconds / 3600:.1f}h, {window}low {low:.0f}F)"
        )

# --- save a small history record for later forecast-vs-actual checks ---
try:
    hist_dir = os.path.expanduser("~/.local/share/skycheck/history")
    os.makedirs(hist_dir, exist_ok=True)
    with open(os.path.join(hist_dir, f"{today.isoformat()}.json"), "w") as f:
        json.dump(dict(
            generated=dt.datetime.now(tz).isoformat(timespec="seconds"),
            place=PLACE, forecast_days=days, models=MODELS,
            settings=dict(max_cloud=MAX_CLOUD, max_wind=MAX_WIND, max_gust=MAX_GUST,
                          min_visibility_m=MIN_VIS_M, min_dew_spread_f=MIN_DEW_SPREAD_F),
            nights=night_log,
        ), f, indent=2)
except Exception as e:
    print(f"note: could not save history ({e})", file=sys.stderr)

# --- month graphic (horizon trails, public-facing) ---
W = {}
for t, w in wx.items():
    W[t] = (w["cloud"], w["wind"], w["gust"], w["cspread"], w["gspread"])

mn = ephem.Moon()
# Calendar covers only days with an evening forecast, starting today.
last = today
for i in range(16):
    day = today + dt.timedelta(days=i)
    hrs = [W[k] for k in W if getattr(k, "tzinfo", None) and k.date() == day and 18 <= k.hour <= 23]
    if len(hrs) >= 6:
        last = day
    elif i > 0:
        break
dates = []
d0 = today
while d0 <= last:
    dates.append(d0)
    d0 += dt.timedelta(days=1)
if last.month == today.month:
    rng = f"{today:%b %-d}–{last.day}"
else:
    rng = f"{today:%b %-d}–{last:%b %-d}"

cells = ""
green_days = []
for day in dates:
    tt = dt.datetime(day.year, day.month, day.day, 21, tzinfo=tz)
    obs.date = ephem.Date(tt.astimezone(dt.timezone.utc).replace(tzinfo=None))
    mn.compute(obs)
    il = mn.phase / 100
    wax = ephem.Moon(ephem.Date(obs.date) + 1).phase > mn.phase
    e = "🌑🌒🌓🌔🌕🌖🌗🌘"[
        0 if il < 0.06 else 4 if il > 0.94 else (1 if il < 0.35 else 2 if il < 0.65 else 3) if wax else (7 if il < 0.35 else 6 if il < 0.65 else 5)
    ]
    ev = [dt.datetime(day.year, day.month, day.day, 18, tzinfo=tz) + dt.timedelta(minutes=10 * i) for i in range(37)]
    upm = [alt(ephem.Moon(), t) > 0 for t in ev]
    fm = lambda t: t.strftime("%-I%p").lower().replace("m", "").replace("12a", "12a")
    if all(upm):
        ml = "all eve"
    elif not any(upm):
        ml = "down"
    elif upm[0]:
        ml = f"sets {fm(ev[upm.index(False)])}"
    else:
        ml = f"rises {fm(ev[upm.index(True)])}"
    mlh = f'<div class="mo">{e}<span class="ml2">{ml}</span></div>'
    hrs = [W[k] for k in W if getattr(k, "tzinfo", None) and k.date() == day and 18 <= k.hour <= 23]
    c = sum(x[0] for x in hrs) / len(hrs)
    w = max(x[1] for x in hrs)
    g = max(x[2] for x in hrs)
    disagree = sum(1 for x in hrs if x[3] > 30 or x[4] > 10) > len(hrs) / 2
    ok = c <= MAX_CLOUD and w < MAX_WIND and g < MAX_GUST and not disagree
    cls = "g" if ok else ("y" if c <= 60 and w < 15 else "rd")
    wxcell = f'<div class="x">☁ {c:.0f}%</div><div class="x">💨 {w:.0f}</div>'
    if ok:
        green_days.append(day)
    dn = f"{day:%b} {day.day}" if day.day == 1 and day.month != today.month else str(day.day)
    cells += f'<div class="d {cls}"><div class="dn">{dn}</div>{mlh}{wxcell}</div>'

# Week starts Sunday, same as the SMTWTFS headers.
pad_n = (today.weekday() + 1) % 7
pad = "".join('<div class="d e"></div>' for _ in range(pad_n))
trail = (pad_n + len(dates)) % 7
if trail:
    pad_after = "".join('<div class="d e"></div>' for _ in range(7 - trail))
else:
    pad_after = ""
cells += pad_after

t0 = dt.datetime(Y, M, 15, 12, tzinfo=tz)
dark, t = [], t0
while t < t0 + dt.timedelta(hours=19):
    if alt(sun, t) < -18:
        dark.append(t)
    t += dt.timedelta(minutes=10)

rows = []
for n, ra, de, f, mo in T:
    b = body(ra, de)
    up = [t for t in dark if alt(b, t) > 0]
    if len(up) < 6:
        continue
    def P(t, b=b):
        hh = alt(b, t)
        compass = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((math.degrees(b.az) + 22.5) % 360 // 45)]
        return f"{compass} {round(hh)}°"
    pk = max(up, key=lambda t: alt(b, t))
    path = f"{P(up[0])} → {P(pk)} at {pk.strftime('%-I:%M')} → {P(up[-1])}" if pk not in (up[0], up[-1]) else f"{P(up[0])} → {P(up[-1])}"
    rows.append((int(f), len(up), path, n, ra, de, up[0].strftime("%-I:%M"), (up[-1] + dt.timedelta(minutes=10)).strftime("%-I:%M"), int(mo)))
rows.sort(key=lambda r: (-r[0], -r[1]))
rows = rows[:5]

R, C = 440, 480
COL = ["#f2b632", "#3fa7f5", "#e8573f", "#46c96b", "#e0e0e0"]

def xy(al, az):
    r = (90 - al) / 90 * R
    a = math.radians(az)
    return C - r * math.sin(a), C - r * math.cos(a)

sv = f'<svg width="960" height="960" viewBox="0 0 960 960"><circle cx="{C}" cy="{C}" r="{R}" fill="#0b1230" stroke="#3a4a85" stroke-width="3"/>'
sv += f'<circle cx="{C}" cy="{C}" r="{R*60/90}" fill="#0e1738" stroke="#2b3970" stroke-width="2"/><circle cx="{C}" cy="{C}" r="{R*30/90}" fill="none" stroke="#2b3970" stroke-width="2"/>'
for lab2, az in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
    x, y = xy(5, az)
    sv += f'<text x="{x}" y="{y+12}" fill="#c9d3f5" font-size="36" font-weight="700" text-anchor="middle">{lab2}</text>'

t8 = dt.datetime(Y, M, 15, 20, tzinfo=tz)
ts = [dt.datetime(Y, M, 15, 18, 30, tzinfo=tz) + dt.timedelta(minutes=15 * i) for i in range(50)]
for i, (f, _, wpath, n, ra, de, a, z, mo) in enumerate(rows):
    b = body(ra, de)
    segs = [[]]
    for t in ts:
        al = alt(b, t)
        if al > 0:
            segs[-1].append(xy(al, math.degrees(b.az)))
        elif segs[-1]:
            segs.append([])
    for sg in segs:
        if len(sg) > 1:
            sv += f'<polyline points="{" ".join(f"{x:.0f},{y:.0f}" for x,y in sg)}" fill="none" stroke="{COL[i]}" stroke-width="5" stroke-opacity=".9" stroke-linecap="round"/>'
    upw = [t for t in [dt.datetime(Y, M, 15, 18, 30, tzinfo=tz) + dt.timedelta(minutes=10 * k) for k in range(76)] if alt(b, t) > 0]
    for th, lbl in ((upw[0], a), (upw[-1], z)) if upw else ():
        alh = alt(b, th)
        hx, hy = xy(alh, math.degrees(b.az))
        sv += f'<circle cx="{hx:.0f}" cy="{hy:.0f}" r="7" fill="{COL[i]}"/><text x="{hx+12:.0f}" y="{hy-10:.0f}" font-size="24" fill="{COL[i]}" font-weight="700">{lbl}</text>'
    tm = dt.datetime(Y, M, 16, 0, tzinfo=tz)
    am = alt(b, tm)
    if am > 0:
        mx, my = xy(am, math.degrees(b.az))
        sv += f'<rect x="{mx-9:.0f}" y="{my-9:.0f}" width="18" height="18" fill="none" stroke="#ffffff" stroke-width="3"/>'
    tt = t8 if alt(b, t8) > 0 else max(ts, key=lambda t: alt(b, t))
    al = alt(b, tt)
    x, y = xy(al, math.degrees(b.az))
    sv += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="11" fill="{COL[i]}" stroke="#0b1230" stroke-width="3"/>'
sv += "</svg>"

key = "".join(
    f'<div class="kr"><span class="kd" style="background:{COL[i]}">{i+1}</span><span class="o">{html.escape(n)}{" 🌙" if mo else ""}</span><span class="t">{a}–{z}</span></div>'
    for i, (f, _, wpath, n, ra, de, a, z, mo) in enumerate(rows)
)

H = f'''<html><head><style>body{{margin:0;background:linear-gradient(#070b1f,#111a3d);font-family:Inter,Helvetica,Arial,sans-serif;color:#e8ecff}}
.w{{padding:50px 44px}} h1{{font-size:64px;margin:0}} .sub{{font-size:28px;color:#9fb0e6;margin:8px 0 24px}}
.cal{{display:grid;grid-template-columns:repeat(7,1fr);gap:8px}} .hd{{text-align:center;font-size:24px;color:#7f90c8}}
.d{{background:#18224a;border-radius:14px;padding:8px 4px;text-align:center;min-height:118px}} .e{{background:none}}
.dn{{font-size:26px;font-weight:700}} .mo{{font-size:30px;margin:4px 0;display:flex;align-items:center;justify-content:center;gap:4px}} .x{{font-size:22px;color:#c9d3f5}} .nf{{color:#56638f}} .ml2{{font-size:19px;color:#ffe9a8}}
.g{{background:#155c3a;outline:3px solid #3ddc84}} .y{{background:#5a4a14}} .rd{{background:#4a1d26}} .p{{opacity:.35}}
.k{{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:14px 0 30px}} .ch{{font-size:26px;padding:6px 16px;border-radius:12px}} .g2{{background:#155c3a;outline:3px solid #3ddc84}} .y2{{background:#5a4a14}} .r2{{background:#4a1d26}} .kt{{font-size:24px;color:#9fb0e6;width:100%}} h2{{font-size:44px;color:#ffd36b;margin:0 0 6px}} .h2s{{font-size:26px;color:#9fb0e6;margin:0 0 16px;line-height:1.45}}
.c{{background:#18224a;border-radius:22px;padding:14px 26px}}
.sk{{text-align:center}} .kr{{display:flex;align-items:center;font-size:34px;line-height:1.8;border-bottom:1px solid #26315e}} .kd{{width:44px;height:44px;border-radius:22px;color:#0b1230;font-weight:800;text-align:center;line-height:44px;margin-right:16px}} .f{{font-size:27px;color:#9fb0e6;margin-top:22px;line-height:1.6}} .o{{flex:1}} .t{{width:200px;text-align:right;color:#9fb0e6}}</style></head><body><div class="w">
<h1>Go / No-Go</h1><div class="sub">{PLACE} · Deep-sky targets · {rng} · updated {today:%b %-d}</div>
<div class="cal">{"".join(f'<div class="hd">{x}</div>' for x in "SMTWTFS")}{pad}{cells}</div>
<div class="k"><span class="ch g2">Clear + calm</span><span class="ch y2">Iffy</span><span class="ch r2">No</span><span class="kt">Moon icon + when it rises/sets 6 PM–midnight · ☁ cloud % · 💨 wind mph · green = 6–11 PM average · yellow also means models disagree</span></div>
<h2>Top 5 targets · sky at 8 PM</h2><div class="h2s">A short list: the 5 most fun deep-sky targets that are up after the sky is fully dark (sun 18° down, {dark[0].strftime('%-I:%M')} mid-month). Dots show 8 PM.</div><div class="sk">{sv}</div><div class="c">{key}</div>
<div class="f"><div>🕘 Times PM, mid-month (~1 hr earlier by {LAB[:3]} {nd})</div><div>Map = looking straight up, N at top. Center = overhead. Trails = path through the dark night, labels = start/end of darkness or rise/set. White square = midnight.</div><div>🌙 = still visible with the moon up · Weather data: Open-Meteo (CC BY 4.0) · Forecast guidance only</div></div></div></body></html>'''

html_path = os.path.join(HERE, "month.html")
png_name = f"month_{LAB[:3].lower()}.png"
png_path = os.path.join(HERE, png_name)
open(html_path, "w").write(H)

if not os.path.exists(CHROME):
    raise SystemExit(f"ERROR: Chrome not found at {CHROME} (set SKYCHECK_CHROME)")

from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)
    page = browser.new_page(viewport={"width": 1080, "height": 800})
    page.goto("file://" + html_path)
    page.wait_for_timeout(300)
    page.screenshot(path=png_path, full_page=True)
    browser.close()

print()
print(f"Graphic: {png_path}")
if green_days:
    print("Green on the calendar: " + ", ".join(d.strftime("%a %-d") for d in green_days))
else:
    print("No green nights on the calendar.")
