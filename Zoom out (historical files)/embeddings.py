import os
from typing import List
from sentence_transformers import SentenceTransformer

_model = None

def get_embedder(model_name: str = None):
    global _model
    name = model_name or os.environ.get("EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    if _model is None or getattr(_model, '_name', '') != name:
        _model = SentenceTransformer(name)
        _model._name = name
    return _model

def encode(texts: List[str]):
    model = get_embedder()
    return model.encode(texts, normalize_embeddings=True)
