"""Gmail ingest pipeline: schema, ground-truth labels, incremental historyId sync."""

from email_classifier.ingest.db import Database
from email_classifier.ingest.ground_truth import label_for_message, is_replied_in_thread
from email_classifier.ingest.runner import run_ingest

__all__ = ["Database", "label_for_message", "is_replied_in_thread", "run_ingest"]
