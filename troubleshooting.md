# Troubleshooting journal

## Entry 1: NGINX listens on wrong port — host cannot reach container
- Date: 2026-09-06 (static analysis, not yet fixed)
- Symptom: Host port 8080 forwards to container port 81, but NGINX listens on 80. All public traffic gets connection refused.
- Hypothesis: Mismatch between compose `ports` target and nginx `listen`.
- Command or test:
  ```bash
  grep -n "listen" nginx/nginx.conf
  grep -n "ports:" docker-compose.yml
  ```
- Actual output: `listen 80;` vs `ports: ["127.0.0.1:${PUBLIC_PORT:-8080}:81"]` — target 81 never listened on.
- Failed attempt and what changed your thinking: No failed attempt — visible on first side-by-side diff of both files.
- Root cause: `nginx.conf` listens on 80, compose forwards to 81.
- Fix: Change compose target to `80`, or `listen` to `81`. Prefer compose `...:80` to keep nginx default.
- Retest evidence: (pending) `curl -v http://127.0.0.1:8080/` returns 200 via nginx.
- Related commit: (pending fix commit)
- Remaining uncertainty: None.

## Entry 2: PostgreSQL connection fails — wrong port and password
- Date: 2026-09-06 (static analysis, not yet fixed)
- Symptom: application.log shows `InvalidPassword` errors on both app instances during 11:20-11:21. PostgreSQL container runs on default port 5432.
- Hypothesis: `DATABASE_URL` in `config/app.env` disagrees with compose postgres service.
- Command or test:
  ```bash
  cat config/app.env
  grep -n "POSTGRES_\|5432" docker-compose.yml
  ```
- Actual output: `DATABASE_URL=postgresql://barq_app:BarqLabOnly_7qN2vK8d@postgres:5433/barq_tasks` vs compose `POSTGRES_PASSWORD: BarqLabOnly_7qN2vK8c` and internal `5432`. Port off by one, password last char `d` vs `c`.
- Failed attempt and what changed your thinking: First saw only port 5433 vs 5432; char-by-char diff of passwords revealed second bug.
- Root cause: Two typos in `config/app.env`.
- Fix: Change to `postgresql://barq_app:BarqLabOnly_7qN2vK8c@postgres:5432/barq_tasks`.
- Retest evidence: (pending) `curl localhost:8080/ready` shows `"postgres":"ready"`.
- Related commit: (pending fix commit)
- Remaining uncertainty: None.

## Entry 3: Redis connection fails — wrong port
- Date: 2026-09-06 (static analysis, not yet fixed)
- Symptom: application.log shows `TimeoutError` on Redis for both instances during 11:12-11:15. Redis runs on default port 6379.
- Hypothesis: `REDIS_URL` points at wrong port.
- Command or test:
  ```bash
  cat config/app.env
  docker ps --filter "name=redis" --format "{{.Names}}: {{.Ports}}"  ```
- Actual output: `REDIS_URL=redis://redis:6380/0` but redis service exposes default `6379`, no remap.
- Failed attempt and what changed your thinking: No failed attempt — checked compose for custom port mapping first, none exists.
- Root cause: Typo `6380` instead of `6379`.
- Fix: Change to `redis://redis:6379/0`.
- Retest evidence: (pending) `curl localhost:8080/counter` returns incrementing counter.
- Related commit: (pending fix commit)
- Remaining uncertainty: None.

## Entry 4: PostgreSQL data not persisted — wrong volume path + tmpfs
- Date: 2026-09-06 (static analysis, not yet fixed)
- Symptom: Records from `/records` disappear after `docker compose recreate postgres`.
- Hypothesis: Named volume mounted where postgres never writes, plus tmpfs wipes data dir.
- Command or test:
  ```bash
  grep -n "volumes:\|tmpfs\|postgres-data" docker-compose.yml
  ```
- Actual output: `- postgres-data:/var/lib/postgresql/backup` (should be `/var/lib/postgresql/data`) plus `tmpfs: [/var/lib/postgresql/data]` which hides any mount with RAM disk.
- Failed attempt and what changed your thinking: First blamed only tmpfs; re-reading mount path showed volume was also wrong even without tmpfs.
- Root cause: Wrong mount path + tmpfs over data dir.
- Fix: Remove `tmpfs` line, change to `postgres-data:/var/lib/postgresql/data`.
- Retest evidence: (pending) create record, `docker compose up -d --force-recreate postgres`, record still listed.
- Related commit: (pending fix commit)
- Remaining uncertainty: None.

## Entry 5: app-02 reports wrong identity (both say app-01)
- Date: 2026-09-06 (static analysis, not yet fixed)
- Symptom: In plain words: we run 2 app containers but they both claim to be the same one. `GET /instance` always returns `{"instance_id":"app-01"}`, never `app-02`. So you cannot prove traffic hits both backends.
- Hypothesis: Copy-paste error — app-02 was given app-01's name in `docker-compose.yml`. The app itself just prints whatever `INSTANCE_ID` env var it gets (see `app/server.py:51`).
- Command or test:
  ```bash
  grep -n "INSTANCE_ID" docker-compose.yml
  # app-01 block -> INSTANCE_ID: "app-01"  (correct)
  # app-02 block -> INSTANCE_ID: "app-01"  (wrong, should be "app-02")
  grep -n "INSTANCE_ID" app/server.py
  # line 51: INSTANCE_ID=os.getenv("INSTANCE_ID","local") -> proves app trusts the env var
  ```
- Actual output: Both services set `"app-01"`. Live `/instance` after `docker compose up` can never show `app-02`.
- Note on logs vs live config: `logs/application.log` DOES show `instance_id: app-02` with 200 OK (e.g. lab-000002, lab-000004). That is expected — logs are synthetic history from a time when config was correct (see `logs/README.md`: "historical incident, not the current environment"). Current `docker-compose.yml` has the bug; logs show what correct behaviour looked like.
- Failed attempt and what changed your thinking: No failed attempt — checked app code first to be sure the ID comes from env, not hostname, then blamed compose.
- Root cause: `docker-compose.yml:59` duplicates `app-01` ID for `app-02`.
- Fix: In `app-02` block only, change to `INSTANCE_ID: "app-02"`.
- Retest evidence: (pending) run `for i in 1 2 3 4; do curl -s http://127.0.0.1:8080/instance; done` — must see both `app-01` and `app-02` across repeats, matching the historical log pattern.
- Related commit: (pending fix commit)
- Remaining uncertainty: None.

## Entry 6: Healthcheck always unhealthy — wrong endpoint
- Date: 2026-09-06 (static analysis, not yet fixed)
- Symptom: `docker ps` would show `unhealthy` for app containers.
- Hypothesis: Healthcheck path does not exist in Flask.
- Command or test:
  ```bash
  grep -n "healthcheck" -A2 docker-compose.yml
  grep -n "@app.get" app/server.py
  ```
- Actual output: healthcheck calls `/healthz`, app defines `/health`, `/ready`, `/`, `/instance`, `/records`, `/counter` — no `/healthz`, returns 404.
- Failed attempt and what changed your thinking: No failed attempt — route list proves it.
- Root cause: Typo `/healthz` vs `/health`.
- Fix: Change healthcheck URL to `http://127.0.0.1:8080/health` (also fix APP_HOST below so probe binds correctly).
- Retest evidence: (pending) `docker inspect app-01 --format '{{.State.Health.Status}}'` shows `healthy`.
- Related commit: (pending fix commit)
- Remaining uncertainty: None.

## Entry 7: Container runs as root
- Date: 2026-09-06 (static analysis, not yet fixed)
- Symptom: `whoami` inside app container returns `root`, violates least-privilege.
- Hypothesis: Dockerfile `USER` directive undoes app user.
- Command or test:
  ```bash
  grep -n "USER\|useradd\|chown" Dockerfile
  ```
- Actual output: creates `app` uid 10001, `COPY --chown=app:app`, then `USER root`.
- Failed attempt and what changed your thinking: No failed attempt — last `USER` wins, clearly `root`.
- Root cause: Stray `USER root`.
- Fix: Change to `USER app`. Needs `curl` or `wget` or python healthcheck usable by non-root (python is fine).
- Retest evidence: (pending) `docker compose exec app-01 whoami` returns `app`.
- Related commit: (pending fix commit)
- Remaining uncertainty: Whether image has `urllib` only (yes, stdlib) so non-root probe still works.

## Entry 8: No failover — single backend failure returns 502
- Date: 2026-09-06 (log evidence 2026-08-20 11:05-11:09)
- Symptom: `error.log` 59x `connect() failed (111) to 172.23.0.12:8080`, `access.log` 502s whenever round-robin hits app-02. `application.log` stops for app-02 after 11:05:00.
- Hypothesis: `proxy_next_upstream off` + `max_fails=0` disables retry.
- Command or test:
  ```bash
  grep -n "proxy_next_upstream\|max_fails" nginx/nginx.conf
  grep -c '"status":502' logs/access.log
  grep -c "Connection refused" logs/error.log
  python3 -c "import json; rows=[json.loads(l) for l in open('logs/access.log')]; print(len({r['request_id'] for r in rows}), len(rows))"
  ```
- Actual output: `proxy_next_upstream off;`, `max_fails=0` on both upstreams; ~59 unique 502s; 3 duplicate request_ids (`lab-000121, lab-000181, lab-000241`) so raw line count overcounts by 3.
- Failed attempt and what changed your thinking: First counted lines as requests; dedup by `request_id` showed 3 duplicates — must dedup to avoid double-counting.
- Root cause: app-02 down 11:05:02–11:09:57 + nginx configured never to retry other upstream.
- Fix: `proxy_next_upstream error timeout http_502;` and `max_fails=3 fail_timeout=10s`.
- Retest evidence: (pending) `docker stop app-02`, repeated curls still 200, `docker start app-02`.
- Related commit: (pending fix commit)
- Remaining uncertainty: None on nginx part; app-02 crash cause is out of scope (synthetic fixture).

## Entry 9: DB/Redis ports published + restart disabled
- Date: 2026-09-06 (static analysis, not yet fixed)
- Symptom: Task forbids publishing app/DB/cache ports, requires restart policies. Compose violates both.
- Hypothesis: Extra `ports` on stateful services, `restart: "no"`.
- Command or test:
  ```bash
  grep -n 'ports:\|restart:' docker-compose.yml
  grep -n "networks:" -A3 docker-compose.yml | head -20
  ```
- Actual output: `ports: ["127.0.0.1:15432:5432"]`, `ports: ["127.0.0.1:16379:6379"]`, `restart: "no"`, nginx on both `frontend, backend`.
- Failed attempt and what changed your thinking: No failed attempt — task text vs compose diff is direct.
- Root cause: Leftover debug ports, missing restart policy, nginx attached to backend.
- Fix: Remove postgres/redis `ports`, set `restart: unless-stopped`, keep nginx on `frontend` only.
- Retest evidence: (pending) `docker ps --format '{{.Names}} {{.Ports}}'` shows only `127.0.0.1:8080->80` on nginx.
- Related commit: (pending fix commit)
- Remaining uncertainty: None.
