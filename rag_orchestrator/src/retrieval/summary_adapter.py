# rag_orchestrator/src/retrieval/summary_adapter.py

import logging
from typing import List, Dict, Optional
import requests

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Base URL for the ingestion service where summaries live
INGESTION_API_BASE_URL = "http://ingestion_service:8000"


def fetch_summaries(document_ids: List[str]) -> Dict[str, str]:
    """
    Given a list of document IDs, fetch their saved summaries from ingestion service.

    Returns:
        Dict[document_id, summary_text]
        If a document has no summary, it will be absent from the dict.
    """
    summaries: Dict[str, str] = {}

    for doc_id in document_ids:
        try:
            resp = requests.get(f"{INGESTION_API_BASE_URL}/v1/summary/{doc_id}", timeout=300)
            if resp.status_code == 200:
                data = resp.json()
                summary_text = data.get("summary")
                if summary_text:
                    summaries[doc_id] = summary_text
            else:
                logger.debug(f"No summary for doc_id={doc_id} (status={resp.status_code})")
        except Exception as exc:
            logger.warning(f"Error fetching summary for doc_id={doc_id}: {exc}")

    return summaries
