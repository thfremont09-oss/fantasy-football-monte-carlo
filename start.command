#!/bin/bash
# Double-click this file on a Mac (or run ./start.command) to launch the app.
cd "$(dirname "$0")" || exit 1

PY=""
for cand in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$cand" >/dev/null 2>&1 && \
     "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is required."
  echo "Install it from https://www.python.org/downloads/macos/ (or: brew install python), then run this again."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up (about a minute)..."
  "$PY" -m venv .venv || { read -r -p "Could not create virtual environment. Press Enter to close..."; exit 1; }
fi
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/python -m pip install -q -r requirements.txt || { read -r -p "Install failed. Press Enter to close..."; exit 1; }

echo "Opening the app in your browser. Close this window (or press Ctrl+C) to stop it."
exec .venv/bin/python -m streamlit run app.py --browser.gatherUsageStats false
