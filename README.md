# email optimization

This repository contains `email_optimization.py`, a script that summarizes and organizes emails.

Quick start (macOS / zsh):

1. Create and activate a virtual environment and install dependencies:

```bash
cd /Users/test/Desktop/dev/emails
./setup_venv.sh
source .venv/bin/activate
```

2. Run the script:

```bash
python email_optimization.py
```

Notes:
- `requirements.txt` includes common NLP and ML libraries used in the script. If you have local custom modules (like `email_parser`), ensure they are in the same folder or installed into the venv.
- The venv folder is `.venv` and is ignored by `.gitignore`.
