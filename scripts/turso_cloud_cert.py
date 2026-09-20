#!/usr/bin/env python3
"""Real Turso cloud certification — never prints secrets.

Exit 0 only if critical cloud acceptance criteria pass.
Namespace: cloud_certification/
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _present(name: str) -> bool:
    return bool(os.environ.get(name, "").strip())


def main() -> int:
    results: list[tuple[str, str, str]] = []

    def ok(name: str, note: str = "") -> None:
        results.append((name, "PASS", note))
        print(f"[PASS] {name}" + (f" — {note}" if note else ""))

    def fail(name: str, note: str = "") -> None:
        results.append((name, "FAIL", note))
        print(f"[FAIL] {name}" + (f" — {note}" if note else ""))

    if not (_present("TURSO_DATABASE_URL") and _present("TURSO_AUTH_TOKEN")):
        print("CLOUD_CAN_RUN=false")
        print("CLOUD INTEGRATION = NOT EXECUTED")
        return 2

    print("CLOUD_CAN_RUN=true")
    print("Secret presence: TURSO_DATABASE_URL=yes TURSO_AUTH_TOKEN=yes (values not printed)")

    url = os.environ["TURSO_DATABASE_URL"].strip()
    token = os.environ["TURSO_AUTH_TOKEN"].strip()

    from src.python.memory.client import MemoryStatus, connect_turso
    from src.python.memory import queries as mq
    from src.python.memory.schema import SCHEMA_VERSION

    try:
        mem = connect_turso(url, token, prefer_http=True, timeout_sec=45.0)
    except Exception as e:
        fail("connection", type(e).__name__)
        return _summary(results)

    if mem.status != MemoryStatus.AVAILABLE or not mem.is_remote:
        fail("connection", f"status={mem.status} backend={mem._backend} err={mem.last_error}")
        return _summary(results)
    ok("connection", f"backend={mem._backend}")
    ok("authentication", "reachable")

    try:
        mem.migrate()
        mem.migrate()
        ok("schema_version_code", f"SCHEMA_VERSION={SCHEMA_VERSION}")
        ok("migration_idempotent", "migrate x2")
    except Exception as e:
        fail("migration", type(e).__name__)
        return _summary(results)

    ns = f"cloud_certification/{uuid.uuid4().hex[:12]}"
    ts = datetime.now(timezone.utc).isoformat()
    print(f"namespace={ns}")

    exp_id = f"{ns}/exp"
    fp = f"{ns}/fp/{uuid.uuid4().hex[:16]}"
    w = mq.write_experiment(
        mem,
        {
            "experiment_id": exp_id,
            "fingerprint": fp,
            "status": "CLOUD_CERT",
            "commit_sha": "cert",
            "dataset_hash": "cert",
            "result_hash": "cert",
            "evidence_hash": "cert",
            "artifact_reference": f"cloud_cert://{ns}",
            "dependency_snapshot": {"cert": True, "ts": ts},
        },
    )
    if not (w.get("persisted") and w.get("remote_persisted") and not w.get("local_persisted")):
        fail("write_experiment", str({k: w.get(k) for k in ("status", "persisted", "remote_persisted", "local_persisted", "backend")}))
    else:
        ok("write_experiment", f"backend={w.get('backend')}")

    hid = f"{ns}/hyp"
    wh = mq.write_hypothesis(mem, {"hypothesis_id": hid, "hypothesis": "cert", "status": "OPEN"})
    (ok if wh.get("remote_persisted") else fail)("write_hypothesis", str(wh.get("status")))

    fid = f"{ns}/fail"
    wf = mq.write_failure(mem, {"failure_id": fid, "failure_type": "CERT"})
    (ok if wf.get("remote_persisted") else fail)("write_failure", str(wf.get("status")))

    kid = f"{ns}/know"
    wk = mq.write_knowledge(mem, {"knowledge_id": kid, "source_type": "CERT", "content": "cert"})
    (ok if wk.get("remote_persisted") else fail)("write_knowledge", str(wk.get("status")))

    did = f"{ns}/drift"
    wd = mq.write_drift(mem, {"drift_id": did, "metric": "cert"})
    (ok if wd.get("remote_persisted") else fail)("write_drift", str(wd.get("status")))

    r = mq.query_experiment(mem, exp_id)
    (ok if r.get("status") == "MATCH_FOUND" else fail)("read_experiment", str(r.get("status")))

    rf = mq.query_by_fingerprint(mem, fp)
    (ok if rf.get("status") == "MATCH_FOUND" else fail)("read_fingerprint", str(rf.get("status")))

    rh = mq.query_hypotheses(mem, hid)
    (ok if rh.get("status") == "MATCH_FOUND" else fail)("read_hypothesis", str(rh.get("status")))

    rfail = mq.query_failures(mem, fid)
    (ok if rfail.get("status") == "MATCH_FOUND" else fail)("read_failure", str(rfail.get("status")))

    rk = mq.query_knowledge(mem, kid)
    (ok if rk.get("status") == "MATCH_FOUND" else fail)("read_knowledge", str(rk.get("status")))

    rd = mq.query_drift(mem, did)
    (ok if rd.get("status") == "MATCH_FOUND" else fail)("read_drift", str(rd.get("status")))

    re = mq.query_experiment_events(mem, exp_id)
    if re.get("status") in ("MATCH_FOUND", "NO_MATCH"):
        ok("read_experiment_events", str(re.get("status")))
    else:
        fail("read_experiment_events", str(re.get("status")))

    w2 = mq.write_experiment(mem, {"experiment_id": exp_id, "fingerprint": fp, "status": "CLOUD_CERT"})
    if w2.get("idempotent"):
        ok("idempotency", "second write idempotent")
    else:
        fail("idempotency", str(w2))

    missing_fp = f"{ns}/never/{uuid.uuid4().hex}"
    nm = mq.query_by_fingerprint(mem, missing_fp)
    if nm.get("status") == "NO_MATCH":
        ok("no_match", "NO_MATCH for unknown fingerprint")
    else:
        fail("no_match", str(nm.get("status")))

    try:
        bad = connect_turso(url, "invalid-token-cloud-cert-test", prefer_http=True, timeout_sec=20.0)
        if bad.status == MemoryStatus.UNAVAILABLE:
            ok("auth_negative", f"error={bad.last_error}")
        else:
            fail("auth_negative", f"status={bad.status} err={bad.last_error}")
    except Exception as e:
        ok("auth_negative", f"raised={type(e).__name__}")

    from src.python.memory.client import (
        memory_cannot_approve_evidence,
        memory_cannot_mutate_champion,
        memory_cannot_mutate_ledger,
    )
    if memory_cannot_mutate_ledger() and memory_cannot_mutate_champion() and memory_cannot_approve_evidence():
        ok("isolation_flags")
    else:
        fail("isolation_flags")

    mem.close()
    return _summary(results)


def _summary(results: list[tuple[str, str, str]]) -> int:
    fails = [r for r in results if r[1] == "FAIL"]
    passes = [r for r in results if r[1] == "PASS"]
    print("--- SUMMARY ---")
    print(f"PASS={len(passes)} FAIL={len(fails)}")
    critical = {
        "connection", "authentication", "migration_idempotent",
        "write_experiment", "read_experiment", "read_fingerprint",
        "idempotency", "no_match",
    }
    crit_fail = [r for r in fails if r[0] in critical]
    if crit_fail:
        print("CLOUD CERTIFICATION = FAIL")
        for n, s, note in crit_fail:
            print(f"  critical_fail: {n} {note}")
        return 1
    if fails:
        print("CLOUD CERTIFICATION = CONDITIONAL")
        for n, s, note in fails:
            print(f"  noncritical_fail: {n} {note}")
        return 1
    print("CLOUD CERTIFICATION = PASS")
    print("CLOUD INTEGRATION = PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
