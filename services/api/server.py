import os
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from packages.rag_core.retriever import FaissRetriever
from packages.rag_core.rag_chain import build_prompt, mock_llm_generate

load_dotenv()
INDEX_DIR = os.environ.get("INDEX_DIR", "indices")
retriever = FaissRetriever(INDEX_DIR)

app = FastAPI(title="Multilingual RAG + Live2D API")

class AskBody(BaseModel):
    q: str
    k: int | None = 8

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/ask")
def ask(body: AskBody):
    hits = retriever.search(body.q, k=body.k or 8)
    prompt = build_prompt(body.q, hits)
    answer = mock_llm_generate(prompt)
    return {"answer": answer, "citations": [{"rank":h["rank"], "page":h.get("page"), "src":h.get("source")} for h in hits]}
