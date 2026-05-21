#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

psql "$DATABASE_URL" -f "$ROOT_DIR/database/schema.sql"

if [[ "${IMPORT_SEED_DEV:-0}" == "1" ]]; then
  psql "$DATABASE_URL" -f "$ROOT_DIR/database/seed_dev.sql"
fi

echo "Imported schema${IMPORT_SEED_DEV:+ and optional seed data} into online PostgreSQL."
