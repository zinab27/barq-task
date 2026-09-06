#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

BACKUP_DIR="${BACKUP_DIR:-./backups}"
WAIT_SECS="${BACKUP_WAIT:-60}"

mkdir -p -- "$BACKUP_DIR"

deadline=$((SECONDS + WAIT_SECS))
until docker compose exec -T postgres pg_isready -U barq_app -d barq_tasks >/dev/null 2>&1; do
  if ((SECONDS >= deadline)); then
    echo "FAIL postgres not ready within ${WAIT_SECS}s" >&2
    exit 1
  fi
  sleep 2
done

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
out="${BACKUP_DIR}/backup-${stamp}.sql"

docker compose exec -T postgres pg_dump --clean --if-exists -U barq_app barq_tasks >"$out"

if [[ ! -s "$out" ]] || ! grep -q "CREATE TABLE" "$out"; then
  echo "FAIL backup at $out is empty or invalid" >&2
  exit 1
fi

echo "PASS backup written to $out ($(wc -l <"$out") lines)"
