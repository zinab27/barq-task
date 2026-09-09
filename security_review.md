# Security and production-readiness review

## 1. DB password hardcoded in compose and baked into the image — FIXED
- Risk and evidence: `POSTGRES_PASSWORD` was hardcoded in `docker-compose.yml` and `DATABASE_URL` (with password) was `COPY`d into the image via `config/app.env`. Anyone with repo or image access owned the database.
- Impact: Full DB read/write on any leaked checkout or pushed image layer.
- Implemented fix / commit: Password only from ignored `.env` (`${POSTGRES_PASSWORD:?...}` fail-fast), `DATABASE_URL` assembled at runtime, `config/app.env` + image `COPY` deleted (hardening commit).
- Production follow-up: Secret manager with rotation; per-environment credentials.
- How to verify: `grep -r BarqLabOnly --include='Dockerfile' --include='*.yml' .` returns nothing; `docker compose config` errors without `.env`.

## 2. Containers ran as root — FIXED
- Risk and evidence: `Dockerfile` ended with `USER root`, discarding the created `app` user.
- Impact: A Flask RCE would land as container root, easing host-escape chaining.
- Implemented fix / commit: `USER app` (`5b6bd0e`); healthcheck uses stdlib `urllib`, no root needed.
- Production follow-up: Read-only root filesystem, dropped capabilities, seccomp profile.
- How to verify: `docker compose exec app-01 whoami` → `app`.

## 3. Database and cache ports published to the host — FIXED
- Risk and evidence: Compose published `15432:5432` and `16379:6379` on loopback; any local process could reach the DB.
- Impact: Credential-stuffing and data theft from local malware/other users.
- Implemented fix / commit: `ports` removed (`0611ce8`); backend network is `internal:true`.
- Production follow-up: No public listeners at all; access via bastion/VPC peering with mTLS.
- How to verify: `validate.py` host-ports check; `docker ps` shows ports only on nginx.

## 4. NGINX attached to the backend network — FIXED
- Risk and evidence: `nginx` was on both `frontend` and `backend`, so a compromised edge could reach Postgres/Redis directly.
- Impact: Larger blast radius from the most exposed container.
- Implemented fix / commit: nginx on `frontend` only (hardening lineage from `0611ce8`).
- Production follow-up: Egress policies per workload (K8s NetworkPolicy/service mesh).
- How to verify: `validate.py` network-isolation check.

## 5. No proxy failover; dead backend served 502s — FIXED
- Risk and evidence: `proxy_next_upstream off` + `max_fails=0`; logs show 40 user-visible 502s that retries would have saved (19/19 retried succeeded).
- Impact: Single-backend outage = ~50% user errors instead of ~0%.
- Implemented fix / commit: `proxy_next_upstream error timeout http_502 http_503`, `max_fails=3 fail_timeout=10s` (`b486e68`).
- Production follow-up: Retry budgets, circuit breakers, multi-replica edge.
- How to verify: `failure_test.py` — 30/30 during backend stop.

## 6. PostgreSQL data could evaporate — FIXED
- Risk and evidence: Volume mounted at `/var/lib/postgresql/backup` (unused path) plus `tmpfs` over `/var/lib/postgresql/data`.
- Impact: Total data loss on every container recreate.
- Implemented fix / commit: `postgres-data:/var/lib/postgresql/data`, tmpfs removed (`0611ce8`); `backup.sh`/`restore.sh` proven (`bcb5f41`).
- Production follow-up: Off-host backups, PITR, restore drills on schedule.
- How to verify: Recreate postgres, records persist; `./backup.sh` + `./restore.sh` round-trip.

## 7. Redis had zero durability — FIXED
- Risk and evidence: `--save "" --appendonly no`, no volume; counter reset on every restart.
- Impact: Silent state loss; rate-limit/counter semantics unreliable.
- Implemented fix / commit: AOF + `save 60 1` on named `redis-data` volume (hardening commit).
- Production follow-up: Sentinel/Cluster, eviction + memory policy review.
- How to verify: `docker volume ls | grep redis-data`; recreate redis, counter continues.

## 8. Pinned images without scanning or updates — PARTIALLY FIXED
- Risk and evidence: Digests are pinned (good) but nothing checks them for CVEs or refreshes them.
- Impact: Known-vulnerable base layer ships silently.
- Implemented fix / commit: Informational Trivy fs scan in CI (`7265387`, `continue-on-error`).
- Production follow-up: Blocking threshold, Dependabot/Renovate digest bumps, image signing (cosign).
- How to verify: Actions run shows the scan step; promote it to blocking after triage.

## 9. No TLS, single edge replica, single host — PLANNED (out of lab scope)
- Risk and evidence: Plain HTTP, one nginx, one Postgres, one Redis, one Docker host.
- Impact: Eavesdropping on any non-loopback path; any component loss is an outage.
- Implemented fix / commit: Loopback-only publishing + `unless-stopped` restarts mitigate locally only.
- Production follow-up: TLS at LB/edge, 2+ edge replicas, managed Postgres with replica + PITR, Redis Sentinel/Cluster, multi-AZ nodes.
- How to verify: Architecture review + chaos drills (kill each component, measure).

## 10. Flat observability: logs only, no metrics or alerts — PLANNED
- Risk and evidence: JSON logs exist but nothing aggregates, alerts, or traces slow `/records` (the 11:25 504 pattern would recur silently).
- Impact: Outages found by users, slow dependency drift invisible.
- Implemented fix / commit: `Cache-Control: no-store`, request-id propagation kept; nothing added.
- Production follow-up: Centralized logs, RED metrics per endpoint, `/ready`-based alerting, SLO on p95.
- How to verify: Dashboard + alert test demonstrating a failing `/ready` pages someone.
