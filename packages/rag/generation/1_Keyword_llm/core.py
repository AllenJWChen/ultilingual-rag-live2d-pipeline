# -*- coding: utf-8 -*-
from __future__ import annotations

"""
Keyword LLM runner (parallel-ready)

Usage (basic):
  python -m packages.rag.generation.Keyword_llm.make_keywords

Custom:
  python -m packages.rag.generation.Keyword_llm.make_keywords ^
    --index indices ^
    --out data/chunk_k.jsonl ^
    --langs zh,en ^
    --max-chunks 0 ^
    --workers 8 ^
    --max-chars 1600

Env (OpenAI-compatible / Ollama):
  $env:LLM_MODE="OPENAI_COMPAT"
  $env:OPENAI_BASE_URL="http://localhost:11434/v1"
  $env:OPENAI_API_KEY="ollama"
  $env:MODEL_KEYWORDS="llama3.1:latest"
"""

import os
import json
import re
import time
import argparse
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm.auto import tqdm
except Exception:
    tqdm = None  # type: ignore

# project-local
from .llm_clients import generate_keywords  # expects: (text: str, n: int = 3, lang: str = "auto") -> List[str]


# ---------- chunk loading ----------
def _load_from_jsonl(path: str) -> List[Dict]:
    items: List[Dict] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
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
            items.append({
                "text": text,
                "source": obj.get("source", obj.get("file", "unknown")),
                "page": int(obj.get("page", 0) or 0),
            })
    return items


def _load_from_txt(path: str) -> List[Dict]:
    """Accepts JSONL, TSV, PIPE, or BLOCK header format inside a .txt file."""
    # fast path line-wise
    tmp: List[Dict] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            s = raw.strip()
            if not s:
                continue
            # JSONL try
            if s.startswith("{") and s.endswith("}"):
                try:
                    obj = json.loads(s)
                    text = (obj.get("text") or "").strip()
                    if not text:
                        continue
                    tmp.append({
                        "text": text,
                        "source": obj.get("source", obj.get("file", "unknown")),
                        "page": int(obj.get("page", 0) or 0),
                    })
                    continue
                except Exception:
                    pass
            # TSV: src \t page \t text
            if "\t" in s:
                parts = s.split("\t", 2)
                if len(parts) == 3:
                    src, pg, txt = parts
                    try:
                        pg_i = int(pg)
                    except Exception:
                        pg_i = 0
                    if txt.strip():
                        tmp.append({"text": txt.strip(), "source": src or "unknown", "page": pg_i})
                        continue
            # PIPE: src ||| page ||| text
            if "|||" in s:
                parts = s.split("|||", 2)
                if len(parts) == 3:
                    src, pg, txt = [p.strip() for p in parts]
                    try:
                        pg_i = int(pg)
                    except Exception:
                        pg_i = 0
                    if txt:
                        tmp.append({"text": txt, "source": src or "unknown", "page": pg_i})
                        continue

    if len(tmp) >= 5:
        return tmp

    # BLOCK format: [<source> | page N] then multi-line content
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        blob = f.read()
    text_all = blob.replace("\\n", "\n")
    header_re = re.compile(r'\[(.+?)\s*\|\s*page\s+(\d+)\]', re.IGNORECASE)

    items: List[Dict] = []
    matches = list(header_re.finditer(text_all))
    for i, m in enumerate(matches):
        src = m.group(1).strip()
        try:
            pg = int(m.group(2))
        except Exception:
            pg = 0
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text_all)
        body = text_all[start:end].strip()
        if body:
            items.append({"text": body, "source": src, "page": pg})
    return items


def load_chunks(index_dir: str) -> List[Dict]:
    jsonl_path = os.path.join(index_dir, "chunks.jsonl")
    txt_path = os.path.join(index_dir, "chunks.txt")
    if os.path.exists(jsonl_path):
        rows = _load_from_jsonl(jsonl_path)
        if rows:
            return rows
    if os.path.exists(txt_path):
        rows = _load_from_txt(txt_path)
        if rows:
            return rows
    return []


# ---------- worker ----------
def _trim(s: str, max_chars: int) -> str:
    if max_chars <= 0 or len(s) <= max_chars:
        return s
    return s[:max_chars]


def _one_job(idx: int, rec: Dict, kw_lang: str, max_chars: int, retries: int = 2, backoff: float = 1.2) -> Tuple[int, Dict]:
    """
    Returns (idx, output_record) where output_record:
      {
        "chunk_id": idx, "source": ..., "page": ..., "keywords": [...], "preview": ...
      }
    """
    text = _trim((rec.get("text") or "").strip(), max_chars)
    source = rec.get("source", rec.get("file", "unknown"))
    try:
        page = int(rec.get("page", 0) or 0)
    except Exception:
        page = 0

    last_err: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            kws = generate_keywords(text, n=3, lang=kw_lang)  # expects list[str]
            kws = [k for k in kws if isinstance(k, str) and k.strip()]
            # pad/truncate to exactly 3
            kws = (kws + [f"KW_{i}" for i in range(1, 4)])[:3]
            return idx, {
                "chunk_id": idx,
                "source": source,
                "page": page,
                "keywords": kws,
                "preview": text[:200]
            }
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep((attempt + 1) * backoff)
            else:
                # fallback placeholder
                return idx, {
                    "chunk_id": idx,
                    "source": source,
                    "page": page,
                    "keywords": [f"KW_{i}" for i in range(1, 4)],
                    "preview": text[:200],
                    "error": str(last_err)
                }

    # should not reach here
    return idx, {
        "chunk_id": idx,
        "source": source,
        "page": page,
        "keywords": [f"KW_{i}" for i in range(1, 4)],
        "preview": text[:200],
        "error": "unknown"
    }


# ---------- main ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default="indices")
    parser.add_argument("--out", default="data/chunk_k.jsonl")
    parser.add_argument("--langs", default="zh,en", help="language hint(s) for keywords; first item used as primary")
    parser.add_argument("--max-chunks", type=int, default=0, help="limit number of chunks (0 = all)")
    parser.add_argument("--workers", type=int, default=1, help="parallel workers (threads)")
    parser.add_argument("--max-chars", type=int, default=1400, help="truncate chunk text before sending to LLM")
    args = parser.parse_args()

    langs = [s.strip() for s in args.langs.split(",") if s.strip()]
    kw_lang = langs[0] if langs else "auto"

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    chunks = load_chunks(args.index)
    if args.max_chunks and args.max_chunks > 0:
        chunks = chunks[: args.max_chunks]
    print(f"[info] loaded {len(chunks)} chunks from '{args.index}'")

    # prepare executor
    workers = max(1, int(args.workers))
    jobs = []
    with open(args.out, "w", encoding="utf-8") as fout:
        if workers == 1:
            # sequential
            iterator = enumerate(chunks)
            progress = iterator
            if tqdm:
                progress = tqdm(iterator, total=len(chunks), desc="keywords", unit="chunk")
            for i, rec in progress:
                _, outrec = _one_job(i, rec, kw_lang=kw_lang, max_chars=args.max_chars)
                fout.write(json.dumps(outrec, ensure_ascii=False) + "\n")
        else:
            # threaded parallel
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futures = []
                for i, rec in enumerate(chunks):
                    futures.append(ex.submit(_one_job, i, rec, kw_lang, args.max_chars))
                if tqdm:
                    fut_iter = tqdm(as_completed(futures), total=len(futures), desc="keywords", unit="chunk")
                else:
                    fut_iter = as_completed(futures)
                for fut in fut_iter:
                    _, outrec = fut.result()
                    fout.write(json.dumps(outrec, ensure_ascii=False) + "\n")

    print(f"[OK] wrote {len(chunks)} lines → {args.out}")


if __name__ == "__main__":
    main()
