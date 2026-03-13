#!/bin/zsh

## Weekly trash wrapper script ##

set -euo pipefail

# Change path
cd /Users/test/dev/emails

# Log everything
exec >> /Users/test/dev/emails/trash.log 2>> /Users/test/dev/emails/trash.error.log

echo "--- run_trash_weekly.sh START $(date) ---"

# Load env vars
set -a
source .env
set +a

# Activate venv if you use it
source .venv/bin/activate

# Optional: Uncomment this for first run
# Install dependencies if any
# python3 -m pip install -r requirements.txt

# Weekly trash
python3 src/email_optimization.py --no-summarize --trash --trash-query "in:inbox newer_than:7d"

echo "---run_weekly_trash.sh END $(date) ---"