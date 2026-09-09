# BARQ DevOps Task — Fixed Environment

Flask API (app-01, app-02) behind NGINX on `http://127.0.0.1:8080`, with PostgreSQL + Redis on an isolated backend network. All starter faults investigated in `troubleshooting.md`, log evidence in `log_analysis.md`.

## Prerequisites

Linux/WSL2, Docker with Compose v2, Python 3, Git. Free names: app-01, app-02, nginx, postgres, redis. Free port 8080.

Video end-state: the recording moves the public port 8080 → 8090 (`PUBLIC_PORT=8090`) and adds a third backend `app-03`; `architecture.png` depicts that final state.

## Setup

```bash
git clone <your-repo-url> && cd barq-task
cp .env.example .env
```

Edit `.env` and set `POSTGRES_PASSWORD`. Any value works on a fresh volume; to keep an existing volume you must reuse the password it was initialized with.

## Build and start

```bash
docker compose config
docker compose up -d --build
sleep 20
docker compose ps
curl -s http://127.0.0.1:8080/ready
```

All five containers must be `healthy`. Only nginx publishes a host port (`127.0.0.1:8080->80`).

## Stop

```bash
docker compose stop        # stop, keep containers and volumes
docker compose down        # remove containers, KEEP volumes (safe for data)
```

Never use `down -v` unless you intend to delete the database. Never run `./video_challenge.sh` outside the recording.

## Endpoints

| Method | Path | Meaning |
|---|---|---|
| GET | `/` | app message |
| GET | `/health` | process liveness, no dependencies |
| GET | `/ready` | 200 only when PostgreSQL + Redis both ready |
| GET | `/instance` | backend identity (`app-01`/`app-02`) |
| GET/POST | `/records` | list / create `{"title": "..."}` PostgreSQL records |
| GET | `/counter` | Redis-backed incrementing counter |

```bash
curl -s http://127.0.0.1:8080/health
curl -s http://127.0.0.1:8080/ready
for i in $(seq 1 6); do curl -s http://127.0.0.1:8080/instance; echo; done
curl -s http://127.0.0.1:8080/records
curl -s -X POST http://127.0.0.1:8080/records -H 'Content-Type: application/json' -d '{"title":"demo"}'
curl -s http://127.0.0.1:8080/counter
```

## Test

```bash
python3 validate.py       # 11 checks, exits 1 on any FAIL
python3 failure_test.py   # stops app-02, measures 30 requests, restores, proves recovery
python -m unittest discover -s tests -v   # app-only unit tests (fake deps)
```

CI (`.github/workflows/ci.yml`, push + PR): syntax/compose checks → build → start → wait for readiness → validate → failure test → informational image scan.

## Backup, restore, persistence proof

```bash
./backup.sh
docker compose exec -T postgres psql -U barq_app -d barq_tasks -c 'DROP TABLE IF EXISTS records;'
./restore.sh "backups/$(ls -t backups/ | head -1)"
curl -s http://127.0.0.1:8080/records
docker compose up -d --force-recreate app-01 app-02 postgres
sleep 15
curl -s http://127.0.0.1:8080/records
```

Records must survive both restore and container recreation (named `postgres-data` volume).

## Cleanup

```bash
docker compose down
docker volume ls | grep barq
```

## Questions

**What failed first? What proved the cause? Which failed attempt taught you something?**
First live failure was `502 Bad Gateway` on every public request: `APP_HOST=127.0.0.1` bound Flask to container loopback so NGINX could never connect. Proved by `docker compose exec nginx wget http://app-01:8080/health` failing while the app's own healthcheck passed. Most instructive wrong turn: counting raw log lines as requests — 5 access + 49 application duplicate lines and 19 single-line proxy retries forced dedup by `request_id` (720 distinct, not 725).

**What patterns did the logs reveal? How did you avoid double-counting requests?**
Three non-overlapping episodes: 11:05–11:09 app-02 connection-refused (40x 502, 19 retried-ok), 11:12–11:21 Redis timeouts (31x) + Postgres auth failures (16x) as 503s on both backends, 11:25–11:26 `/records` slower than the proxy timeout (8x 504). Dedup: first-wins by `request_id`; a comma-separated `upstream` in one line is one retried request, not two. Cross-check: 720 access IDs − 680 app IDs = exactly the 40 never-reached 502s.

**How do requests flow? Why these ports, networks and readiness checks?**
Client → `127.0.0.1:8080` → nginx container `:80` → `app-01:8080`/`app-02:8080` round-robin with retry on 502/503. Port 80 is the NGINX default (starter mapped 81 by mistake). `frontend` carries client traffic only; `backend` is `internal:true` so Postgres/Redis are unreachable from outside and NGINX cannot reach them at all. `/health` is liveness (no dependencies, safe for auto-restart decisions); `/ready` gates traffic on both dependencies.

**Why these timeouts, retries, restart settings and resource limits?**
2s connect / 3s read matches the app's own 2s dependency timeouts so the proxy gives up just after the app would; `proxy_next_upstream error timeout http_502 http_503` + `max_fails=3 fail_timeout=10s` retries a dead backend once then benches it for 10s. `unless-stopped` recovers from crashes without resurrecting intentionally stopped containers. Limits (apps 256m/0.5, postgres 512m/1.0, redis 256m/0.5, nginx 128m/0.5) are assessment-sized guards against runaway memory, not production tuning.

**When should validation fail? What does green CI prove, or not prove?**
`validate.py` exits 1 on any FAIL: unreachable public URL, any endpoint non-200/wrong body, missing backend identity, unready dependency, wrong networks, or any published DB/app port. Green CI proves a fresh checkout builds, becomes ready within ~2 minutes, and passes all 11 checks plus the failure test on the runner. It does not prove persistence across `down -v`, production load behavior, image vulnerabilities (scan is informational), or secrets handling beyond `.env` presence.

**Which single points of failure remain? How would you fix them in production?**
NGINX (one replica — run 2+ behind a load balancer or keepalived), PostgreSQL (single node, volume on one host — managed Postgres or streaming replica + PITR), Redis (single node, AOF on one volume — Sentinel or Cluster), one Docker host (multi-node Swarm/Kubernetes across AZs).

**What would you improve? How did you verify AI-assisted work?**
Managed Postgres/Redis, TLS at the edge, structured log shipping, metrics/alerts, non-latest pinned digests with Dependabot, read-only root filesystems. See `AI_USAGE.md`: every AI suggestion was re-typed or reviewed, executed locally, and only committed after `validate.py` / `failure_test.py` passed — see the verify commits.

## Map

- `docker-compose.yml`, `Dockerfile`, `nginx/nginx.conf`, `app/server.py` — runtime
- `validate.py`, `failure_test.py`, `backup.sh`, `restore.sh` — Part 3 scripts
- `troubleshooting.md`, `log_analysis.md`, `decisions.md`, `security_review.md`, `AI_USAGE.md` — reports
- `docs/EVIDENCE_INDEX.md` — requirement → evidence map
