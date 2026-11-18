#!/bin/sh
# Start the research agent. Reads .env if present.
cd "$(dirname "$0")"
exec python3 app.py
