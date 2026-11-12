#!/usr/bin/env bash
# Run skycheck.py, publish the forecast, and email it.
# Cron: 0 5 * * * /home/user/ethos101.github.io/_scripts/run_skycheck.sh
set -uo pipefail

REPO="/home/user/ethos101.github.io"
SCRIPT_DIR="$REPO/_scripts"
OUT="$SCRIPT_DIR/out.log"
INCLUDE="$REPO/_includes/forecast_status.html"
POST_URL="https://willowcreekobservatory.com/about/"
MAIL_TO="${SKYCHECK_MAIL_TO:-ethos101@gmail.com}"
MAIL_FROM="${SKYCHECK_MAIL_FROM:-ethos101@gmail.com}"
LOCK="/tmp/skycheck-$(id -u).lock"
BODY="/tmp/skycheck-mail-$(id -u).txt"

export TZ="America/Chicago"
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o BatchMode=yes}"

send_mail() {  # $1 subject, $2 body file, $3 optional attachment
    [ "${SKYCHECK_NO_MAIL:-0}" = "1" ] && return 0
    if [ -n "${3:-}" ]; then
        mailx -r "$MAIL_FROM" -s "$1" -A "$3" "$MAIL_TO" <"$2"
    else
        mailx -r "$MAIL_FROM" -s "$1" "$MAIL_TO" <"$2"
    fi
}

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
    send_mail "Observatory Go/No-go FAILED" "$OUT"
    exit "$status"
fi

# 2. Publish the newest monthly graphic at the stable path used by the post.
latest=$(ls -t "$SCRIPT_DIR"/month_*.png 2>/dev/null | head -n1)
if [ -z "$latest" ]; then
    echo "ERROR: no month_*.png produced" >>"$OUT"
    send_mail "Observatory Go/No-go FAILED" "$OUT"
    exit 1
fi
cp "$latest" "$REPO/images/month.png"

# 3. Write a short text summary for the post (so it isn't image-only).
stamp=$(date '+%b %-d')
if grep -q '^GO ' "$OUT"; then
    summary="Next good night: $(grep -m1 '^GO ' "$OUT" | sed 's/^GO //')"
else
    summary="No GO nights in the latest forecast."
fi
cat >"$INCLUDE" <<EOF
<p class="notice--info"><strong>Forecast updated $stamp:</strong> $summary</p>
<p class="small">Weather data: <a href="https://open-meteo.com/">Open-Meteo</a> (CC BY 4.0). Forecast guidance only — check the sky before heading out.</p>
EOF

# 4. Commit and push only the published files (never sweep in other staged work).
push_note=""
git -C "$REPO" add images/month.png "$INCLUDE"
if ! git -C "$REPO" diff --cached --quiet -- images/month.png "$INCLUDE"; then
    if git -C "$REPO" commit --only -m "Update stargazing forecast ($stamp)" -- images/month.png "$INCLUDE" >>"$OUT" 2>&1; then
        if ! git -C "$REPO" push origin main >>"$OUT" 2>&1; then
            push_note="WARNING: forecast committed locally but git push failed."
            echo "$push_note" >>"$OUT"
        fi
    else
        push_note="WARNING: forecast generated but git commit failed."
        echo "$push_note" >>"$OUT"
    fi
fi

# 5. Email the forecast text + graphic.
{
    echo "Forecast updated $stamp."
    echo
    cat "$OUT"
    [ -n "$push_note" ] && { echo; echo "$push_note"; }
    echo
    echo "Post: $POST_URL"
} >"$BODY"
send_mail "Observatory Go/No-go" "$BODY" "$REPO/images/month.png"
