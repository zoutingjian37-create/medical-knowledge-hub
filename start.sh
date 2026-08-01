#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"
exec python -m uvicorn app:app --host 127.0.0.1 --port "${PORT:-5000}"
