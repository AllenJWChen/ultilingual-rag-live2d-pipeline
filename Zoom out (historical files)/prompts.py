# ====== FILE: rag/generation/prompts.py ======
"""
四段式 LLM Prompt 集合（Question → Answer → Judge → Final）
用法：
    from rag.generation.prompts import (
        build_question_prompt, build_answer_prompt, build_judge_prompt, build_final_prompt
    )
"""
from textwrap import dedent
from typing import List, Dict

Citation = Dict[str, str]


def _fmt_evidence(snippets: List[Dict]) -> str:
    """將檢索到的片段格式化，包含 [source | page] 與文字節錄。
    期望 snippets 的每個元素包含 keys: text, source, page。
    """
    lines = []
    for i, s in enumerate(snippets, 1):
        head = f"[{i}] {s.get('source','unknown')} | page {s.get('page','?')}"
        body = s.get("text", "").strip()
        lines.append(f"{head}
{body}")
    return "

".join(lines)


# ---- (1) Question LLM：查詢規劃／正規化 ----

def build_question_prompt(question: str) -> str:
    return dedent(f"""
    [SYSTEM]
    You are a bilingual query planner. Normalize the question, extract keywords, and propose 3-6 high-recall search queries.
    Return STRICT JSON with keys:
      - normalized_zh: string (Traditional Chinese)
      - normalized_en: string (English)
      - keywords_zh: string[]
      - keywords_en: string[]
      - queries: string[]   # ranked, most important first

    [USER]
    Raw Question:
    {question}
    """)


# ---- (2) Answer LLM：依證據起草答案（允許標記缺證據） ----

def build_answer_prompt(question: str, evidence_snippets: List[Dict]) -> str:
    evidence = _fmt_evidence(evidence_snippets)
    return dedent(f"""
    [SYSTEM]
    You are a cautious domain assistant. Draft a concise, structured answer STRICTLY grounded in EVIDENCE.
    * If any claim is not supported, mark it as [UNSUPPORTED] and list what to retrieve next.
    * Return BILINGUAL output: Traditional Chinese first, then English.
    * Use citation placeholders like [CITATION 1], [CITATION 2] where a sentence relies on a snippet.

    [USER]
    QUESTION:
    {question}

    EVIDENCE (numbered snippets):
    {evidence}
    """)


# ---- (3) Judge LLM：事實驗證／補檢索建議 ----

def build_judge_prompt(draft: str, evidence_snippets: List[Dict]) -> str:
    evidence = _fmt_evidence(evidence_snippets)
    return dedent(f"""
    [SYSTEM]
    You are a meticulous fact verifier/editor.
    For EACH claim in DRAFT, check if it is supported by EVIDENCE.
    - For unsupported or contradicted claims: list them explicitly and propose re-retrieval keywords (zh/en) in a TODO list.
    - Produce a corrected OUTLINE that only keeps supported claims.
    - Finally give a one-word verdict: PASS or RETRIEVE.

    [USER]
    DRAFT:
    {draft}

    EVIDENCE:
    {evidence}

    Return JSON with keys: outline, issues, todo_keywords, verdict.
    """)


# ---- (4) Final LLM：雙語最終稿 + 逐句引文 ----

def build_final_prompt(question: str, outline: str, evidence_snippets: List[Dict]) -> str:
    evidence = _fmt_evidence(evidence_snippets)
    return dedent(f"""
    [SYSTEM]
    You produce the FINAL bilingual answer. Rules:
    - Only keep claims supported by EVIDENCE. Do not hallucinate.
    - Merge citations inline as [檔名 | page N] after each relevant sentence; multiple allowed.
    - Chinese section first, English section second.
    - If evidence is insufficient, state limits explicitly.

    [USER]
    QUESTION: {question}
    CORRECTED OUTLINE:
    {outline}

    EVIDENCE (for citation rendering):
    {evidence}
    """)


