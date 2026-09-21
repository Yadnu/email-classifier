"""FastAPI app: POST /classify and GET /metrics."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from email_classifier.config import load_config
from email_classifier.models.result import ClassificationResult
from email_classifier.observability import REGISTRY, setup_observability
from email_classifier.pipeline import classify_message


@asynccontextmanager
async def lifespan(_app: FastAPI):
    setup_observability()
    yield


app = FastAPI(title="email-classifier", version="0.1.0", lifespan=lifespan)


class ClassifyRequest(BaseModel):
    message_id: str


@app.post("/classify", response_model=ClassificationResult)
def classify(body: ClassifyRequest) -> ClassificationResult:
    cfg = load_config()
    try:
        return classify_message(body.message_id, cfg)
    except SystemExit as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="classification failed") from exc


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
