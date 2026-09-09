# Technical decisions

## Decision 1 — Fix compose target port to 80, keep nginx `listen 80`
- Choice: Changed `docker-compose.yml` nginx mapping `...:81` → `...:80` instead of changing `listen` to 81.
- Why: 80 is the NGINX/image default; least surprise for reviewers and tooling.
- Alternative: `listen 81` in nginx.conf. Equally functional once matched.
- Trade-off: Touches the host-facing mapping rather than app config; either one-line fix works.
- Evidence / commit: `0611ce8`, verified `curl http://127.0.0.1:8080/` 200.
- Production improvement: Fixed port is fine for the lab; production terminates TLS at a load balancer anyway.

## Decision 2 — Failover via `proxy_next_upstream` + `max_fails=3 fail_timeout=10s`
- Choice: Retry `error timeout http_502 http_503` on the other backend; bench a failing peer for 10s after 3 fails.
- Why: Historical logs prove the value — 19/19 retried requests succeeded; 40 identical ones failed only because retry was `off`.
- Alternative: Active health-checked load balancer (Consul/haproxy) or client-side retries.
- Trade-off: Retries can amplify load and are unsafe for non-idempotent POSTs; all retried paths here are idempotent GETs except POST /records (never retried in practice since both backends share one DB).
- Evidence / commit: `b486e68`, `failure_test.py` 30/30 during outage.
- Production improvement: Retry budgets, hedging, and per-route retry policies.

## Decision 3 — Secrets via ignored `.env`, never in image or compose
- Choice: `POSTGRES_PASSWORD` only from `${POSTGRES_PASSWORD:?...}`; `DATABASE_URL` assembled in compose; deleted `config/app.env` and its `COPY` into the image; `.env.example` documents placeholders.
- Why: Starter baked the DB password into the image layer and hardcoded it in compose — visible to anyone with image/repo access.
- Alternative: Docker secrets / Vault / cloud secret manager.
- Trade-off: Local boot now requires `cp .env.example .env`; CI does it automatically. A password change needs a volume re-init (`down -v` + restore) since Postgres pins it at init.
- Evidence / commit: hardening commit, `docker compose config` fails fast without `.env`.
- Production improvement: Managed secret store with rotation; distinct credentials per environment.

## Decision 4 — Redis AOF persistence on a named volume
- Choice: `redis-server --appendonly yes --save "60 1"` with `redis-data:/data` instead of `--save "" --appendonly no` and no volume.
- Why: Counter state otherwise evaporates on every recreation; AOF with a 60s/1-change snapshot is cheap durability for lab scale.
- Alternative: RDB only, or no persistence (acceptable if counter is treated as ephemeral).
- Trade-off: Small write amplification and slower restarts vs total loss; AOF rewrite tuning left at defaults.
- Evidence / commit: hardening commit, `redis-data` volume created on boot.
- Production improvement: Redis Sentinel/Cluster + persistence + eviction policy matched to workload.

## Decision 5 — `mem_limit`/`cpus` instead of `deploy.resources`
- Choice: Per-service `mem_limit`/`cpus` (apps 256m/0.5, postgres 512m/1.0, redis 256m/0.5, nginx 128m/0.5).
- Why: `deploy.resources` is ignored by `docker compose up` without Swarm; `mem_limit` is actually enforced here.
- Alternative: Swarm/Kubernetes requests+limits.
- Trade-off: Values are assessment-sized guards, not load-tested rightsizing; too-low limits would OOM under real traffic.
- Evidence / commit: hardening commit, `docker stats` stays within caps during validate + failure test.
- Production improvement: Load-test, then set requests/limits with HPA and OOM alerts.

## Decision 6 — Python stdlib for validate/failure scripts, no new dependencies
- Choice: `validate.py`/`failure_test.py` use only `urllib`, `json`, `subprocess`.
- Why: Zero install friction in CI and on the student's machine; no supply-chain additions for test tooling.
- Alternative: pytest/requests/httpx suite with richer assertions.
- Trade-off: More verbose code, sequential requests only; fine for 60 bounded requests.
- Evidence / commit: `23830fd`, `54787f0`, green CI in 1m12s.
- Production improvement: Proper test framework with parallel load generation and latency histograms.

## Decision 7 — Base images: keep starter pins (python:3.12-slim, postgres:16-alpine, redis:7.4-alpine, nginx:1.28-alpine)
- Choice: Did not change base images or digests; fixed how they are used (non-root user, healthchecks, persistence).
- Why: Pins are recent and already digest-locked; `slim`/`alpine` keep the attack surface and pull size small; stdlib-only healthchecks (`urllib`, `pg_isready`, `redis-cli`, `wget`) already exist in the images.
- Alternative: Distroless/chainguard images for the app.
- Trade-off: Keeps glibc/musl compatibility risk where it was; assessment scope favors stability over re-platforming.
- Evidence / commit: `Dockerfile` (`USER app`), compose healthchecks, all `healthy` in `docker compose ps`.
- Production improvement: Minimal-base rebuild, digest automation (Renovate/Dependabot), signed images.

## Assumptions and limits
- Single Docker host, localhost-only traffic, synthetic lab credentials, assessment-scale load.
- Log fixtures are historical training data, not live incidents; timeout/memory values are reasoned, not load-tested.
