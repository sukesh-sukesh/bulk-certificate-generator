from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CertificateInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    certificate_title: str = Field(min_length=1, max_length=200)
    event_name: str = Field(min_length=1, max_length=200)
    issuer: str = Field(min_length=1, max_length=200)
    issue_date: date

    @field_validator("certificate_title", "event_name", "issuer")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class CreateGenerationJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    certificate: CertificateInfo
    recipients: list[dict[str, Any]] = Field(min_length=1)


class RecipientData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=254)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if len(value) > 254 or value.count("@") != 1:
            raise ValueError("must be a valid email address")
        local_part, domain = value.rsplit("@", 1)
        if not local_part or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("must be a valid email address")
        if any(character.isspace() for character in value):
            raise ValueError("must be a valid email address")
        return value


class JobResponse(BaseModel):
    job_id: str
    status: str
    total_count: int
    success_count: int
    failure_count: int
    processed_count: int
    progress_percent: float
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class GenerationResultResponse(BaseModel):
    recipient_id: str
    name: str | None
    email: str | None
    status: str
    failure_reason: str | None
    certificate_url: str | None
    created_at: datetime
    completed_at: datetime | None


class ResultsResponse(BaseModel):
    job_id: str
    status: str
    total_count: int
    success_count: int
    failure_count: int
    results: list[GenerationResultResponse]
