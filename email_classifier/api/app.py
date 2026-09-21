"""FastAPI app: POST /classify returns the ClassificationResult contract."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from email_classifier.config import load_config
from email_classifier.models.result import ClassificationResult
from email_classifier.pipeline import classify_message

app = FastAPI(title="email-classifier", version="0.1.0")


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
