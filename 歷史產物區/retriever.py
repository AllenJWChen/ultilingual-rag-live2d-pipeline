import os, json
import numpy as np
from typing import List, Dict
from .embeddings import encode

class FaissRetriever:
    def __init__(self, index_dir: str):
        import faiss
        self.index_dir = index_dir
        with open(os.path.join(index_dir, "metadata.json"), "r", encoding="utf-8") as f:
            self.meta = json.load(f)
        self.faiss = faiss.read_index(os.path.join(index_dir, "faiss.index"))

    def search(self, query: str, k: int = 8) -> List[Dict]:
        vec = encode([query]).astype("float32")
        D, I = self.faiss.search(vec, k)
        out = []
        for rank, (idx, score) in enumerate(zip(I[0], D[0]), start=1):
            item = self.meta["chunks"][int(idx)].copy()
            item["rank"] = rank
            item["score"] = float(score)
            out.append(item)
        return out
