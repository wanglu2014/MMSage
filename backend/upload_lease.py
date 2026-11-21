"""Track the browser that owns a coordinate upload, independently of public job status."""

import hashlib
import secrets
import time

from filelock import FileLock

from runtime_state import job_dir, load_json, save_json


LEASE_SECONDS = 90


def _path(job_id):
    return job_dir(job_id) / "upload_lease.json"


def _digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_lease(job_id: str) -> str:
    token = secrets.token_urlsafe(32)
    save_json(_path(job_id), {
        "token_hash": _digest(token),
        "state": "active",
        "expires_at": time.time() + LEASE_SECONDS,
    })
    return token


def _state(lease):
    if lease["state"] == "active" and time.time() >= lease["expires_at"]:
        return "paused"
    return lease["state"]


def lease_state(job_id: str) -> str | None:
    path = _path(job_id)
    if not path.is_file():
        return None
    with FileLock(path.with_suffix(".lock")):
        return _state(load_json(path))


def update_lease(job_id: str, token: str, *, pause: bool = False) -> bool:
    path = _path(job_id)
    if not path.is_file():
        return False
    with FileLock(path.with_suffix(".lock")):
        lease = load_json(path)
        if not secrets.compare_digest(lease["token_hash"], _digest(token)):
            return False
        if _state(lease) == "active":
            if pause:
                lease["state"] = "paused"
            else:
                lease["expires_at"] = time.time() + LEASE_SECONDS
            save_json(path, lease)
        return True


def begin_archive(job_id: str) -> bool:
    """Serialize the last cancellation check with entry into shared catalog publication."""
    path = _path(job_id)
    with FileLock(path.with_suffix(".lock")):
        lease = load_json(path)
        if _state(lease) != "active":
            return False
        lease["state"] = "archiving"
        save_json(path, lease)
        return True
