import logging
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Iterator

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, create_database
from app.models import GenerationJob, GenerationResult
from app.processing import process_generation_job
from app.schemas import (
    CreateGenerationJob,
    GenerationResultResponse,
    JobResponse,
    ResultsResponse,
)

logger = logging.getLogger(__name__)


def _job_response(job: GenerationJob) -> JobResponse:
    processed_count = job.success_count + job.failure_count
    progress_percent = round(processed_count * 100 / job.total_count, 2)
    return JobResponse(
        job_id=job.id,
        status=job.status,
        total_count=job.total_count,
        success_count=job.success_count,
        failure_count=job.failure_count,
        processed_count=processed_count,
        progress_percent=progress_percent,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _get_db(request: Request) -> Iterator[Session]:
    session: Session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def create_app(
    database_url: str | None = None,
    storage_dir: str | Path | None = None,
) -> FastAPI:
    resolved_database_url = database_url or os.getenv(
        "DATABASE_URL", "sqlite:///./certificates.db"
    )
    resolved_storage_dir = Path(
        storage_dir or os.getenv("CERTIFICATE_STORAGE_DIR", "./generated_certificates")
    ).resolve()
    engine, session_factory = create_database(resolved_database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        Base.metadata.create_all(bind=engine)
        yield
        engine.dispose()

    app = FastAPI(
        title="Bulk Certificate Generator",
        description="Create and track bulk certificate-generation jobs.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.session_factory = session_factory
    app.state.storage_dir = resolved_storage_dir

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/v1/jobs",
        response_model=JobResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["jobs"],
    )
    def create_generation_job(
        request_body: CreateGenerationJob,
        background_tasks: BackgroundTasks,
        request: Request,
        db: Session = Depends(_get_db),
    ) -> JobResponse:
        job_id = str(uuid.uuid4())
        job = GenerationJob(
            id=job_id,
            status="queued",
            certificate_info=request_body.certificate.model_dump(mode="json"),
            total_count=len(request_body.recipients),
            success_count=0,
            failure_count=0,
        )
        job.recipients = [
            GenerationResult(
                id=str(uuid.uuid4()),
                input_data=recipient,
                recipient_name=(
                    recipient.get("name") if isinstance(recipient.get("name"), str) else None
                ),
                recipient_email=(
                    recipient.get("email") if isinstance(recipient.get("email"), str) else None
                ),
                status="pending",
            )
            for recipient in request_body.recipients
        ]
        db.add(job)
        db.commit()
        db.refresh(job)
        background_tasks.add_task(
            process_generation_job,
            job_id,
            request.app.state.session_factory,
            request.app.state.storage_dir,
        )
        return _job_response(job)

    @app.get(
        "/api/v1/jobs/{job_id}",
        response_model=JobResponse,
        tags=["jobs"],
    )
    def get_generation_job(job_id: str, db: Session = Depends(_get_db)) -> JobResponse:
        job = db.get(GenerationJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Generation job not found")
        return _job_response(job)

    @app.get(
        "/api/v1/jobs/{job_id}/results",
        response_model=ResultsResponse,
        tags=["jobs"],
    )
    def get_generation_results(
        job_id: str, db: Session = Depends(_get_db)
    ) -> ResultsResponse:
        job = db.get(GenerationJob, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Generation job not found")
        recipients = db.scalars(
            select(GenerationResult)
            .where(GenerationResult.job_id == job_id)
            .order_by(GenerationResult.created_at, GenerationResult.id)
        ).all()
        return ResultsResponse(
            job_id=job.id,
            status=job.status,
            total_count=job.total_count,
            success_count=job.success_count,
            failure_count=job.failure_count,
            results=[
                GenerationResultResponse(
                    recipient_id=result.id,
                    name=result.recipient_name,
                    email=result.recipient_email,
                    status=result.status,
                    failure_reason=result.failure_reason,
                    certificate_url=(
                        f"/api/v1/jobs/{job.id}/certificates/{result.id}"
                        if result.status == "succeeded"
                        else None
                    ),
                    created_at=result.created_at,
                    completed_at=result.completed_at,
                )
                for result in recipients
            ],
        )

    @app.get(
        "/api/v1/jobs/{job_id}/certificates/{recipient_id}",
        response_class=FileResponse,
        responses={404: {"description": "Job, recipient, or certificate not found"}},
        tags=["certificates"],
    )
    def download_certificate(
        job_id: str,
        recipient_id: str,
        request: Request,
        db: Session = Depends(_get_db),
    ) -> FileResponse:
        result = db.scalar(
            select(GenerationResult).where(
                GenerationResult.id == recipient_id,
                GenerationResult.job_id == job_id,
            )
        )
        if result is None:
            raise HTTPException(status_code=404, detail="Certificate not found")
        if result.status != "succeeded" or not result.file_path:
            raise HTTPException(
                status_code=404, detail="Certificate is not available for this recipient"
            )

        root_path = Path(request.app.state.storage_dir).resolve()
        file_path = Path(result.file_path).resolve()
        try:
            file_path.relative_to(root_path)
        except ValueError:
            logger.error("Stored certificate path for result %s is outside storage", result.id)
            raise HTTPException(status_code=404, detail="Certificate file not found") from None
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="Certificate file not found")
        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=f"certificate-{result.id}.pdf",
        )

    return app


app = create_app()
