#!/usr/bin/env bash
# Run skycheck.py, publish the newest forecast graphic to the site, and email it.
# Intended for cron: 0 5 * * * /home/user/ethos101.github.io/_scripts/run_skycheck.sh
set -uo pipefail

REPO="/home/user/ethos101.github.io"
SCRIPT_DIR="$REPO/_scripts"
OUT="$SCRIPT_DIR/out.log"
MAIL_TO="ethos101@gmail.com"
MAIL_FROM="ethos101@gmail.com"

cd "$SCRIPT_DIR" || exit 1

# 1. Generate the forecast (skycheck.py bootstraps its own venv on first run).
./skycheck.py >"$OUT" 2>&1
status=$?
if [ "$status" -ne 0 ]; then
    echo "skycheck.py failed with status $status" >>"$OUT"
    mailx -r "$MAIL_FROM" -s "Observatory Go/No-go FAILED" "$MAIL_TO" <"$OUT"
    exit "$status"
fi

# 2. Publish the newest monthly graphic at the stable path used by the post.
latest=$(ls -t "$SCRIPT_DIR"/month_*.png 2>/dev/null | head -n1)
if [ -n "$latest" ]; then
    cp "$latest" "$REPO/images/month.png"
    if ! git -C "$REPO" diff --quiet -- images/month.png; then
        git -C "$REPO" add images/month.png
        git -C "$REPO" commit -m "Update stargazing forecast ($(date +%Y-%m))" >>"$OUT" 2>&1
        git -C "$REPO" push origin main >>"$OUT" 2>&1 \
            || echo "WARN: git push failed; image is committed locally" >>"$OUT"
    fi
fi

# 3. Email the graphic.
mailx -r "$MAIL_FROM" -s "Observatory Go/No-go" \
    -A "$REPO/images/month.png" "$MAIL_TO" </dev/null >>"$OUT" 2>&1
