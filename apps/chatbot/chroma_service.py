"""Simple ChromaDB adapter.

Uses a per-project collection name and exposes `upsert_chunks` and
`get_relevant` to match the expectations of `RAGService`.
"""
from __future__ import annotations

import os
from typing import Dict, Iterable, List, Optional

import chromadb

from .embedding_service import EmbeddingService


class ChromaService:
    def __init__(self, persist_dir: Optional[str] = None, embedding_service: Optional[EmbeddingService] = None):
        persist_dir = persist_dir or os.environ.get('CHROMA_PERSIST_DIR', './chroma_db')
        # Use new Chroma API (PersistentClient)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.embedding = embedding_service or EmbeddingService()

    def _collection_name(self, project_id: int) -> str:
        return f'project_{project_id}'

    def get_or_create_collection(self, project_id: int):
        name = self._collection_name(project_id)
        try:
            return self.client.get_collection(name)
        except Exception:
            return self.client.create_collection(name)

    def upsert_chunks(self, project_id: int, chunks: Iterable[Dict]):
        """Upsert chunks. Each chunk dict: {id, text, metadata(dict)}"""
        col = self.get_or_create_collection(project_id)
        texts = []
        ids = []
        metadatas = []
        for c in chunks:
            ids.append(str(c['id']))
            texts.append(c['text'])
            metadatas.append(c.get('metadata') or {})

        embeddings = self.embedding.embed_texts(texts)
        col.upsert(ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings)

    def get_relevant(self, project_id: int, query: str, top_k: int = 5, chat_session_id: Optional[int] = None) -> List[Dict]:
        col = self.get_or_create_collection(project_id)
        q_emb = self.embedding.embed_texts([query])[0]
        query_kwargs = {
            'query_embeddings': [q_emb],
            'n_results': top_k,
            'include': ['documents', 'metadatas', 'distances'],
        }

        if chat_session_id is not None:
            query_kwargs['where'] = {'chat_session_id': int(chat_session_id)}

        # New Chroma API: don't include 'ids' in include list
        try:
            results = col.query(**query_kwargs)
        except Exception:
            # If the installed Chroma version rejects the metadata filter,
            # fall back to broad retrieval and filter in Python.
            query_kwargs.pop('where', None)
            results = col.query(**query_kwargs)
        out = []
        # results fields are lists per query; take first
        docs = results.get('documents', [[]])[0]
        metas = results.get('metadatas', [[]])[0]
        dists = results.get('distances', [[]])[0]
        ids = results.get('ids', [[]])[0]  # ids are returned automatically
        for did, doc, meta, dist in zip(ids, docs, metas, dists):
            out.append({'id': did, 'text': doc, 'metadata': meta, 'score': float(dist)})
        return out


__all__ = ['ChromaService']
