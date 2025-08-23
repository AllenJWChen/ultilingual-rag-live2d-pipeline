# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import List, Dict
# 頂部加：
from tqdm import tqdm

import os, json, re, argparse

from .prompts_keywords import build_keywords_prompt
from .llm_clients import ask_keywords_llm

# ---- add this helper right under the imports ----
def generate_keywords(text: str, n: int = 3, lang: str = "en"):
    """Build prompt -> call LLM -> return 3 keywords."""
    prompt = build_keywords_prompt(text=text, n=n, lang=lang)
    return ask_keywords_llm(prompt)

def _load_chunks(index_dir: str) -> List[Dict]:
    """
    優先讀 indices/chunks.jsonl（新格式），
    找不到時再回退到舊的 chunks.txt / metadata.json。
    需要回傳每筆至少包含: text, source, page
    """
    import os, json, re
    from typing import List, Dict

    jsonl_path = os.path.join(index_dir, "chunks.jsonl")
    txt_path   = os.path.join(index_dir, "chunks.txt")
    meta_path  = os.path.join(index_dir, "metadata.json")

    # 1) JSONL（新格式，建議用）
    if os.path.exists(jsonl_path):
        items: List[Dict] = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line: 
                    continue
                try:
                    rec = json.loads(line)
                    text = (rec.get("text") or "").strip()
                    if not text:
                        continue
                    items.append({
                        "text": text,
                        "source": rec.get("source", "unknown"),
                        "page": int(rec.get("page", 0) or 0),
                    })
                except Exception:
                    continue
        return items

    # 2) 既有 metadata.json
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if isinstance(meta, dict) and isinstance(meta.get("chunks"), list):
                out = []
                for c in meta["chunks"]:
                    if isinstance(c, dict) and (c.get("text") or "").strip():
                        out.append({
                            "text": c["text"].strip(),
                            "source": c.get("source", "unknown"),
                            "page": int(c.get("page", 0) or 0),
                        })
                if out:
                    return out
        except Exception:
            pass

    # 3) 舊的 chunks.txt（支援 JSONL/TSV/PIPE/區塊標頭）
    tmp: List[Dict] = []
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                # 單行 JSON
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
                # TSV: src \t page \t text
                if "\t" in s:
                    parts = s.split("\t", 2)
                    if len(parts) == 3:
                        src, pg, txt = parts
                        try:    pg_i = int(pg)
                        except: pg_i = 0
                        if txt.strip():
                            tmp.append({"text": txt.strip(), "source": src or "unknown", "page": pg_i})
                            continue
                # PIPE: src ||| page ||| text
                if "|||" in s:
                    parts = s.split("|||", 2)
                    if len(parts) == 3:
                        src, pg, txt = [p.strip() for p in parts]
                        try:    pg_i = int(pg)
                        except: pg_i = 0
                        if txt:
                            tmp.append({"text": txt, "source": src or "unknown", "page": pg_i})
                            continue
    if tmp:
        return tmp

    # 4) 區塊標頭格式：[<source> | page N] ...（最後保底）
    blocks: List[Dict] = []
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8", errors="replace") as f:
            blob = f.read()
        text_all = blob.replace("\\n", "\n")
        header_re = re.compile(r'\[(.+?)\s*\|\s*page\s+(\d+)\]', re.IGNORECASE)
        matches = list(header_re.finditer(text_all))
        for i, m in enumerate(matches):
            src = m.group(1).strip()
            try:    pg = int(m.group(2))
            except: pg = 0
            start = m.end()
            end = matches[i+1].start() if i+1 < len(matches) else len(text_all)
            body = text_all[start:end].strip()
            if body:
                blocks.append({"text": body, "source": src, "page": pg})
    return blocks


# --- make_keywords.py 修正版 ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", default="indices")
    parser.add_argument("--out", default="data/chunk_k.jsonl")
    parser.add_argument("--langs", default="zh,en")   # ✅ 多語支援
    parser.add_argument("--max-chunks", type=int, default=0)
    args = parser.parse_args()

    # ✅ 轉成 list
    langs = [s.strip() for s in args.langs.split(",") if s.strip()]
    main_lang = langs[0] if langs else "en"

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    chunks = _load_chunks(args.index)
    if args.max_chunks > 0:
        chunks = chunks[: args.max_chunks]

    print(f"[info] loaded {len(chunks)} chunks from '{args.index}'")

    n_written = 0
    # ✅ with 區塊內縮
    with open(args.out, "w", encoding="utf-8") as fout:
        for i, c in enumerate(tqdm(chunks, desc="keywords", unit="chunk")):
            text = (c.get("text") or "").strip()
            if not text:
                continue
            # ✅ 用 main_lang
            kws = generate_keywords(text, n=3, lang=main_lang)
            rec = {
                "chunk_id": i,
                "source": c.get("source", "unknown"),
                "page": int(c.get("page", 0) or 0),
                "keywords": kws,
                "preview": text[:200],
            }
            fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_written += 1   # ✅ 計數

    print(f"[OK] wrote {n_written} lines → {args.out}")


if __name__ == "__main__":
    main()
