#!/usr/bin/env bash
# Run skycheck.py and publish the forecast.
# Cron: 0 2 * * * /home/user/ethos101.github.io/_scripts/run_skycheck.sh
set -uo pipefail

REPO="/home/user/ethos101.github.io"
SCRIPT_DIR="$REPO/_scripts"
OUT="$SCRIPT_DIR/out.log"
INCLUDE="$REPO/_includes/forecast_status.html"
ABOUT="$REPO/_posts/1900-01-01-about.md"
LOCK="/tmp/skycheck-$(id -u).lock"

export TZ="America/Chicago"
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes}"

# Only one run at a time.
exec 9>"$LOCK"
if ! flock -n 9; then
    echo "skycheck already running; skipping" >&2
    exit 0
fi

cd "$SCRIPT_DIR" || exit 1

# 1. Generate the forecast.
./skycheck.py >"$OUT" 2>&1
status=$?
if [ "$status" -ne 0 ]; then
    echo "skycheck.py failed with status $status" >>"$OUT"
    exit "$status"
fi

# 2. Publish the newest monthly graphic at the stable path used by the post.
latest=$(ls -t "$SCRIPT_DIR"/month_*.png 2>/dev/null | head -n1)
if [ -z "$latest" ]; then
    echo "ERROR: no month_*.png produced" >>"$OUT"
    exit 1
fi
cp "$latest" "$REPO/images/month.png"

# 3. Write a short text summary for the post (so it isn't image-only).
today=$(date '+%Y-%m-%d')
stamp=$(date -d "$today" '+%b %-d')
if grep -q '^GO ' "$OUT"; then
    summary="Next good night: $(grep -m1 '^GO ' "$OUT" | sed 's/^GO //')"
else
    summary="No GO nights in the latest forecast."
fi
cat >"$INCLUDE" <<EOF
<p class="notice--info"><strong>Forecast updated $stamp:</strong> $summary</p>
<p class="small">Weather data: <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0). Forecast guidance only — check the sky before heading out.</p>
EOF

# Keep the post's displayed date in step with today's forecast update.
if [ -f "$ABOUT" ]; then
    sed -i -E "s/^date: .*/date: $today/" "$ABOUT"
fi

# 4. Commit and push only the published files (never sweep in other staged work).
publish=(images/month.png "$INCLUDE")
[ -f "$ABOUT" ] && publish+=("$ABOUT")
git -C "$REPO" add "${publish[@]}"
if ! git -C "$REPO" diff --cached --quiet -- "${publish[@]}"; then
    if git -C "$REPO" commit --only -m "Update stargazing forecast ($stamp)" -- "${publish[@]}" >>"$OUT" 2>&1; then
        if ! git -C "$REPO" push origin main >>"$OUT" 2>&1; then
            echo "WARNING: forecast committed locally but git push failed." >>"$OUT"
        fi
    else
        echo "WARNING: forecast generated but git commit failed." >>"$OUT"
    fi
fi
