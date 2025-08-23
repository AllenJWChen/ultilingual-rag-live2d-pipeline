# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Dict
import os
import json
import re
import argparse

from .prompts_dataset import build_question_prompt
from .llm_clients import ask_question_llm



def _load_chunks(index_dir: str) -> List[Dict]:
    """
    Load chunks from:
      1) metadata.json -> meta["chunks"]
      2) chunks.txt as:
         a) JSONL: {"text": "...", "source": "...", "page": 12}
         b) TSV:   source \t page \t text
         c) PIPE:  source ||| page ||| text
         d) BLOCK: [<source> | page <n>] ... until next header (file may contain literal '\n')
    """
    import json, os, re

    meta_path = os.path.join(index_dir, "metadata.json")
    chunks_path = os.path.join(index_dir, "chunks.txt")

    # ---------- 1) metadata.json ----------
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if isinstance(meta, dict) and isinstance(meta.get("chunks"), list):
                items = [c for c in meta["chunks"] if isinstance(c, dict) and (c.get("text") or "").strip()]
                if len(items) >= 5:
                    return items
        except Exception:
            pass

    if not os.path.exists(chunks_path):
        return []

    # ---------- 2) quick single-line formats (JSONL / TSV / PIPE) ----------
    tmp: List[Dict] = []
    with open(chunks_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            # JSONL?
            if s.startswith("{") and s.endswith("}"):
                try:
                    obj = json.loads(s)
                    text = (obj.get("text") or "").strip()
                    if text:
                        tmp.append({
                            "text": text,
                            "source": obj.get("source", obj.get("file", "unknown")),
                            "page": int(obj.get("page", 0) or 0),
                        })
                        continue
                except Exception:
                    pass
            # TSV: source \t page \t text
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
            # PIPE: source ||| page ||| text
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

    # ---------- 3) BLOCK format over the whole file ----------
    # Read the entire file as a single string; many dumps store literal "\n" sequences.
    with open(chunks_path, "r", encoding="utf-8", errors="replace") as f:
        blob = f.read()

    # Normalize literal "\n" into real newlines for easier slicing
    # but also keep original for safety if there are real newlines already.
    text_all = blob.replace("\\n", "\n")

    # Header like: [<source> | page 12]
    header_re = re.compile(r'\[(.+?)\s*\|\s*page\s+(\d+)\]', re.IGNORECASE)
    blocks: List[Dict] = []

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
            blocks.append({"text": body, "source": src, "page": pg})

    return blocks


# ---------- helpers below _load_chunks ----------

def _safe_json_extract(s: str) -> Dict:
    """Try to extract a top-level JSON object from a raw string."""
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
    Ensure structure:
      - 3 keywords
      - 5 base questions
      - 2 questions per keyword (3 keywords)
    If missing, truncate/pad with placeholders.
    """
    out = {"keywords": [], "base_questions": [], "keyword_questions": []}

    # keywords
    kws = [k for k in (data.get("keywords") or []) if isinstance(k, str) and k.strip()]
    kws = kws[:3]
    while len(kws) < 3:
        kws.append(f"KW_{len(kws)+1}")
    out["keywords"] = kws

    # base questions
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

    # keyword questions
    kwq_list = []
    provided = data.get("keyword_questions") or []
    for kw in kws:
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default="indices")
    parser.add_argument("--out", default="data/questions.jsonl")
    parser.add_argument("--langs", default="zh,en")
    parser.add_argument("--max-chunks", type=int, default=0)
    args = parser.parse_args()

    langs = [s.strip() for s in args.langs.split(",") if s.strip()]

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    chunks = _load_chunks(args.index)
    if args.max_chunks > 0:
        chunks = chunks[: args.max_chunks]

    print(f"[info] loaded {len(chunks)} chunks from '{args.index}'")

    n_written = 0
    with open(args.out, "w", encoding="utf-8") as fout:
        for i, c in enumerate(chunks):
            text = (c.get("text") or "").strip()
            if not text:
                continue
            source = c.get("source", c.get("file", "unknown"))
            try:
                page = int(c.get("page", 0) or 0)
            except Exception:
                page = 0

            prompt = build_question_prompt(
                chunk_text=text,
                source=source,
                page=page,
                base_n=5,
                per_kw_n=2,
                langs=langs,
            )
            raw = ask_question_llm(prompt)
            data = _safe_json_extract(raw)
            norm = _normalize_questions(data, expect_base=5, expect_kw=2)

            # flatten to 11 questions (5 base + 6 keyword)
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

            rec = {
                "chunk_id": i,
                "source": source,
                "page": page,
                "keywords": norm["keywords"],
                "questions": all_qs,   # 11 items
                "preview": text[:200],
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_written += 1

    print(f"Done. Wrote {n_written} lines to {args.out}")


if __name__ == "__main__":
    main()

