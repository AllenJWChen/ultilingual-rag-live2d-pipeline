# —— 放在檔案頂部的 import 區 —— 
from .retriever import FaissRetriever  # 用你已經有的檢索器

# —— 這就是「包一層」：把物件方法變成 QuadLLMChain 期望的函式 —— 
def make_retrieve_fn(index_dir: str):
    """
    將 FaissRetriever.search 包裝成 QuadLLMChain 需要的 retrieve_fn 介面。
    使用：
        retrieve_fn = make_retrieve_fn("data/indices")
        evidence = retrieve_fn("矽光子的主要市場？", 8)
    """
    retriever = FaissRetriever(index_dir)

    def _retrieve_fn(query: str, k: int):
        # 直接呼叫你現有的 search
        return retriever.search(query, k)
    return _retrieve_fn





# ====== FILE: rag/generation/tri_chain.py ======
"""
四段式 RAG Orchestration（Question → Answer → Judge → Final）

使用方式（範例）：

    from rag.generation.tri_chain import QuadLLMChain
    from rag.generation.prompts import (
        build_question_prompt, build_answer_prompt, build_judge_prompt, build_final_prompt
    )
    from rag.generation.llm_router import get_llm  # 你現有的路由介面

    chain = QuadLLMChain(
        retrieve_fn=my_retrieve,               # callable(query, k) -> List[dict(text, source, page)]
        llm_question=get_llm("question"),     # 查詢規劃/正規化（溫度低）
        llm_answer=get_llm("answer"),         # 起草答案（溫度 0.5~0.7）
        llm_judge=get_llm("judge"),           # 事實驗證（溫度 0.1~0.2）
        llm_final=get_llm("final"),           # 雙語合併 + 引文（溫度 0.2~0.4）
        k=8,
        k_per_query=3,
    )
    result = chain.run("矽光子的主要市場？", lang="auto")
    print(result["final_text"])  # 雙語 + 引用

注意：
- 本模組只約定介面；不依賴特定檢索或 LLM SDK，便於你替換 FAISS/BM25 或雲端/本地模型。
- 檢索回傳的 snippets 需含 {text, source, page}。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
import json

from .prompts import (
    build_question_prompt,
    build_answer_prompt,
    build_judge_prompt,
    build_final_prompt,
)

RetrieveFn = Callable[[str, int], List[Dict]]
LLMFn = Callable[[str], str]


@dataclass
class QuadLLMChain:
    retrieve_fn: RetrieveFn
    llm_question: LLMFn
    llm_answer: LLMFn
    llm_judge: LLMFn
    llm_final: LLMFn
    k: int = 8               # 總證據目標數
    k_per_query: int = 3     # 每個查詢的檢索份數
    max_iters: int = 2       # Judge 建議後的補檢索輪數

    # ---- helpers ----
    def _retrieve(self, q: str, k: int) -> List[Dict]:
        return self.retrieve_fn(q, k)

    @staticmethod
    def _parse_json_loose(text: str) -> Dict:
        """盡量寬鬆地抓取 JSON（避免模型回傳多餘文字）。"""
        try:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except Exception:
            pass
        return {}

    @staticmethod
    def _dedup_merge(base: List[Dict], extra: List[Dict]) -> List[Dict]:
        seen = {(s.get('source'), s.get('page'), s.get('text')) for s in base}
        for s in extra:
            key = (s.get('source'), s.get('page'), s.get('text'))
            if key not in seen:
                base.append(s)
                seen.add(key)
        return base

    @staticmethod
    def _bilingual_order(src_lang: str, zh: str, en: str) -> str:
        if src_lang.lower().startswith("zh") or src_lang == "auto":
            return f"【中文】
{zh}

【English】
{en}"
        else:
            return f"【English】
{en}

【中文】
{zh}"

    # ---- main ----
    def run(self, question: str, lang: str = "auto") -> Dict[str, str]:
        # (1) Question LLM：生成查詢計畫
        q_prompt = build_question_prompt(question)
        q_raw = self.llm_question(q_prompt)
        q_parsed = self._parse_json_loose(q_raw)
        queries: List[str] = q_parsed.get("queries") or [question]

        # (2) 檢索：依 queries 聚合證據
        evidence: List[Dict] = []
        for q in queries:
            ev = self._retrieve(q, self.k_per_query)
            evidence = self._dedup_merge(evidence, ev)
            if len(evidence) >= self.k:
                evidence = evidence[: self.k]
                break

        # (3) Answer LLM：起草
        a_prompt = build_answer_prompt(question, evidence)
        draft = self.llm_answer(a_prompt)

        # (4) Judge LLM：驗證並建議補檢索
        outline = None
        verdict = "RETRIEVE"
        crit_raw = ""
        for _ in range(self.max_iters + 1):
            j_prompt = build_judge_prompt(draft, evidence)
            crit_raw = self.llm_judge(j_prompt)
            parsed = self._parse_json_loose(crit_raw)
            outline = parsed.get("outline") or outline or ""
            verdict = (parsed.get("verdict") or "RETRIEVE").upper()
            todo = parsed.get("todo_keywords") or []
            if verdict == "PASS" or not todo:
                break
            follow_q = f"{question} {' '.join(todo)}"
            more = self._retrieve(follow_q, max(2, self.k_per_query))
            evidence = self._dedup_merge(evidence, more)

        # (5) Final LLM：雙語 + 引文
        f_prompt = build_final_prompt(question, outline or "", evidence)
        final_text = self.llm_final(f_prompt)

        return {
            "question_plan": q_raw,
            "draft": draft,
            "judge": crit_raw,
            "final_text": final_text,
        }


if __name__ == "__main__":
    # 這段只是測試；正式環境你會在 API/CLI 內呼叫
    from rag.generation.llm_router import get_llm  # 你的路由器

    retrieve_fn = make_retrieve_fn("data/indices")

    chain = QuadLLMChain(
        retrieve_fn=retrieve_fn,
        llm_question=get_llm("question"),  # 低溫度，回 JSON（queries/keywords）
        llm_answer=get_llm("answer"),      # 起草回答
        llm_judge=get_llm("judge"),        # 驗證 + 建議補檢索
        llm_final=get_llm("final"),        # 雙語最終稿 + 引用
        k=8,            # 總證據數目上限
        k_per_query=3,  # 每個 query 抓幾段
        max_iters=2,    # 補檢索輪數
    )

    q = "矽光子的主要市場？"
    result = chain.run(q, lang="auto")
    print(result["final_text"])

