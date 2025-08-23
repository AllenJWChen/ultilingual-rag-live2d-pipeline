# -*- coding: utf-8 -*-
from __future__ import annotations

"""
改進版Keyword LLM runner - 支援優化chunks格式和更好的關鍵字生成

主要改進：
1. 支援優化版chunks格式（包含quality_score）
2. 更智能的關鍵字生成策略
3. 批量處理和上下文感知
4. 更好的錯誤處理和重試機制
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
    tqdm = None

# project-local
from .clients import generate_keywords, generate_keywords_batch


# ---------- 改進版chunk載入 ----------
def _load_from_jsonl(path: str) -> List[Dict]:
    """支援優化版chunks格式的載入"""
    items: List[Dict] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
            except Exception as e:
                print(f"[WARN] Line {line_no}: JSON解析失敗 - {e}")
                continue
                
            text = (obj.get("text") or "").strip()
            if not text:
                continue
                
            # 支援優化版本的額外字段
            chunk_data = {
                "text": text,
                "source": obj.get("source", obj.get("file", "unknown")),
                "page": int(obj.get("page", 0) or 0),
            }
            
            # 保留優化版本的品質信息
            if "quality_score" in obj:
                chunk_data["quality_score"] = obj["quality_score"]
            if "length" in obj:  
                chunk_data["length"] = obj["length"]
            if "_quality" in obj:  # 兼容格式
                chunk_data["_quality"] = obj["_quality"]
                
            items.append(chunk_data)
    return items


def _load_from_txt(path: str) -> List[Dict]:
    """保持原有的txt格式支援"""
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


def load_chunks(index_dir: str, input_file: str = None) -> List[Dict]:
    """
    改進版chunk載入 - 支援指定特定文件
    """
    if input_file:
        # 如果指定了具體文件
        file_path = input_file if os.path.isabs(input_file) else os.path.join(index_dir, input_file)
        if os.path.exists(file_path):
            if file_path.endswith('.jsonl'):
                return _load_from_jsonl(file_path)
            else:
                return _load_from_txt(file_path)
    
    # 原有邏輯：自動查找
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


# ---------- 改進版worker ----------
def _trim(s: str, max_chars: int) -> str:
    if max_chars <= 0 or len(s) <= max_chars:
        return s
    return s[:max_chars]


def _detect_content_type(text: str) -> str:
    """
    自動檢測內容類型以改進關鍵字生成
    """
    text_lower = text.lower()
    
    # 技術文件指標
    tech_indicators = ["display", "led", "oled", "cpu", "gpu", "algorithm", "protocol", "specification"]
    # 商業文件指標  
    business_indicators = ["market", "revenue", "business", "strategy", "competition", "growth"]
    # 學術文件指標
    academic_indicators = ["research", "study", "analysis", "methodology", "experiment", "conclusion"]
    
    tech_score = sum(1 for indicator in tech_indicators if indicator in text_lower)
    business_score = sum(1 for indicator in business_indicators if indicator in text_lower)
    academic_score = sum(1 for indicator in academic_indicators if indicator in text_lower)
    
    max_score = max(tech_score, business_score, academic_score)
    if max_score == 0:
        return "general"
    elif tech_score == max_score:
        return "technical"
    elif business_score == max_score:
        return "business"
    else:
        return "academic"


def _one_job(idx: int, rec: Dict, kw_lang: str, max_chars: int,
             retries: int = 2, backoff: float = 1.2) -> Tuple[int, Dict]:
    """
    改進版單個任務處理 - 更智能的關鍵字生成
    """
    full_text = (rec.get("text") or "").strip()
    text_for_llm = _trim(full_text, max_chars)

    source = rec.get("source", rec.get("file", "unknown"))
    try:
        page = int(rec.get("page", 0) or 0)
    except Exception:
        page = 0

    def _make_record(kws: list, error: str = None, content_type: str = "unknown") -> Dict:
        out = {
            "chunk_id": idx,
            "source": source,
            "page": page,
            "text": full_text,
            "keywords": kws,
            "preview": full_text[:120],  # 增加預覽長度
        }
        
        # 保留優化版本的額外信息
        if "quality_score" in rec:
            out["quality_score"] = rec["quality_score"]
        if "_quality" in rec:
            out["_quality"] = rec["_quality"]
            
        # 添加內容類型信息
        out["content_type"] = content_type
        
        if error:
            out["error"] = error
        return out

    # 檢測內容類型
    content_type = _detect_content_type(full_text)
    
    last_err = None
    for attempt in range(retries + 1):
        try:
            # 使用改進的關鍵字生成
            kws = generate_keywords(text_for_llm, n=3, lang=kw_lang, content_type=content_type)
            
            # 確保有效性
            kws = [k for k in kws if isinstance(k, str) and k.strip()]
            if not kws:
                kws = [f"fallback_kw_{i+1}" for i in range(3)]
            elif len(kws) < 3:
                kws.extend([f"supplementary_{i+1}" for i in range(3 - len(kws))])
            
            return idx, _make_record(kws[:3], content_type=content_type)
            
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep((attempt + 1) * backoff)
            else:
                fallback_kws = [f"error_fallback_{i+1}" for i in range(3)]
                return idx, _make_record(
                    fallback_kws,
                    error=str(last_err),
                    content_type=content_type
                )

    return idx, _make_record(
        [f"unknown_error_{i+1}" for i in range(3)],
        error="unknown",
        content_type=content_type
    )


def _batch_process_with_context(chunks: List[Dict], kw_lang: str, max_chars: int) -> List[Dict]:
    """
    批量處理 - 考慮上下文相關性
    """
    print(f"[INFO] 使用批量上下文處理模式")
    
    # 準備數據
    processed_chunks = []
    for i, chunk in enumerate(chunks):
        chunk_copy = chunk.copy()
        chunk_copy["text"] = _trim(chunk["text"], max_chars)
        processed_chunks.append(chunk_copy)
    
    # 批量生成關鍵字
    results = generate_keywords_batch(processed_chunks, n=3, lang=kw_lang)
    
    # 轉換為輸出格式
    output_records = []
    for i, result in enumerate(results):
        source = result.get("source", "unknown")
        try:
            page = int(result.get("page", 0) or 0)
        except Exception:
            page = 0
            
        full_text = chunks[i]["text"]  # 使用原始完整文本
        
        out_record = {
            "chunk_id": i,
            "source": source,
            "page": page,
            "text": full_text,
            "keywords": result.get("keywords", [f"batch_kw_{j+1}" for j in range(3)]),
            "preview": full_text[:120],
        }
        
        # 保留額外信息
        if "quality_score" in result:
            out_record["quality_score"] = result["quality_score"]
        if "_quality" in result:
            out_record["_quality"] = result["_quality"]
            
        output_records.append(out_record)
    
    return output_records


# ---------- 主程序 ----------
def main():
    parser = argparse.ArgumentParser(description="改進版關鍵字生成工具")
    parser.add_argument("--index", default="indices", help="索引目錄")
    parser.add_argument("--input-file", help="指定特定的chunks文件 (可選)")
    parser.add_argument("--out", default="outputs/data/chunk_keywords.jsonl", help="輸出文件")
    parser.add_argument("--langs", default="zh,en", help="語言提示，第一個作為主要語言")
    parser.add_argument("--max-chunks", type=int, default=0, help="限制處理chunks數量 (0=全部)")
    parser.add_argument("--workers", type=int, default=1, help="並行worker數量")
    parser.add_argument("--max-chars", type=int, default=1400, help="發送給LLM前的文本截斷長度")
    parser.add_argument("--batch-mode", action="store_true", help="使用批量上下文處理模式")
    
    args = parser.parse_args()

    langs = [s.strip() for s in args.langs.split(",") if s.strip()]
    kw_lang = langs[0] if langs else "auto"

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    # 載入chunks
    chunks = load_chunks(args.index, args.input_file)
    if args.max_chunks and args.max_chunks > 0:
        chunks = chunks[:args.max_chunks]
    
    print(f"[INFO] 從 '{args.index}' 載入了 {len(chunks)} 個chunks")
    if args.input_file:
        print(f"[INFO] 使用指定文件: {args.input_file}")
    
    # 顯示chunks統計
    quality_chunks = len([c for c in chunks if c.get("quality_score", 0) > 0])
    if quality_chunks > 0:
        avg_quality = sum(c.get("quality_score", 0) for c in chunks) / quality_chunks
        print(f"[INFO] 發現 {quality_chunks} 個帶品質評分的chunks，平均品質: {avg_quality:.3f}")

    workers = max(1, int(args.workers))
    
    with open(args.out, "w", encoding="utf-8") as fout:
        if args.batch_mode:
            # 批量上下文模式
            results = _batch_process_with_context(chunks, kw_lang, args.max_chars)
            for record in results:
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            
        elif workers == 1:
            # 順序處理
            iterator = enumerate(chunks)
            progress = iterator
            if tqdm:
                progress = tqdm(iterator, total=len(chunks), desc="生成關鍵字", unit="chunk")
            
            for i, rec in progress:
                _, outrec = _one_job(i, rec, kw_lang=kw_lang, max_chars=args.max_chars)
                fout.write(json.dumps(outrec, ensure_ascii=False) + "\n")
                
        else:
            # 並行處理
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futures = []
                for i, rec in enumerate(chunks):
                    futures.append(ex.submit(_one_job, i, rec, kw_lang, args.max_chars))
                
                if tqdm:
                    fut_iter = tqdm(as_completed(futures), total=len(futures), 
                                  desc="生成關鍵字", unit="chunk")
                else:
                    fut_iter = as_completed(futures)
                    
                for fut in fut_iter:
                    _, outrec = fut.result()
                    fout.write(json.dumps(outrec, ensure_ascii=False) + "\n")

    print(f"[OK] 已寫入 {len(chunks)} 條記錄到 {args.out}")
    
    # 顯示處理統計
    content_types = {}
    error_count = 0
    
    with open(args.out, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                content_type = record.get("content_type", "unknown")
                content_types[content_type] = content_types.get(content_type, 0) + 1
                if record.get("error"):
                    error_count += 1
            except:
                pass
    
    print(f"[INFO] 內容類型分布: {content_types}")
    if error_count > 0:
        print(f"[WARN] 處理過程中有 {error_count} 個錯誤")


if __name__ == "__main__":
    main()