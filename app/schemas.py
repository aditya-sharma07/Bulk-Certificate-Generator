from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class CertificateDetails(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=120)
    course: str = Field(min_length=1, max_length=160)
    issuer: str = Field(min_length=1, max_length=120)
    issue_date: date


class RecipientInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is not None and not EMAIL_PATTERN.fullmatch(value):
            raise ValueError("must be a valid email address")
        return value


class JobCreate(BaseModel):
    certificate: CertificateDetails
    recipients: list[RecipientInput] = Field(min_length=1)


JobStatus = Literal[
    "queued", "processing", "completed", "completed_with_errors", "failed"
]
RecipientStatus = Literal["queued", "processing", "succeeded", "failed"]


class JobCreated(BaseModel):
    id: str
    status: JobStatus
    total: int
    status_url: str


class Progress(BaseModel):
    total: int
    queued: int
    processing: int
    succeeded: int
    failed: int
    percent_complete: float


class RecipientResult(BaseModel):
    id: str
    name: str
    email: str | None
    status: RecipientStatus
    error: str | None
    download_url: str | None


class JobResult(BaseModel):
    id: str
    status: JobStatus
    certificate: CertificateDetails
    progress: Progress
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    download_all_url: str | None
    recipients: list[RecipientResult]

