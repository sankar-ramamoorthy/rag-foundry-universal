import logging
from typing import List, Dict, Optional, Callable

from .types import RetrievedContext
from .agent_adapter import prepare_chunks_for_agent
from .summary_adapter import fetch_summaries
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class AgentPromptPipeline:
    """
    Feed retrieved chunks into an LLM agent prompt while enforcing:
      - Deterministic document + chunk ordering
      - Token budget limits
      - Optional scoring/filtering
      - Provenance tracing
    """

    def __init__(
        self,
        max_chunks_per_doc: int = 5,
        max_total_chunks: int = 50,
        max_tokens: Optional[int] = None,
        chunk_token_count: Optional[Callable] = None,
        filter_chunk: Optional[Callable] = None,
        debug: bool = False,
    ):
        self.max_chunks_per_doc = max_chunks_per_doc
        self.max_total_chunks = max_total_chunks
        self.max_tokens = max_tokens
        self.chunk_token_count = chunk_token_count
        self.filter_chunk = filter_chunk
        self.debug = debug

    def build_prompt_input(
        self,
        retrieved: RetrievedContext,
        document_order: Optional[List[str]] = None,
    ) -> List[Dict[str, object]]:
        """
        Convert RetrievedContext into agent-ready chunks and optionally enforce
        token budgets and filtering before sending to the LLM.
        """

        chunks = prepare_chunks_for_agent(
            retrieved,
            document_order=document_order,
            max_chunks_per_doc=self.max_chunks_per_doc,
            max_total_chunks=self.max_total_chunks,
            max_tokens=self.max_tokens,
            chunk_token_count=self.chunk_token_count,
            filter_chunk=self.filter_chunk,
            debug=self.debug,
        )

        if self.debug:
            logger.debug(f"Agent prompt input prepared with {len(chunks)} chunks")

        return chunks

    def build_prompt_text(
        self,
        retrieved: RetrievedContext,
        document_order: Optional[List[str]] = None,
        template: Optional[str] = None,
    ) -> str:
        """
        Flatten chunks into a single prompt string for the LLM,
        preserving provenance and deterministic order.
        Prepend document summaries (conceptual layer) before chunks (evidence layer).
        """

        # Step 0: Determine document order
        if document_order is None:
            document_order = sorted(retrieved.chunks_by_document.keys())

        # Step 1: Fetch summaries for these documents
        summaries = fetch_summaries(document_order)

        prompt_parts: List[str] = []

        # Step 2: Add summaries first (conceptual layer)
        for doc_id in document_order:
            summary = summaries.get(doc_id)
            if summary:
                prompt_parts.append(f"[SUMMARY:{doc_id}] {summary}")

        # Step 3: Add chunks next (evidence layer)
        chunks = self.build_prompt_input(retrieved, document_order=document_order)
        for c in chunks:
            if template is None:
                part = f"[{c['document_id']}/{c['chunk_id']}] {c['text']}"
            else:
                part = template.format(**c)
            prompt_parts.append(part)

        # Combine everything
        return "\n\n".join(prompt_parts)

