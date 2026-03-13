#!/bin/zsh

## Daily summary wrapper script ##

set -euo pipefail

# Change path
cd /Users/test/dev/emails

# Log everything
exec >> /Users/test/dev/emails/summary.log 2>> /Users/test/dev/emails/summary.error.log

echo "---- run_email_pipeline.sh START $(date) ---"

# Load env vars
set -a # export all variables that get defined
source .env # load env variables
set +a # stop exporting everying

# Activate venv
source .venv/bin/activate

# Optional: Uncomment this for first run
# Install dependencies if any
# python3 -m pip install -r requirements.txt 

# Daily summary (previous day only)
python3 src/email_optimization.py --summarize --no-trash

echo "--- run_email_pipeline.sh END $(date) ---"
