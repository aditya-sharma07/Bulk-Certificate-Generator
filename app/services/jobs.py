from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.database import Database
from app.schemas import CertificateDetails, JobCreate, RecipientInput
from app.services.certificates import generate_certificate


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class AppContext:
    database: Database
    storage_dir: Path
    max_recipients_per_job: int


def create_job(context: AppContext, request: JobCreate) -> str:
    job_id = uuid4().hex
    now = utc_now()

    with context.database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO jobs (
                id, title, course, issuer, issue_date, status, total_count, created_at
            ) VALUES (?, ?, ?, ?, ?, 'queued', ?, ?)
            """,
            (
                job_id,
                request.certificate.title,
                request.certificate.course,
                request.certificate.issuer,
                request.certificate.issue_date.isoformat(),
                len(request.recipients),
                now,
            ),
        )
        connection.executemany(
            """
            INSERT INTO recipients (
                id, job_id, ordinal, name, email, status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'queued', ?)
            """,
            [
                (uuid4().hex, job_id, index, recipient.name, recipient.email, now)
                for index, recipient in enumerate(request.recipients)
            ],
        )
    return job_id


def _record_recipient_success(
    connection: sqlite3.Connection, recipient_id: str, file_name: str
) -> None:
    connection.execute(
        """
        UPDATE recipients
        SET status = 'succeeded', file_name = ?, error = NULL, completed_at = ?
        WHERE id = ?
        """,
        (file_name, utc_now(), recipient_id),
    )


def _record_recipient_failure(
    connection: sqlite3.Connection, recipient_id: str, error: str
) -> None:
    connection.execute(
        """
        UPDATE recipients
        SET status = 'failed', error = ?, completed_at = ?
        WHERE id = ?
        """,
        (error[:1000], utc_now(), recipient_id),
    )


def process_job(context: AppContext, job_id: str) -> None:
    """Generate every queued recipient independently and finalize aggregate state."""

    job = context.database.fetch_one("SELECT * FROM jobs WHERE id = ?", (job_id,))
    if job is None:
        return

    with context.database.transaction() as connection:
        connection.execute(
            "UPDATE jobs SET status = 'processing', started_at = ? WHERE id = ?",
            (utc_now(), job_id),
        )

    certificate = CertificateDetails(
        title=job["title"],
        course=job["course"],
        issuer=job["issuer"],
        issue_date=job["issue_date"],
    )
    recipients = context.database.fetch_all(
        "SELECT * FROM recipients WHERE job_id = ? ORDER BY ordinal", (job_id,)
    )
    job_directory = context.storage_dir / job_id

    for row in recipients:
        recipient_id = row["id"]
        file_name = f"{row['ordinal'] + 1:04d}-{recipient_id}.pdf"
        output_path = job_directory / file_name

        with context.database.transaction() as connection:
            connection.execute(
                "UPDATE recipients SET status = 'processing' WHERE id = ?",
                (recipient_id,),
            )

        try:
            generate_certificate(
                output_path=output_path,
                certificate=certificate,
                recipient=RecipientInput(name=row["name"], email=row["email"]),
                certificate_id=recipient_id,
            )
        except Exception as exc:
            with context.database.transaction() as connection:
                _record_recipient_failure(
                    connection,
                    recipient_id,
                    f"{type(exc).__name__}: {exc}",
                )
        else:
            with context.database.transaction() as connection:
                _record_recipient_success(connection, recipient_id, file_name)

    counts = context.database.fetch_one(
        """
        SELECT
            SUM(CASE WHEN status = 'succeeded' THEN 1 ELSE 0 END) succeeded,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) failed
        FROM recipients WHERE job_id = ?
        """,
        (job_id,),
    )
    succeeded = int(counts["succeeded"] or 0)
    failed = int(counts["failed"] or 0)
    if succeeded and failed:
        final_status = "completed_with_errors"
    elif failed:
        final_status = "failed"
    else:
        final_status = "completed"

    with context.database.transaction() as connection:
        connection.execute(
            """
            UPDATE jobs
            SET status = ?, succeeded_count = ?, failed_count = ?, completed_at = ?
            WHERE id = ?
            """,
            (final_status, succeeded, failed, utc_now(), job_id),
        )

