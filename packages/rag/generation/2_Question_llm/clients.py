# -*- coding: utf-8 -*-
from __future__ import annotations

# Minimal Question LLM client (no router)
# Modes:
#   - MOCK: returns a synthetic JSON (for pipeline testing)
#   - OPENAI_COMPAT: calls an OpenAI-compatible endpoint (OpenAI / Ollama / OpenWebUI)
#
# Env vars:
#   LLM_MODE=MOCK | OPENAI_COMPAT
#   OPENAI_BASE_URL=http://localhost:11434/v1
#   OPENAI_API_KEY=sk-xxx
#   MODEL_QUESTION=llama3.1:8b-instruct

import os
import json

try:
    import httpx  # only needed for OPENAI_COMPAT
except Exception:
    httpx = None  # type: ignore

MODE = os.getenv("LLM_MODE", "MOCK").upper()
BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "sk-mock")
MODEL_Q = os.getenv("MODEL_QUESTION", "llama3.1:8b-instruct")


def _mock_payload() -> str:
    """Return a JSON string that matches the dataset schema:
       - 3 keywords
       - 5 base questions
       - 2 questions per keyword (3 keywords)
    """
    data = {
        "keywords": ["keyword_one", "keyword_two", "keyword_three"],
        "base_questions": [
            {"text": "Summarize the main topic discussed in this chunk.", "lang": "en", "difficulty": "easy", "topic": "overview"},
            {"text": "Explain the key mechanism or principle mentioned here.", "lang": "en", "difficulty": "medium", "topic": "mechanism"},
            {"text": "What data points or metrics are emphasized in this passage?", "lang": "en", "difficulty": "medium", "topic": "data"},
            {"text": "Compare two alternatives referenced in the text in terms of cost and performance.", "lang": "en", "difficulty": "hard", "topic": "comparison"},
            {"text": "Describe the trend or outlook implied by this section.", "lang": "en", "difficulty": "medium", "topic": "trend"}
        ],
        "keyword_questions": [
            {
                "keyword": "keyword_one",
                "questions": [
                    {"text": "Define keyword_one in the context of this chunk.", "lang": "en", "difficulty": "easy", "topic": "definition"},
                    {"text": "How does keyword_one impact the topic discussed here?", "lang": "en", "difficulty": "medium", "topic": "impact"}
                ]
            },
            {
                "keyword": "keyword_two",
                "questions": [
                    {"text": "What role does keyword_two play according to the passage?", "lang": "en", "difficulty": "medium", "topic": "role"},
                    {"text": "Provide an example or scenario illustrating keyword_two from the chunk.", "lang": "en", "difficulty": "medium", "topic": "example"}
                ]
            },
            {
                "keyword": "keyword_three",
                "questions": [
                    {"text": "Why is keyword_three relevant to the subject discussed?", "lang": "en", "difficulty": "medium", "topic": "relevance"},
                    {"text": "What are the limitations or risks related to keyword_three mentioned here?", "lang": "en", "difficulty": "hard", "topic": "risk"}
                ]
            }
        ]
    }
    return json.dumps(data, ensure_ascii=True)


def ask_question_llm(prompt: str) -> str:
    """Return the raw model output as a string (expected to be JSON)."""
    if MODE == "MOCK":
        return _mock_payload()

    if httpx is None:
        raise RuntimeError("Please `pip install httpx` or set LLM_MODE=MOCK to test without HTTP calls.")

    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {"model": MODEL_Q, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    resp = httpx.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]
