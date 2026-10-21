"""Simulation worker. In AWS it is triggered by SQS; locally it runs in a thread."""
import json
import time

import engine
import store


def process(job_id):
    job = store.get_job(job_id)
    if not job:
        return
    store.update_job(job_id, status="RUNNING", started_at=store.now_ms())
    t0 = time.time()
    try:
        rec = store.get_twin(job["user_id"])
        if not rec:
            raise ValueError("Twin not found")
        result = engine.simulate(
            rec["twin"], years=int(job["years"]), num_paths=int(job["num_paths"]),
            scenario=job["scenario"],
        )
        result["compute_ms"] = round((time.time() - t0) * 1000)
        store.update_job(job_id, status="DONE", result=json.dumps(result), finished_at=store.now_ms())
    except Exception as exc:  # record the failure instead of retrying forever
        store.update_job(job_id, status="FAILED", error=str(exc)[:300], finished_at=store.now_ms())


def handler(event, context):
    """SQS event source mapping entry point (batch size 1)."""
    for record in event.get("Records", []):
        process(json.loads(record["body"])["job_id"])
    return {"processed": len(event.get("Records", []))}
