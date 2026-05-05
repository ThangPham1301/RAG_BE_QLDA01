"""Embedding service using sentence-transformers."""
from __future__ import annotations

from typing import List

from sentence_transformers import SentenceTransformer
import numpy as np
import torch


class EmbeddingService:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', device: str | None = None, batch_size: int = 32):
        self.model_name = model_name
        # prefer explicit device arg, fallback to cuda if available
        if device:
            self.device = device
        else:
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.batch_size = batch_size
        # initialize model on the selected device
        self.model = SentenceTransformer(model_name, device=self.device)

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts. Batches to avoid OOM on GPU.

        Returns list of float lists.
        """
        if not texts:
            return []
        all_embs = []
        # sentence-transformers will run on device set at init
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            embs = self.model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
            np_embs = np.asarray(embs)
            for emb in np_embs:
                all_embs.append(emb.tolist())
        return all_embs


__all__ = ['EmbeddingService']
