"""RAG orchestration service.

This module coordinates retrieval from ChromaDB, prompt building and LLM
generation to produce answers, summaries and citations. It keeps
high-level logic out of views and is easy to test and evolve.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Iterable, List, Optional

from .prompt_service import build_qa_prompt
from .llm_service import LLMService

logger = logging.getLogger(__name__)


class RAGService:
    """High-level Retrieval-Augmented-Generation service.

    This service depends on an external Chroma adapter to fetch relevant
    chunks. The Chroma adapter is intentionally dependency-injected via
    the `retriever` argument (duck-typed), so it can be mocked in tests.
    """

    def __init__(self, retriever, llm: Optional[LLMService] = None, default_top_k: int = 5):
        """Create a RAGService.

        retriever: object with method get_relevant(project_id, query, top_k) -> List[Dict]
                   each dict should contain at least 'text' and optional metadata like 'document_id' and 'score'.
        llm: LLMService instance (optional). If omitted, a default will be created.
        """
        self.retriever = retriever
        self.llm = llm or LLMService()
        self.default_top_k = default_top_k
        try:
            self.max_context_chars = int(os.environ.get('RAG_MAX_CONTEXT_CHARS', '2500'))
        except Exception:
            self.max_context_chars = 2500
        try:
            self.answer_max_tokens = int(os.environ.get('RAG_MAX_TOKENS', '256'))
        except Exception:
            self.answer_max_tokens = 256

    def answer_question(self, project_id: int, question: str, top_k: Optional[int] = None, instruction: Optional[str] = None, document_ids: Optional[List[int]] = None) -> Dict[str, object]:
        """Answer a question using retrieval + LLM.

        Returns a dict with keys:
        - 'answer': generated answer string
        - 'sources': list of metadata for retrieved chunks used for citation
        - 'raw_retrieval': raw items returned by retriever
        """
        top_k = top_k or self.default_top_k
        logger.debug('RAGService.answer_question project=%s top_k=%s', project_id, top_k)

        # 1) retrieve
        items = self.retriever.get_relevant(project_id=project_id, query=question, top_k=top_k, document_ids=document_ids)
        texts = [it.get('text', '') for it in items]

        # 2) build prompt
        prompt = build_qa_prompt(
            question=question,
            contexts=texts,
            instruction=instruction,
            max_context_chars=self.max_context_chars,
        )

        # 3) call LLM
        answer = self.llm.generate(prompt, max_tokens=self.answer_max_tokens)

        # 4) prepare sources for citation (document_id and chunk index if present)
        sources = []
        for it in items:
            metadata = it.get('metadata', {})
            meta = {
                'document_id': metadata.get('document_id'),
                'chunk_id': it.get('id'),
                'score': it.get('score'),
            }
            sources.append(meta)

        return {
            'answer': answer,
            'sources': sources,
            'raw_retrieval': items,
        }


__all__ = ['RAGService']
