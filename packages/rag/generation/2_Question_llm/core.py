# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import argparse
import time
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

# 若你有保留原專案的 llm 客戶端與 prompt 模組，照原樣引入
# build_question_prompt 未必需要；本檔直接自組 prompt
from .clients import ask_question_llm  # 必需：你專案裡呼叫 LLM 的函式
# from .prompts_dataset import build_question_prompt  # 可選


# -------------------- 小工具 --------------------

def _safe_json_extract(s: str) -> Dict:
    """盡力從 LLM 的原始輸出裡擷取最外層 JSON 物件。"""
    try:
        start = s.find("{")
        end = s.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(s[start:end])
    except Exception:
        pass
    return {}


def _normalize_questions(data: Dict, expect_base: int = 5, expect_kw: int = 2) -> Dict:
    """
    正規化 LLM 回傳，使其一定包含：
      - "keywords": 長度 3
      - "base_questions": 長度 expect_base
      - "keyword_questions": 3 個 keyword × 每個 expect_kw 題
    """
    out = {"keywords": [], "base_questions": [], "keyword_questions": []}

    # keywords 固定 3
    kws = [k for k in (data.get("keywords") or []) if isinstance(k, str) and k.strip()]
    kws = kws[:3]
    while len(kws) < 3:
        kws.append(f"KW_{len(kws)+1}")
    out["keywords"] = kws

    # base questions 固定 expect_base
    bq = [q for q in (data.get("base_questions") or []) if isinstance(q, dict) and q.get("text")]
    bq = bq[:expect_base]
    while len(bq) < expect_base:
        bq.append({
            "text": f"Summarize the next key point from the chunk ({len(bq)+1}).",
            "lang": "en",
            "difficulty": "easy",
            "topic": "overview",
        })
    out["base_questions"] = bq

    # keyword questions：每個 kw 固定 expect_kw 題
    kwq_list = []
    provided = data.get("keyword_questions") or []
    for kw in kws:
        # 嘗試從回傳裡找對應 keyword 的題目
        cand = None
        for item in provided:
            if isinstance(item, dict) and str(item.get("keyword", "")).strip().lower() == kw.lower():
                cand = item
                break
        qs = []
        if cand and isinstance(cand.get("questions"), list):
            qs = [q for q in cand["questions"] if isinstance(q, dict) and q.get("text")]
        qs = qs[:expect_kw]
        while len(qs) < expect_kw:
            qs.append({
                "text": f"Ask an explanatory question about keyword '{kw}' ({len(qs)+1}).",
                "lang": "en",
                "difficulty": "medium",
                "topic": "keyword",
            })
        kwq_list.append({"keyword": kw, "questions": qs})
    out["keyword_questions"] = kwq_list
    return out


def _build_prompt_with_keywords(chunk_text: str, source: str, page: int,
                                keywords: List[str], base_n: int, per_kw_n: int,
                                langs: List[str]) -> str:
    langs_s = ", ".join(langs) if langs else "en"
    kws_s = ", ".join([f"'{k}'" for k in keywords[:3]]) if keywords else ""
    return f"""
You are a question writer for a RAG system.

Given the following CHUNK (from source: {source}, page: {page}) and its top keywords [{kws_s}], produce a JSON object with this schema:

{{
  "keywords": ["k1","k2","k3"],
  "base_questions": [{{"text": "...", "lang": "en|zh", "difficulty": "easy|medium|hard", "topic": "overview"}}],  // exactly {base_n} items
  "keyword_questions": [
     {{"keyword": "k1", "questions": [{{"text":"..." , "lang":"en|zh", "difficulty":"...", "topic":"keyword"}}, ...]}},
     {{"keyword": "k2", "questions": [...] }},
     {{"keyword": "k3", "questions": [...] }}
  ]
}}

Rules:
- Generate exactly {base_n} base questions about the chunk content.
- For EACH keyword (3 total), generate exactly {per_kw_n} focused questions.
- Prefer languages from: {langs_s}.
- Keep questions precise, answerable from the chunk.
- Do NOT include explanations outside the JSON.

CHUNK:
\"\"\"{chunk_text}\"\"\"
""".strip()


def _iter_keyword_jsonl(path: str):
    """逐行讀 keyword JSONL；每列需至少包含 'text' 與 'keywords'（list[str]）。"""
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception:
                continue
            text = (obj.get("text") or "").strip()
            if not text:
                continue
            yield line_no, obj


# -------------------- 併發工作 --------------------

def _one_job(line_no: int,
             obj: Dict,
             base_n: int,
             per_kw_n: int,
             langs: List[str],
             retries: int = 2,
             backoff: float = 1.2) -> Tuple[int, Dict]:
    """
    單筆任務：針對一個 chunk + keywords 產生問題，回傳 (line_no, output_record)
    """
    text = (obj.get("text") or "").strip()
    source = obj.get("source", obj.get("file", "unknown"))
    try:
        page = int(obj.get("page", 0) or 0)
    except Exception:
        page = 0

    kws_in = obj.get("keywords") or []
    if not isinstance(kws_in, list):
        kws_in = []
    kws_in = [k for k in kws_in if isinstance(k, str) and k.strip()]
    if len(kws_in) < 3:
        # 若上游沒填滿，這裡補滿 3 個以穩定 prompt
        while len(kws_in) < 3:
            kws_in.append(f"KW_{len(kws_in)+1}")
    else:
        kws_in = kws_in[:3]

    prompt = _build_prompt_with_keywords(
        chunk_text=text,
        source=source,
        page=page,
        keywords=kws_in,
        base_n=base_n,
        per_kw_n=per_kw_n,
        langs=langs,
    )

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            raw = ask_question_llm(prompt)
            data = _safe_json_extract(raw)
            if "keywords" not in data or not data["keywords"]:
                data["keywords"] = kws_in
            norm = _normalize_questions(data, expect_base=base_n, expect_kw=per_kw_n)

            # 攤平成輸出
            all_qs = []
            for q in norm["base_questions"]:
                q2 = dict(q)
                q2["source_type"] = "base"
                all_qs.append(q2)
            for item in norm["keyword_questions"]:
                kw = item["keyword"]
                for q in item["questions"]:
                    q2 = dict(q)
                    q2["source_type"] = "kw"
                    q2["keyword"] = kw
                    all_qs.append(q2)

            chunk_id = obj.get("chunk_id", line_no)
            out = {
                "chunk_id": chunk_id,
                "source": source,
                "page": page,
                "keywords": norm["keywords"],
                "questions": all_qs,      # base_n + 3 * per_kw_n
                "preview": text[:200],    # 方便快速檢視
            }
            return line_no, out

        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep((attempt + 1) * backoff)
            else:
                # 失敗時依然輸出佔位，避免中斷整批
                chunk_id = obj.get("chunk_id", line_no)
                placeholder = {
                    "chunk_id": chunk_id,
                    "source": source,
                    "page": page,
                    "keywords": kws_in,
                    "questions": [{
                        "text": f"[ERROR] question generation failed: {str(last_err)}",
                        "lang": "en",
                        "difficulty": "easy",
                        "topic": "error",
                        "source_type": "base",
                    }],
                    "preview": text[:200],
                    "error": str(last_err),
                }
                return line_no, placeholder

    # 理論上不會到這裡
    chunk_id = obj.get("chunk_id", line_no)
    return line_no, {
        "chunk_id": chunk_id,
        "source": source,
        "page": page,
        "keywords": kws_in,
        "questions": [{
            "text": "[UNKNOWN ERROR] generation fell through.",
            "lang": "en",
            "difficulty": "easy",
            "topic": "error",
            "source_type": "base",
        }],
        "preview": text[:200],
        "error": "unknown",
    }


# -------------------- 主程式 --------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--keywords", default="data/chunk_k.jsonl",
                        help="Path to keyword JSONL (output of the keyword generator).")
    parser.add_argument("--out", default="data/questions.jsonl",
                        help="Output JSONL path for generated questions.")
    parser.add_argument("--langs", default="zh,en",
                        help="Preferred languages, comma-separated (e.g., 'zh,en').")
    parser.add_argument("--base-n", type=int, default=5,
                        help="Number of base questions per chunk.")
    parser.add_argument("--per-kw-n", type=int, default=2,
                        help="Number of questions per keyword (with 3 keywords).")
    parser.add_argument("--max-chunks", type=int, default=0,
                        help="Limit the number of records to process from --keywords; 0 = no limit.")
    parser.add_argument("--workers", type=int, default=8,
                        help="Number of parallel workers (threads).")
    parser.add_argument("--retries", type=int, default=2,
                        help="Retries per item when LLM call fails.")
    parser.add_argument("--backoff", type=float, default=1.2,
                        help="Backoff base (seconds multiplier) between retries.")

    args = parser.parse_args()
    langs = [s.strip() for s in args.langs.split(",") if s.strip()]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    # 逐行載入（streaming），避免整檔載入記憶體
    iterable = _iter_keyword_jsonl(args.keywords)
    if args.max_chunks and args.max_chunks > 0:
        # 切成固定長度
        iterable = (x for i, x in enumerate(iterable) if i < args.max_chunks)

    print(f"[info] reading from: {args.keywords}")
    print(f"[info] writing to  : {args.out}")
    print(f"[info] workers     : {args.workers}")
    print(f"[info] base_n / per_kw_n : {args.base_n} / {args.per_kw_n}")

    n_submitted = 0
    n_done = 0
    t0 = time.time()

    # 直接邊取邊送 job，邊寫出結果
    with open(args.out, "w", encoding="utf-8") as fout, \
         ThreadPoolExecutor(max_workers=args.workers) as ex:

        futures = {}
        # 提交一批
        for line_no, obj in iterable:
            fut = ex.submit(
                _one_job,
                line_no, obj,
                args.base_n, args.per_kw_n, langs,
                args.retries, args.backoff
            )
            futures[fut] = line_no
            n_submitted += 1

        # 逐個完成就寫出
        for fut in as_completed(futures):
            try:
                line_no, rec = fut.result()
            except Exception as e:
                # 理論上 _one_job 已經兜底；這裡是額外保險
                line_no = futures[fut]
                rec = {
                    "chunk_id": line_no,
                    "source": "unknown",
                    "page": 0,
                    "keywords": ["KW_1", "KW_2", "KW_3"],
                    "questions": [{
                        "text": f"[FUTURE ERROR] {str(e)}",
                        "lang": "en",
                        "difficulty": "easy",
                        "topic": "error",
                        "source_type": "base",
                    }],
                    "preview": "",
                    "error": str(e),
                }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_done += 1
            if n_done % 50 == 0:
                elapsed = time.time() - t0
                print(f"[info] completed {n_done}/{n_submitted} in {elapsed:.1f}s")

    elapsed = time.time() - t0
    print(f"[done] wrote {n_done} records to {args.out} in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
