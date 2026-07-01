"""
app/sync_jobs.py
Generic background-job runner for long-running operations that would
otherwise blow Render's worker timeout (Shopify sync, orders sync, etc.).

Pattern:
  job = start_background_job(kind='products_apply', work_fn=do_apply, user_id=...)
  return jsonify({'job_id': job.id}), 202

The work_fn signature is:
  def work_fn(job: SyncJob) -> dict
where the returned dict is stored as job.result on success.
Exceptions are caught and stored in job.error.

The work_fn can update job.progress and call db.session.commit() to surface
intermediate state to the polling frontend.
"""

import threading
from datetime import datetime, timedelta
from typing import Callable

from flask import current_app

from app import db
from app.models import SyncJob
from app.utils.logger import log_event

import os
import requests as _requests  # alias so we don't conflict if there's another import


def _has_active_job(kind: str) -> SyncJob | None:
    """
    Returns an existing pending/running job for this kind, if any. Used to
    prevent two simultaneous syncs of the same thing stepping on each other.
    """
    return (SyncJob.query
            .filter(SyncJob.kind == kind,
                    SyncJob.status.in_(['pending', 'running']))
            .order_by(SyncJob.id.desc())
            .first())


def get_latest_job(kind_prefix: str) -> SyncJob | None:
    """
    Find the most recent job whose kind starts with `kind_prefix`.
    e.g. kind_prefix='products' matches both 'products_check' and 'products_apply'.
    Used by the status endpoint to surface "the latest products-related thing".
    """
    return (SyncJob.query
            .filter(SyncJob.kind.like(f"{kind_prefix}%"))
            .order_by(SyncJob.id.desc())
            .first())


def start_background_job(kind: str,
                         work_fn: Callable[[SyncJob], dict],
                         user_id: int | None = None) -> tuple[SyncJob, bool]:
    """
    Create a SyncJob row and kick off work_fn in a background thread.
    
    Returns: (job, started)
      job:     the SyncJob row (either the newly-created one, OR the existing
               in-progress one if a conflict was detected)
      started: True if we started a fresh job; False if there was already
               one running for this kind
    """
    existing = _has_active_job(kind)
    if existing is not None:
        return existing, False

    job = SyncJob(
        kind=kind,
        status='pending',
        created_by=user_id,
        started_at=datetime.utcnow(),
    )
    db.session.add(job)
    db.session.commit()

    # Capture the app object — the thread won't have Flask's request context
    # by default, so we use app.app_context() inside the worker.
    app = current_app._get_current_object()
    job_id = job.id

    def _runner():
        with app.app_context():
            # Re-fetch the job inside the app context so it's bound to this
            # session, not the request session.
            j = SyncJob.query.get(job_id)
            if j is None:
                return
            try:
                j.status = 'running'
                db.session.commit()

                result = work_fn(j)

                # work_fn may have called db.session.expunge_all() during its
                # chunked commits, detaching our `j` reference. Re-fetch by ID
                # so mutations land properly.
                j = SyncJob.query.get(job_id)
                if j is None:
                    return
                j.status = 'success'
                j.result = result
                j.finished_at = datetime.utcnow()
                db.session.commit()

                log_event("info", "sync_jobs.complete",
                          f"Background job #{j.id} ({j.kind}) succeeded",
                          payload={"job_id": j.id, "kind": j.kind,
                                   "elapsed_ms": j.to_dict()['elapsed_ms']})
            except Exception as e:
                db.session.rollback()
                # Re-fetch — the rollback wiped our reference
                j = SyncJob.query.get(job_id)
                if j is not None:
                    j.status = 'failed'
                    j.error = str(e)[:2000]
                    j.finished_at = datetime.utcnow()
                    db.session.commit()
                # Notify Discord using the captured plain values (kind, job_id)
                # — never reference the detached `job` ORM object here.
                _notify_discord_failure(kind, job_id, str(e))
                log_event("error", "sync_jobs.failed",
                          f"Background job #{job_id} failed: {str(e)[:200]}",
                          payload={"job_id": job_id, "kind": kind,
                                   "error": str(e)[:500]})

    thread = threading.Thread(target=_runner, daemon=True, name=f"sync-{kind}-{job_id}")
    thread.start()

    return job, True

def _notify_discord_failure(kind: str, job_id: int, error: str):
    """Best-effort Discord ping when a sync job fails. Never raises."""
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        return  # not configured; silent no-op

    payload = {
        "username": "Sync Alerts",
        "embeds": [{
            "title": f"🔴 Sync Job Failed",
            "description": f"Backend sync job died after starting.",
            "color": 15158332,
            "fields": [
                {"name": "Kind",   "value": kind,           "inline": True},
                {"name": "Job ID", "value": str(job_id),    "inline": True},
                {"name": "Error",  "value": f"```{error[:400]}```", "inline": False},
            ],
            "footer": {"text": "social-ai-backend (Render)"},
        }]
    }

    try:
        _requests.post(webhook_url, json=payload, timeout=5)
    except Exception:
        pass  # alerts are best-effort; never let them break the failing flow

# How long a saved cursor stays valid. Older than this = discard, start fresh.
RESUME_WINDOW = timedelta(hours=24)


def get_resume_cursor(kind: str) -> str | None:
    """
    Decide whether to resume a previously-failed sync of this kind.
    
    Returns:
        A URL string to resume from, OR None to start fresh.
    
    Resume when ALL of these are true:
      - The most recent job of this kind failed
      - It saved a resume_cursor before dying
      - The failure was within the last 24 hours
    
    Otherwise return None (start fresh).
    """
    latest = (SyncJob.query
              .filter(SyncJob.kind == kind)
              .order_by(SyncJob.id.desc())
              .first())
    
    if latest is None:
        return None  # No prior job at all
    
    if latest.status != 'failed':
        return None  # Prior job succeeded (or is still running) — start fresh
    
    if not latest.resume_cursor:
        return None  # Failed but nothing saved — nothing to resume from
    
    # Check the failure was recent enough to trust the cursor
    finished = latest.finished_at or latest.started_at
    if finished is None:
        return None
    
    age = datetime.utcnow() - finished
    if age > RESUME_WINDOW:
        log_event("info", "sync_jobs.resume.stale",
                  f"Discarding stale cursor for {kind} (age: {age})")
        return None
    
    log_event("info", "sync_jobs.resume.will_resume",
              f"Resuming {kind} from saved cursor (age: {age})")
    return latest.resume_cursor


def notify_discord_warning(title: str, message: str, fields: list = None):
    """
    Send a yellow WARNING alert to Discord (not a red failure).
    Used for things like 'cursor expired, restarted from scratch' where
    the sync will still complete — we just want visibility.
    """
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        return
    
    payload = {
        "username": "Sync Alerts",
        "embeds": [{
            "title": f"🟡 {title}",
            "description": message,
            "color": 16763904,  # yellow
            "fields": fields or [],
        }]
    }
    
    try:
        _requests.post(webhook_url, json=payload, timeout=5)
    except Exception:
        pass

import re

def get_previous_progress_count(kind: str) -> int | None:
    """
    Extracts the last known 'processed count' from the previous failed job's
    progress text. Used to display 'Continued after ~N' in resumed syncs.
    
    Returns None if no previous progress can be found.
    """
    latest = (SyncJob.query
              .filter(SyncJob.kind == kind, SyncJob.status == 'failed')
              .order_by(SyncJob.id.desc())
              .first())
    if latest is None or not latest.progress:
        return None
    
    # Match patterns like "Processed 9,000 orders..." or "Processed 15,000 customers..."
    match = re.search(r'Processed\s+([\d,]+)', latest.progress)
    if not match:
        return None
    try:
        return int(match.group(1).replace(',', ''))
    except (ValueError, AttributeError):
        return None