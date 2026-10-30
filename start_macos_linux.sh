#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  cp .env.example .env
  echo 'Created .env. Set ADMIN_PASSWORD to enable admin access.'
fi
exec python3 server.py
