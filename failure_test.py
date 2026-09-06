#!/usr/bin/env python3
"""Stop one backend, measure traffic/errors, restore it and prove recovery."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8080").rstrip("/")
VICTIM = os.environ.get("FAILURE_VICTIM", "app-02")
TIMEOUT = int(os.environ.get("FAILURE_TIMEOUT", "5"))
WAIT_SECS = int(os.environ.get("FAILURE_WAIT", "90"))
BASELINE_N = int(os.environ.get("FAILURE_BASELINE_N", "10"))
DURING_N = int(os.environ.get("FAILURE_DURING_N", "30"))
AFTER_N = int(os.environ.get("FAILURE_AFTER_N", "20"))
MIN_SUCCESS_RATE = float(os.environ.get("FAILURE_MIN_RATE", "0.95"))

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS" if ok else "FAIL") + " " + name + (" - " + detail if detail else ""), flush=True)


def get_instance():
    try:
        with urllib.request.urlopen(BASE + "/instance", timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode() or "{}")
            return resp.status, body.get("instance_id")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return None, None


def burst(n):
    ok = err = 0
    seen = set()
    for _ in range(n):
        status, inst = get_instance()
        if status == 200 and inst:
            ok += 1
            seen.add(inst)
        else:
            err += 1
    return ok, err, seen


def docker(*args):
    out = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=60)
    if out.returncode:
        raise RuntimeError((out.stderr or out.stdout).strip() or "docker failed")
    return out.stdout.strip()


def wait_for_instances(required, secs):
    deadline = time.time() + secs
    seen = set()
    while time.time() < deadline:
        _, inst = get_instance()
        if inst:
            seen.add(inst)
        if required <= seen:
            return True, seen
        time.sleep(2)
    return False, seen


def main():
    if VICTIM not in ("app-01", "app-02"):
        print("FAIL bad-victim - FAILURE_VICTIM must be app-01 or app-02", flush=True)
        return 2
    survivor = "app-01" if VICTIM == "app-02" else "app-02"

    ok, seen = wait_for_instances({"app-01", "app-02"}, WAIT_SECS)
    check("preflight-both-up", ok, f"instances={sorted(seen)}")
    if not ok:
        return 1

    ok, err, seen = burst(BASELINE_N)
    check("baseline", err == 0 and seen == {"app-01", "app-02"},
          f"sent={BASELINE_N} ok={ok} errors={err} instances={sorted(seen)}")

    try:
        docker("stop", VICTIM)
        time.sleep(3)
        ok, err, seen = burst(DURING_N)
        rate = ok / DURING_N if DURING_N else 0
        during = (rate >= MIN_SUCCESS_RATE and survivor in seen and VICTIM not in seen,
                  f"sent={DURING_N} ok={ok} errors={err} rate={rate:.2f} instances={sorted(seen)}")
    finally:
        try:
            docker("start", VICTIM)
            restored = (True, f"{VICTIM} restarted")
        except Exception as exc:
            restored = (False, f"docker start {VICTIM} failed: {exc}")
    check("availability-during-failure", *during)
    check("restore", *restored)
    if not restored[0]:
        return 1

    ok, seen = wait_for_instances({VICTIM}, WAIT_SECS)
    check("victim-healthy", ok, f"{VICTIM} serving again, instances={sorted(seen)}")
    if not ok:
        return 1

    ok, err, seen = burst(AFTER_N)
    check("recovery", err == 0 and VICTIM in seen,
          f"sent={AFTER_N} ok={ok} errors={err} instances={sorted(seen)}")

    failed = results.count(False)
    print(f"{len(results)-failed}/{len(results)} checks passed", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
