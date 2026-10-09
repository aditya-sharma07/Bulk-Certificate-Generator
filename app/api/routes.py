from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path as PathParameter, Request
from fastapi.responses import FileResponse

from app.schemas import JobCreate, JobCreated, JobResult
from app.services.jobs import AppContext, create_job, process_job


router = APIRouter(prefix="/api/v1", tags=["certificate jobs"])


def _context(request: Request) -> AppContext:
    return request.app.state.context


def _job_or_404(context: AppContext, job_id: str):
    job = context.database.fetch_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/jobs", response_model=JobCreated, status_code=202)
def submit_job(
    payload: JobCreate, request: Request, background_tasks: BackgroundTasks
) -> JobCreated:
    context = _context(request)
    if len(payload.recipients) > context.max_recipients_per_job:
        raise HTTPException(
            status_code=422,
            detail=(
                "Too many recipients: the maximum per job is "
                f"{context.max_recipients_per_job}"
            ),
        )

    job_id = create_job(context, payload)
    background_tasks.add_task(process_job, context, job_id)
    return JobCreated(
        id=job_id,
        status="queued",
        total=len(payload.recipients),
        status_url=f"/api/v1/jobs/{job_id}",
    )


@router.get("/jobs/{job_id}", response_model=JobResult)
def get_job(
    request: Request,
    job_id: Annotated[str, PathParameter(min_length=32, max_length=32)],
) -> dict:
    context = _context(request)
    job = _job_or_404(context, job_id)
    recipients = context.database.fetch_all(
        "SELECT * FROM recipients WHERE job_id = ? ORDER BY ordinal", (job_id,)
    )

    status_counts = {"queued": 0, "processing": 0, "succeeded": 0, "failed": 0}
    recipient_results = []
    for recipient in recipients:
        status_counts[recipient["status"]] += 1
        download_url = None
        if recipient["status"] == "succeeded":
            download_url = (
                f"/api/v1/jobs/{job_id}/certificates/{recipient['id']}"
            )
        recipient_results.append(
            {
                "id": recipient["id"],
                "name": recipient["name"],
                "email": recipient["email"],
                "status": recipient["status"],
                "error": recipient["error"],
                "download_url": download_url,
            }
        )

    finished = status_counts["succeeded"] + status_counts["failed"]
    total = job["total_count"]
    return {
        "id": job["id"],
        "status": job["status"],
        "certificate": {
            "title": job["title"],
            "course": job["course"],
            "issuer": job["issuer"],
            "issue_date": job["issue_date"],
        },
        "progress": {
            "total": total,
            **status_counts,
            "percent_complete": round(finished * 100 / total, 2),
        },
        "created_at": job["created_at"],
        "started_at": job["started_at"],
        "completed_at": job["completed_at"],
        "download_all_url": (
            f"/api/v1/jobs/{job_id}/certificates"
            if status_counts["succeeded"]
            else None
        ),
        "recipients": recipient_results,
    }


@router.get("/jobs/{job_id}/certificates/{recipient_id}")
def download_certificate(
    request: Request,
    job_id: Annotated[str, PathParameter(min_length=32, max_length=32)],
    recipient_id: Annotated[str, PathParameter(min_length=32, max_length=32)],
) -> FileResponse:
    context = _context(request)
    _job_or_404(context, job_id)
    recipient = context.database.fetch_one(
        "SELECT * FROM recipients WHERE id = ? AND job_id = ?",
        (recipient_id, job_id),
    )
    if recipient is None:
        raise HTTPException(status_code=404, detail="Recipient not found in this job")
    if recipient["status"] != "succeeded" or not recipient["file_name"]:
        raise HTTPException(status_code=409, detail="Certificate is not available")

    path = context.storage_dir / job_id / recipient["file_name"]
    if not path.is_file():
        raise HTTPException(status_code=410, detail="Certificate file is missing")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"certificate-{recipient_id}.pdf",
    )


@router.get("/jobs/{job_id}/certificates")
def download_all_certificates(
    request: Request,
    job_id: Annotated[str, PathParameter(min_length=32, max_length=32)],
) -> FileResponse:
    context = _context(request)
    _job_or_404(context, job_id)
    recipients = context.database.fetch_all(
        """
        SELECT id, file_name FROM recipients
        WHERE job_id = ? AND status = 'succeeded'
        ORDER BY ordinal
        """,
        (job_id,),
    )
    if not recipients:
        raise HTTPException(status_code=409, detail="No certificates are available")

    job_directory = context.storage_dir / job_id
    archive_path = job_directory / "certificates.zip"
    temporary_path = job_directory / f".{uuid4().hex}.zip"
    try:
        with ZipFile(temporary_path, "w", compression=ZIP_DEFLATED) as archive:
            for index, recipient in enumerate(recipients, start=1):
                certificate_path = job_directory / recipient["file_name"]
                if certificate_path.is_file():
                    archive.write(
                        certificate_path,
                        arcname=f"certificate-{index:04d}-{recipient['id']}.pdf",
                    )
        os.replace(temporary_path, archive_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"certificates-{job_id}.zip",
    )

