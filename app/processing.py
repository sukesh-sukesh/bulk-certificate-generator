import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.certificates import generate_certificate
from app.models import GenerationJob, GenerationResult
from app.schemas import CertificateInfo, RecipientData

logger = logging.getLogger(__name__)


def _refresh_counts(job: GenerationJob, recipients: list[GenerationResult]) -> None:
    job.success_count = sum(result.status == "succeeded" for result in recipients)
    job.failure_count = sum(result.status == "failed" for result in recipients)
    job.updated_at = datetime.now(timezone.utc)


def process_generation_job(
    job_id: str,
    session_factory: sessionmaker,
    storage_dir: Path,
) -> None:
    try:
        with session_factory() as session:
            job = session.get(GenerationJob, job_id)
            if job is None:
                logger.error("Generation job %s disappeared before processing", job_id)
                return
            job.status = "processing"
            session.commit()

            certificate = CertificateInfo.model_validate(job.certificate_info)
            recipients = list(
                session.scalars(
                    select(GenerationResult)
                    .where(GenerationResult.job_id == job_id)
                    .order_by(GenerationResult.created_at, GenerationResult.id)
                )
            )
            for result in recipients:
                output_path = storage_dir / job_id / f"{result.id}.pdf"
                try:
                    recipient = RecipientData.model_validate(result.input_data)
                    result.recipient_name = recipient.name
                    result.recipient_email = recipient.email
                    generate_certificate(output_path, recipient, certificate)
                    result.file_path = str(output_path.resolve())
                    result.failure_reason = None
                    result.status = "succeeded"
                except Exception as exc:
                    if output_path.exists():
                        output_path.unlink()
                    result.file_path = None
                    result.status = "failed"
                    result.failure_reason = str(exc)[:500] or type(exc).__name__
                    logger.exception(
                        "Certificate generation failed for recipient %s in job %s",
                        result.id,
                        job_id,
                    )
                result.completed_at = datetime.now(timezone.utc)
                _refresh_counts(job, recipients)
                session.commit()

            job.status = "completed"
            _refresh_counts(job, recipients)
            session.commit()
    except Exception as exc:
        logger.exception("Generation job %s failed unexpectedly", job_id)
        with session_factory() as session:
            job = session.get(GenerationJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = str(exc)[:500] or type(exc).__name__
                job.updated_at = datetime.now(timezone.utc)
                session.commit()
