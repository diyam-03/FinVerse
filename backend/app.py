"""FinVerse API. `route()` is framework-free so the same code serves
API Gateway (Lambda) and the local dev server."""
import base64
import json
import os
import re
import threading
import uuid

import engine
import store


def _enqueue(job_id):
    queue_url = os.environ.get("QUEUE_URL")
    if queue_url:
        import boto3
        boto3.client("sqs").send_message(QueueUrl=queue_url, MessageBody=json.dumps({"job_id": job_id}))
    else:  # local dev: no SQS, run the worker in a background thread
        import worker
        threading.Thread(target=worker.process, args=(job_id,), daemon=True).start()


def route(method, path, body):
    """Returns (status_code, payload_dict)."""
    try:
        if method == "GET" and path == "/health":
            return 200, {"status": "ok", "storage": "dynamodb" if store.USE_AWS else "memory"}

        if method == "POST" and path == "/twin":
            twin = engine.clean_twin(body)
            dna = engine.financial_dna(twin)
            store.put_twin(twin["user_id"], twin, dna)
            return 200, {"twin": twin, "dna": dna}

        m = re.fullmatch(r"/twin/([A-Za-z0-9_-]{1,40})", path)
        if method == "GET" and m:
            rec = store.get_twin(m.group(1))
            return (200, rec) if rec else (404, {"error": "Twin not found"})

        if method == "POST" and path == "/simulate":
            body = body if isinstance(body, dict) else {}
            uid = str(body.get("user_id", ""))
            scenario = body.get("scenario", "baseline")
            if scenario not in engine.SCENARIOS:
                return 400, {"error": "Unknown scenario"}
            years = int(body.get("years", 10))
            paths = int(body.get("num_paths", 1000))
            if not 1 <= years <= 40:
                return 400, {"error": "years must be 1-40"}
            if not 100 <= paths <= 5000:
                return 400, {"error": "num_paths must be 100-5000"}
            if not store.get_twin(uid):
                return 404, {"error": "Save your twin first"}
            job_id = uuid.uuid4().hex
            store.create_job({"job_id": job_id, "user_id": uid, "scenario": scenario,
                              "years": years, "num_paths": paths, "status": "QUEUED"})
            _enqueue(job_id)
            return 202, {"job_id": job_id, "status": "QUEUED"}

        m = re.fullmatch(r"/result/([a-f0-9]{32})", path)
        if method == "GET" and m:
            job = store.get_job(m.group(1))
            return (200, job) if job else (404, {"error": "Job not found"})

        m = re.fullmatch(r"/history/([A-Za-z0-9_-]{1,40})", path)
        if method == "GET" and m:
            return 200, {"jobs": store.list_jobs(m.group(1))}

        return 404, {"error": "Not found"}
    except (ValueError, TypeError) as exc:
        return 400, {"error": str(exc)}
    except Exception as exc:
        print("ERROR", repr(exc))
        return 500, {"error": "Internal error"}


def handler(event, context):
    """API Gateway HTTP API (payload v2) entry point."""
    http = event["requestContext"]["http"]
    raw = event.get("body")
    if raw and event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode()
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"statusCode": 400, "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Invalid JSON"})}
    status, payload = route(http["method"], event["rawPath"], body)
    return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": json.dumps(payload)}
