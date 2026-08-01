#!/usr/bin/env sh
set -eu

port="${PORT:-5000}"
curl --fail --silent --show-error "http://127.0.0.1:${port}/api/health"
