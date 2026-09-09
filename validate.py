#!/usr/bin/env python3
"""Validate public access, endpoints, backends, dependencies, isolation and ports."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
TIMEOUT = int(os.environ.get("VALIDATE_TIMEOUT", "5"))
WAIT_SECS = int(os.environ.get("VALIDATE_WAIT", "90"))
REQUIRED_INSTANCES = set(os.environ.get("VALIDATE_INSTANCES", "app-01,app-02").split(","))
EXPECTED_NETWORKS = {
    "app-01": {"frontend", "backend"},
    "app-02": {"frontend", "backend"},
    "nginx": {"frontend"},
    "postgres": {"backend"},
    "redis": {"backend"},
}

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS" if ok else "FAIL") + " " + name + (" - " + detail if detail else ""), flush=True)


def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode() or "{}")
        except Exception:
            return exc.code, {}
    except Exception as exc:
        return None, {"error": repr(exc)}


def wait_ready():
    deadline = time.time() + WAIT_SECS
    last = None
    while time.time() < deadline:
        status, body = http("GET", "/ready")
        if status == 200 and body.get("status") == "ready":
            return True, body
        last = (status, body)
        time.sleep(2)
    return False, last


def docker(*args):
    out = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=30)
    if out.returncode:
        raise RuntimeError((out.stderr or out.stdout).strip() or "docker failed")
    return out.stdout.strip()


def main():
    ok, body = wait_ready()
    check("readiness", ok, f"GET /ready -> {body}")
    if not ok:
        return 1

    status, body = http("GET", "/")
    check("public-access", status == 200 and "message" in body, f"GET / -> {status} {body}")

    status, body = http("GET", "/health")
    check("health", status == 200 and body.get("status") == "alive", f"GET /health -> {status} {body}")

    status, body = http("GET", "/ready")
    deps = body.get("dependencies", {}) if isinstance(body, dict) else {}
    check("postgres-ready", deps.get("postgres") == "ready", f"postgres={deps.get('postgres')}")
    check("redis-ready", deps.get("redis") == "ready", f"redis={deps.get('redis')}")

    seen = set()
    for _ in range(20):
        status, body = http("GET", "/instance")
        if status == 200 and body.get("instance_id"):
            seen.add(body["instance_id"])
        if seen == REQUIRED_INSTANCES:
            break
    check("both-backends", seen == REQUIRED_INSTANCES, f"instances={sorted(seen)}")

    status, body = http("GET", "/records")
    check("records-list", status == 200 and isinstance(body.get("records"), list),
          f"GET /records -> {status} count={len(body.get('records', [])) if isinstance(body.get('records'), list) else '?'}")

    title = f"validate-{int(time.time())}"
    status, body = http("POST", "/records", {"title": title})
    created = body.get("record", {}) if isinstance(body, dict) else {}
    status2, body2 = http("GET", "/records")
    titles = [r.get("title") for r in body2.get("records", [])] if isinstance(body2.get("records"), list) else []
    check("records-create", status == 201 and created.get("title") == title and title in titles,
          f"POST /records -> {status} listed={title in titles}")

    status, body = http("GET", "/counter")
    first = body.get("counter") if isinstance(body, dict) else None
    status2, body2 = http("GET", "/counter")
    second = body2.get("counter") if isinstance(body2, dict) else None
    check("counter", isinstance(first, int) and isinstance(second, int) and second > first,
          f"counter {first} -> {second}")

    try:
        nets = {}
        for svc in ("app-01", "app-02", "nginx", "postgres", "redis"):
            info = json.loads(docker("inspect", svc))[0]
            names = info["NetworkSettings"]["Networks"].keys()
            front = [n for n in names if n.endswith("frontend")]
            back = [n for n in names if n.endswith("backend")]
            suffixes = set((["frontend"] if front else []) + (["backend"] if back else []))
            if len(front) > 1 or len(back) > 1:
                suffixes.add("ambiguous")
            nets[svc] = suffixes
        iso_ok = all(nets.get(s) == EXPECTED_NETWORKS[s] for s in EXPECTED_NETWORKS)
        check("network-isolation", iso_ok, f"{nets}")
    except Exception as exc:
        check("network-isolation", False, f"inspect failed: {exc}")

    try:
        bad = []
        for svc in ("app-01", "app-02", "postgres", "redis"):
            info = json.loads(docker("inspect", svc))[0]
            ports = info["NetworkSettings"].get("Ports") or {}
            if any(v for v in ports.values() if v):
                bad.append(svc)
        nginx_info = json.loads(docker("inspect", "nginx"))[0]
        np = nginx_info["NetworkSettings"].get("Ports") or {}
        nginx_ok = any(v for v in np.values() if v)
        ports_ok = not bad and nginx_ok
        check("host-ports", ports_ok, f"published_on={bad} nginx_published={nginx_ok}")
    except Exception as exc:
        check("host-ports", False, f"inspect failed: {exc}")

    failed = results.count(False)
    print(f"{len(results)-failed}/{len(results)} checks passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
