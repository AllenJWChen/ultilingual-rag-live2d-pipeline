# -*- coding: utf-8 -*-
from __future__ import annotations

from textwrap import dedent
from typing import List


def build_question_prompt(
    chunk_text: str,
    source: str,
    page: int,
    base_n: int = 5,
    per_kw_n: int = 2,
    langs: List[str] = None,
) -> str:
    """
    Build a Question LLM prompt:
    - Extract 3 keywords
    - Generate 11 questions: 5 base + 2 per keyword (3 keywords)
    - Output strict JSON matching the schema in the body
    """
    langs = langs or ["zh", "en"]
    langs_str = ", ".join(langs)

    # NOTE: use .format(...) instead of f-strings for Python 3.10 robustness,
    # and double braces {{ }} to render literal { } in the JSON schema.
    return dedent("""
    [SYSTEM]
    You are the Question LLM for dataset creation. For the given document chunk:
    1) Extract EXACTLY 3 domain-specific keywords (avoid overly generic words).
    2) Generate {base_n} base questions directly grounded in the chunk
       (cover definition/mechanism/data/trend/comparison).
    3) For EACH keyword, generate {per_kw_n} questions (total 3*{per_kw_n}).
    4) Limit languages to: {langs_str}. Each question should be 1-2 sentences,
       standalone, and avoid yes/no.

    Return STRICT JSON only, with this schema (no extra text):

    {{
      "keywords": ["K1", "K2", "K3"],
      "base_questions": [
        {{"text":"...", "lang":"zh|en", "difficulty":"easy|medium|hard", "topic":"..."}}
      ],
      "keyword_questions": [
        {{"keyword":"K1", "questions":[
          {{"text":"...", "lang":"zh|en", "difficulty":"...", "topic":"..."}},
          {{"text":"...", "lang":"...",   "difficulty":"...", "topic":"..."}}
        ]}},
        {{"keyword":"K2", "questions":[...]}}
      ]
    }}

    [CONTEXT]
    Source: {source} | page {page}
    Chunk:
    \"\"\"{chunk_text}\"\"\"

    [OUTPUT]
    Output JSON only.
    """.format(
        base_n=base_n,
        per_kw_n=per_kw_n,
        langs_str=langs_str,
        source=source,
        page=page,
        chunk_text=chunk_text,
    ))
