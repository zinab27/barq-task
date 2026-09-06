#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

WAIT_SECS="${RESTORE_WAIT:-60}"

if [[ $# -ne 1 ]]; then
  echo "usage: ./restore.sh <backup-file.sql>" >&2
  exit 2
fi
backup="$1"
if [[ ! -s "$backup" ]]; then
  echo "FAIL backup file missing or empty: $backup" >&2
  exit 1
fi

deadline=$((SECONDS + WAIT_SECS))
until docker compose exec -T postgres pg_isready -U barq_app -d barq_tasks >/dev/null 2>&1; do
  if ((SECONDS >= deadline)); then
    echo "FAIL postgres not ready within ${WAIT_SECS}s" >&2
    exit 1
  fi
  sleep 2
done

docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U barq_app -d barq_tasks -q -f - <"$backup" >/dev/null

count="$(docker compose exec -T postgres psql -tA -U barq_app -d barq_tasks -c 'SELECT count(*) FROM records;')"
if [[ "$count" =~ ^[0-9]+$ ]] && ((count > 0)); then
  echo "PASS restore from $backup verified (${count} records)"
else
  echo "FAIL restore verification, records count: $count" >&2
  exit 1
fi
