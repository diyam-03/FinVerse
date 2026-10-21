"""Storage layer: DynamoDB when TWINS_TABLE / RESULTS_TABLE are set (AWS),
otherwise an in-memory dict (local development)."""
import json
import os
import time
from decimal import Decimal

TWINS_TABLE = os.environ.get("TWINS_TABLE")
RESULTS_TABLE = os.environ.get("RESULTS_TABLE")
USE_AWS = bool(TWINS_TABLE and RESULTS_TABLE)

_mem_twins = {}
_mem_jobs = {}

_ddb = None


def _tables():
    global _ddb
    if _ddb is None:
        import boto3
        _ddb = boto3.resource("dynamodb")
    return _ddb.Table(TWINS_TABLE), _ddb.Table(RESULTS_TABLE)


def now_ms():
    return int(time.time() * 1000)


def _plain(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    return v


def _job_out(item, with_result=True):
    job = {k: _plain(v) for k, v in item.items() if k != "result"}
    if with_result and item.get("result"):
        job["result"] = json.loads(item["result"])
    return job


# ----------------------------------------------------------------- twins
def put_twin(user_id, twin, dna):
    item = {"user_id": user_id, "data": json.dumps(twin), "dna": json.dumps(dna), "updated_at": now_ms()}
    if USE_AWS:
        _tables()[0].put_item(Item=item)
    else:
        _mem_twins[user_id] = item


def get_twin(user_id):
    if USE_AWS:
        item = _tables()[0].get_item(Key={"user_id": user_id}).get("Item")
    else:
        item = _mem_twins.get(user_id)
    if not item:
        return None
    return {"twin": json.loads(item["data"]), "dna": json.loads(item["dna"]), "updated_at": _plain(item["updated_at"])}


# ------------------------------------------------------------------ jobs
def create_job(job):
    job = dict(job, created_at=now_ms())
    if USE_AWS:
        _tables()[1].put_item(Item=job)
    else:
        _mem_jobs[job["job_id"]] = job
    return job


def update_job(job_id, **fields):
    if USE_AWS:
        names = {f"#{k}": k for k in fields}
        values = {f":{k}": v for k, v in fields.items()}
        expr = "SET " + ", ".join(f"#{k} = :{k}" for k in fields)
        _tables()[1].update_item(
            Key={"job_id": job_id}, UpdateExpression=expr,
            ExpressionAttributeNames=names, ExpressionAttributeValues=values,
        )
    else:
        _mem_jobs[job_id].update(fields)


def get_job(job_id):
    if USE_AWS:
        item = _tables()[1].get_item(Key={"job_id": job_id}).get("Item")
    else:
        item = _mem_jobs.get(job_id)
    return _job_out(item) if item else None


def list_jobs(user_id, limit=10):
    if USE_AWS:
        from boto3.dynamodb.conditions import Key
        resp = _tables()[1].query(
            IndexName="user-index", KeyConditionExpression=Key("user_id").eq(user_id),
            ScanIndexForward=False, Limit=limit,
        )
        items = resp.get("Items", [])
    else:
        items = sorted((j for j in _mem_jobs.values() if j["user_id"] == user_id),
                       key=lambda j: j["created_at"], reverse=True)[:limit]
    out = []
    for it in items:
        job = _job_out(it, with_result=False)
        if it.get("result"):
            r = json.loads(it["result"])
            job["summary"] = {"median_case": r["median_case"], "goal_probability": r["goal_probability"]}
        out.append(job)
    return out
