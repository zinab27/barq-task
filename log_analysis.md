# Log analysis

All UTC. Originals unmodified. `request_time` seconds, `duration_ms` ms.
Correlated via `request_id` + `timestamp` + `upstream`/`instance_id`.

## Commands / scripts

```bash
wc -l logs/access.log logs/error.log logs/application.log
head -n 5 logs/access.log; head -n 5 logs/application.log; head -n 5 logs/error.log
sed -n '311p' logs/access.log; sed -n '401p' logs/application.log
grep -c "connect() failed" logs/error.log
grep -c "upstream timed out" logs/error.log
grep -c "request_id=" logs/error.log
```

```bash
python3 << 'PY'
import json, re, collections, statistics
from pathlib import Path
def load_json_valid(fn):
    valid, mal = [], []
    for i,l in enumerate(Path(fn).read_text().splitlines(),1):
        try:
            o=json.loads(l); assert 'timestamp' in o or 'event' in o
            valid.append((i,o))
        except Exception as e: mal.append((i,l[:120],str(e)[:80]))
    return valid, mal

# --- access.log ---
ava,ama=load_json_valid('logs/access.log')
by={}
for _,o in ava: by.setdefault(o['request_id'],o)
print('ACCESS valid',len(ava),'malformed',len(ama),'distinct',len(by))
print('  status',collections.Counter(o['status'] for o in by.values()))
lats=sorted(o['request_time'] for o in by.values())
print('  median',statistics.median(lats),'p95',sorted(lats)[int(len(lats)*0.95)])
ret=[o for o in by.values() if ',' in o['upstream']]
print('  retried',len(ret),'all 200 after retry:',all(o['status']==200 for o in ret))

# --- application.log ---
apa,pma=load_json_valid('logs/application.log')
events=[o for _,o in apa]
print('\nAPP valid',len(events),'malformed',len(pma))
print('  events',collections.Counter(e.get('event') for e in events))
print('  levels',collections.Counter(e.get('level') for e in events))
print('  instances',collections.Counter(e.get('instance_id') for e in events if 'instance_id' in e))
deps=[e for e in events if e.get('event')=='dependency_error']
print('  dependency_error',len(deps))
print('    by dep',collections.Counter(d['dependency'] for d in deps))
print('    by err',collections.Counter(d['error_type'] for d in deps))
print('    by minute',collections.Counter(d['timestamp'][:16] for d in deps).most_common(10))
https=[e for e in events if e.get('event')=='http_request']
print('  http_request',len(https),'status',collections.Counter(h['status'] for h in https))
# dedup by request_id keeping http_request only
app_by_id={}
for h in https: app_by_id.setdefault(h['request_id'],h)
print('  distinct req_ids (http only)',len(app_by_id))

# --- error.log ---
err_lines=Path('logs/error.log').read_text().splitlines()
print('\nERROR lines',len(err_lines))
connect=[l for l in err_lines if 'connect() failed' in l]
timeout=[l for l in err_lines if 'timed out' in l]
print('  connect refused',len(connect))
print('  upstream timed out',len(timeout))
# which upstream IPs
print('  .12 errors',sum('.12' in l for l in connect))
print('  .11 errors',sum('.11' in l for l in connect))
PY
```

## Results

### 1. Interval, valid / malformed / duplicates

| file | raw lines | valid JSON / pattern | malformed | duplicates | UTC interval |
|---|---|---|---|---|---|
| `logs/access.log` | 726 | 725 | 1 (line 311: `{"timestamp":"2026-08-20T11:12:48Z","request_id":` truncated, `json: Expecting value char 49`) | 5 extra lines, 5 IDs x2 identical: `lab-000121, lab-000241, lab-000361, lab-000481, lab-000601` (e.g. two byte-identical `lab-000121 @2026-08-20T11:05:00.055Z`) | `2026-08-20T11:00:00.015Z` .. `2026-08-20T11:29:57.578Z` |
| `logs/application.log` | 730 | 729 | 1 (line 401: `{"timestamp":"2026-08-20T11:17:00Z","event":` truncated, `Expecting value char 44`) | 49 IDs appear 2x = 49 extra lines, but 47 are legitimate pairs `dependency_error + http_request` same ID (not dupes); only 2 true identical dupes: `lab-000181 @11:07:30.035Z`, `lab-000421 @11:17:30.035Z`. Distinct `request_id`: 680 | `2026-08-20T11:00:00.015Z` .. `2026-08-20T11:29:57.578Z` |
| `logs/error.log` | 68 | 68 match `^\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2} \[(error\|notice)\]` (0 malformed, 0 duplicate lines) | 0 | 0 | `2026/08/20 11:05:02` .. `2026/08/20 11:30:00` (`[notice] log collector rotated stream`); errors only `11:05:02`..`11:26:47`. 67x `[error]` + 1x `[notice]` |

Output verified: `ACCESS valid 725 malformed 1 unique_ids 720 dup_extra 5`; `APP valid 729 malformed 1 unique_req_ids 680`; `ERROR valid_pattern 68 malformed 0 dup 0`.

### 2. Distinct client requests, dedup method

**720 distinct client requests.**

Method: `access.log` is client-facing truth. Group by `request_id`, keep first occurrence; drop 1 malformed + collapse 5 identical duplicates. Comma-separated `upstream`/`upstream_status` (e.g. `172.23.0.12:8080, 172.23.0.11:8080` / `502, 200`) is ONE client request with 2 upstream attempts — counted once. `application.log` `dependency_error + http_request` sharing one ID is ONE request with 2 events — not double-counted. `error.log` lines are NGINX diagnostics per attempt, not client requests. Verified: 725 valid - 5 dup extras = 720; 19 retried IDs each appear once in deduped set.

Avoided double-count: did not sum `access + application + error` lines (would be ~1522); did not count each upstream attempt separately; did not count retries as new IDs.

### 3. Final client status counts and error rate

Denominator = **720 distinct client requests** (not 726 raw / 725 valid lines).

Deduped (`request_id` unique):
`200: 615, 502: 40, 503: 47, 504: 8, 404: 10`

Raw valid (725) for comparison: `200: 620 (+5 dupes, all 200), 503: 47, 502: 40, 404: 10, 504: 8`.

Error rate (5xx only): **95/720 = 13.19%**. With 404 as failure: 105/720 = 14.58%. Per-code: 502 5.56%, 503 6.53%, 504 1.11%, 404 1.39%.

### 4. Paths, time windows, backends

Fail paths (deduped, 95x 5xx): `/records 26, /counter 26, /ready 23, /health 10, / 10`. Detail: `(/ready,503) 23, (/counter,503) 16, (/health,502) 10, (/records,502) 10, (/counter,502) 10, (/,502) 10, (/records,503) 8, (/records,504) 8`. `/instance` and `/missing` never 5xx; 404 only `/missing` (10x, spread 11:00-11:26).

Fail minutes (all 5xx): `11:05 8, 11:06 8, 11:07 8, 11:08 8, 11:09 8` (all 502); `11:12 8, 11:14 8, 11:15 8, 11:20 8, 11:21 8, 11:13 7` (all 503); `11:25 4, 11:26 4` (all 504 on `/records`). Healthy minutes (e.g. 11:00-11:04, 11:10-11:11, 11:16-11:19, 11:22-11:24, 11:27-11:29) 0x 5xx. Load steady ~24 req/min.

Backends (client `upstream` on fails): `172.23.0.12:8080: 68, 172.23.0.11:8080: 27`. `upstream_status` on fails: `503: 47, 502: 40, 504: 8` (mirrors client status — proxy faithfully returned upstream code). Success split: `.11 328, .12 268, retried .12->.11 19`. App side 503s balanced: `app-02 24, app-01 23` (redis phase), 504s both backends (`504 .12 x4, .11 x4`).

### 5. Median and p95 client latency

Units: `request_time` seconds (x1000 = ms). n=720 deduped, range 0.003–2.025s. Bimodal: fast path ~0.02–0.12s, stalled 2.001–2.025s (55x ~2s: 47x 503 + 8x 504).

- **median (50th, `statistics.median`) = 0.054 s (54 ms)**
- **p95 linear-interpolation (`k=(n-1)*p`) = 2.001 s (2001 ms); p95 nearest-rank (`ceil(0.95*720)=684th` sorted value) = 2.001 s (2001 ms)** — identical due to 2s plateau.

### 6. Upstream retries

**19 client requests retried upstream, all 19 succeeded (100%) as 200 with `upstream_status: "502, 200"`.**

All pattern `upstream: "172.23.0.12:8080, 172.23.0.11:8080"`, first attempt 502 on `.12`, failover to `.11`. Paths only `/ready x10, /instance x9`, window `11:05 x4, 11:06 x4, 11:07 x4, 11:08 x4, 11:09 x3`. No 503/504 request retried. Example: `lab-000124 @11:05:07.620Z /ready 200 (502,200) rt 0.12`. Non-retried 502s (40x `/health,/records,/counter,/`) returned 502 to client without second attempt.

### 7. Timeline (access + error + application)

**Summary of failure phases (5xx only):**

| Phase | UTC window | Status | Count | Root cause | error.log | app log |
|---|---|---|---|---|---|---|
| A | 11:05:02–11:09:57 | 502 | 40 | backend `.12` down | 59x `connect() failed (111)` | none (never reached app) |
| B | 11:12:09–11:15:52 | 503 | 31 | redis `TimeoutError` | 0 lines | `dependency_error redis TimeoutError` |
| C | 11:20:07–11:21:45 | 503 | 16 | postgres `InvalidPassword` | 0 lines | `dependency_error postgres InvalidPassword` |
| D | 11:25:14–11:26:47 | 504 | 8 | slow `/records` response | 8x `upstream timed out (110)` | `http_request 200 duration 2700ms` |

**Minute-by-minute breakdown (5xx):**

| Minute | 502 | 503 | 504 | Total 5xx | Paths affected |
|---|---|---|---|---|---|
| 11:05 | 8 | 0 | 0 | 8 | `/health /records /counter /` x2 each |
| 11:06 | 8 | 0 | 0 | 8 | `/health /records /counter /` x2 each |
| 11:07 | 8 | 0 | 0 | 8 | `/health /records /counter /` x2 each |
| 11:08 | 8 | 0 | 0 | 8 | `/health /records /counter /` x2 each |
| 11:09 | 8 | 0 | 0 | 8 | `/health /records /counter /` x2 each |
| 11:12 | 0 | 8 | 0 | 8 | `/ready x4 /counter x4` |
| 11:13 | 0 | 7 | 0 | 7 | `/counter x4 /ready x3` |
| 11:14 | 0 | 8 | 0 | 8 | `/ready x4 /counter x4` |
| 11:15 | 0 | 8 | 0 | 8 | `/ready x4 /counter x4` |
| 11:20 | 0 | 8 | 0 | 8 | `/ready x4 /records x4` |
| 11:21 | 0 | 8 | 0 | 8 | `/ready x4 /records x4` |
| 11:25 | 0 | 0 | 4 | 4 | `/records x4` |
| 11:26 | 0 | 0 | 4 | 4 | `/records x4` |

**Phase A detail — 11:05:02–11:09:57 (backend `.12` unreachable):**
- `error.log`: 59x `connect() failed (111: Connection refused) while connecting to upstream ... upstream: "http://172.23.0.12:8080/..."` (all .12, 0 on .11)
- `access.log`: 40x 502 (no retry, final to client) + 19x 200 with `upstream: ".12, .11" upstream_status: "502, 200"` (retried, all succeeded)
- `application.log`: NO records for the 40 pure-502 IDs (e.g. `lab-000122` absent) — proves request never reached app, failure is at proxy/dial level
- Paths retried: `/ready x10, /instance x9` (NGINX `proxy_next_upstream` triggered on these paths only)
- Paths NOT retried (returned 502 to client): `/health x10, /records x10, /counter x10, / x10`
- Minute 11:09 has 1 malformed line 311 in access.log (no status effect)

**Phase B detail — 11:12:09–11:15:52 (redis `TimeoutError`):**
- `application.log`: 31x `dependency_error dependency=redis error_type=TimeoutError` on both `app-01` (15x) and `app-02` (16x); each followed 1ms later by `http_request status=503 duration_ms=2025.0`
- `access.log`: 31x 503, all rt=2.025s, paths `/ready x15, /counter x16`
- `error.log`: 0 lines (upstream answered 503, not a dial failure — proxy returned what it got)
- `app-02` vs `app-01` balanced: redis was unreachable on both instances

**Phase C detail — 11:20:07–11:21:45 (postgres `InvalidPassword`):**
- `application.log`: 16x `dependency_error dependency=postgres error_type=InvalidPassword` on both `app-01` (8x) and `app-02` (8x); each followed by `http_request status=503 duration_ms=2025.0`
- `access.log`: 16x 503, all rt=2.025s, paths `/ready x8, /records x8`
- `error.log`: 0 lines (same reason as Phase B — upstream answered)
- Minute 11:17 has 1 malformed app line 401 (parse exclusion only)

**Phase D detail — 11:25:14–11:26:47 (slow `/records` → timeout):**
- `error.log`: 8x `upstream timed out (110: Operation timed out) while reading response header from upstream ... /records` alternating `.12 x4, .11 x4`
- `access.log`: 8x 504, all rt=2.001s, all path `/records`
- `application.log`: `http_request status=200 duration_ms=2700` for the SAME IDs AFTER client timeout (e.g. `lab-000606` client 504 @11:25:14, app 200 @11:25:15) — proves app succeeded but NGINX gave up at ~2s proxy timeout

**Healthy windows (0x 5xx):**
- 11:00:00–11:04:59 (120x 200), 11:10–11:11 (48x 200), 11:16–11:19 (96x 200), 11:22–11:24 (72x 200), 11:27–11:29 (72x 200)
- Load steady ~24 req/min throughout; no spike correlated with failures
- 11:30:00 `error.log [notice] log collector rotated stream` (end of incident window)

### 8. Correlated examples

Failed (connectivity-phase 503 with dependency proof):
- access: `{"timestamp":"2026-08-20T11:12:09.525Z","request_id":"lab-000292","method":"GET","path":"/ready","status":503,"upstream":"172.23.0.12:8080","upstream_status":"503","request_time":2.025}`
- app: `{"timestamp":"2026-08-20T11:12:09.524Z","level":"ERROR","event":"dependency_error","request_id":"lab-000292","instance_id":"app-02","dependency":"redis","error_type":"TimeoutError"}` + `{"timestamp":"2026-08-20T11:12:09.525Z","level":"WARN","event":"http_request","request_id":"lab-000292","instance_id":"app-02","method":"GET","path":"/ready","status":503,"duration_ms":2025.0}`
- error.log: no line for `lab-000292` (upstream answered, nothing to dial-fail).

Failed (proxy-phase 502, no app trace):
- access: `{"timestamp":"2026-08-20T11:05:02.503Z","request_id":"lab-000122","method":"GET","path":"/health","status":502,"upstream":"172.23.0.12:8080","upstream_status":"502","request_time":0.003}`
- error: `2026/08/20 11:05:02 [error] 31#31: *122 connect() failed (111: Connection refused) while connecting to upstream, request_id=lab-000122, request: "GET /health HTTP/1.1", upstream: "http://172.23.0.12:8080/health"`
- app: no `lab-000122` record (request never reached app).

Successful with retry:
- access: `{"timestamp":"2026-08-20T11:05:07.620Z","request_id":"lab-000124","method":"GET","path":"/ready","status":200,"upstream":"172.23.0.12:8080, 172.23.0.11:8080","upstream_status":"502, 200","request_time":0.12}`
- error: `2026/08/20 11:05:07 [error] ... request_id=lab-000124 ... upstream: "http://172.23.0.12:8080/ready"` (first-attempt fail, then failover)
- app: `{"timestamp":"2026-08-20T11:05:07.620Z","level":"INFO","event":"http_request","request_id":"lab-000124","instance_id":"app-01","method":"GET","path":"/ready","status":200,"duration_ms":120.0}` (served by surviving `.11/app-01`).

### 9. Proxy/connectivity vs dependency/application

Proxy/connectivity: 40x 502 + 19x retried-200, `error.log connect() failed (111 Connection refused) → .12` 11:05–11:09, `request_time ~0.003–0.12s`, no `application.log` entry for pure-502 IDs, `upstream_status 502` while app healthy. Proof: triple absence/presence (`error present + app absent + access 502`) = dial never completed; retry `502,200` proves failover healed it.

Dependency/application: 47x 503 + 8x 504. 503s have `app dependency_error (redis TimeoutError 31x, postgres InvalidPassword 16x)` + `http_request 503 duration 2025ms` on BOTH instances, `access upstream_status 503` matching, and ZERO error.log lines. 504s have `error.log upstream timed out (110)` + `access 504 rt 2.001s` + `app http_request 200 duration 2700ms` (app slow-success after proxy timeout). Proof: app explicitly names dependency + upstream answered (so not dial-refused).

### 10. Limits / next checks

Logs do NOT prove: root cause (deploy? crash? creds rotation? Redis overload? DB slow query? network partition?); config (NGINX `proxy_next_upstream`, timeouts, healthchecks); outside-window state; data loss/duplication on 504 (client saw fail, app logged 200 — was `/records GET` side-effect-free?); auth/client identity; resource metrics; whether 404s are probes or broken links; why only `/ready,/instance` retried.

Next in live env: `docker ps / compose ps, docker logs app-01 app-02 nginx --since`, `curl -i :8080/health /ready /instance` repeatedly, `nginx -T` (upstreams, `proxy_next_upstream`, `proxy_connect/read_timeout ~2s?`), `pg_isready + psql auth test, redis-cli ping/info/slowlog`, `ss/netstat`, `dmesg/journalctl`, metrics (CPU/mem/fd, pg `pg_stat_activity`, redis latency), distributed trace by `X-Request-ID`, chaos re-test (stop one backend, rotate creds) with `validate.py/failure_test.py`.

## Conclusions and limits

Three distinct failure modes, not one: (a) `.12` unreachable 11:05–11:09 (40x 502, 19x healed by retry), (b) Redis timeouts 11:12–11:15 + Postgres auth 11:20–11:21 (47x 503, ~2s), (c) `/records` slowness 11:25–11:26 (8x 504 at 2s proxy timeout vs 2.7s app). Overall 13.19% 5xx on 720 distinct requests; median 54ms hides p95 2001ms. Parse exclusions: 2 truncated lines + 7 identical-duplicate lines removed; 47 app event-pairs kept as one request each. Limits: synthetic lab data, no infra metrics/config — conclusions are log-evidenced correlation, not proven root cause.
