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
TQDM_AVAILABLE = tqdm is not None

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
    jsonl_path = os.path.join(index_dir, "chunks_optimized.jsonl")
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
    輸出包含完整chunks內容，便於後續問題生成
    """
    full_text = (rec.get("text") or "").strip()
    text_for_llm = _trim(full_text, max_chars)

    source = rec.get("source", rec.get("file", "unknown"))
    try:
        page = int(rec.get("page", 0) or 0)
    except Exception:
        page = 0

    def _make_record(kws: list, error: str = None, content_type: str = "unknown") -> Dict:
        # 包含完整chunks資訊的輸出格式
        out = {
            "chunk_id": idx,
            "source": source,
            "page": page,
            "text": full_text,  # 🎯 完整文字內容
            "keywords": kws,
            "preview": full_text[:150],  # 適當長度的預覽
            "content_type": content_type,
            "text_length": len(full_text),  # 文字長度統計
        }
        
        # 保留優化版本的額外信息
        if "quality_score" in rec:
            out["quality_score"] = rec["quality_score"]
        if "_quality" in rec:
            out["_quality"] = rec["_quality"]
        if "length" in rec:
            out["original_length"] = rec["length"]
            
        # 添加keywords統計
        out["keywords_count"] = len(kws)
        
        if error:
            out["error"] = error
            out["has_error"] = True
        else:
            out["has_error"] = False
            
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
    批量處理 - 考慮上下文相關性，輸出完整chunks內容
    """
    print(f"[INFO] 使用批量上下文處理模式")
    
    # 準備數據
    processed_chunks = []
    
    # 添加數據準備進度條
    if TQDM_AVAILABLE:
        chunk_iter = tqdm(enumerate(chunks), total=len(chunks), desc="準備數據", unit="chunk")
    else:
        chunk_iter = enumerate(chunks)
        print(f"[INFO] 準備 {len(chunks)} 個chunks的數據...")
        
    for i, chunk in chunk_iter:
        chunk_copy = chunk.copy()
        chunk_copy["text"] = _trim(chunk["text"], max_chars)
        processed_chunks.append(chunk_copy)
    
    # 批量生成關鍵字
    print(f"[INFO] 開始批量關鍵字生成...")
    results = generate_keywords_batch(processed_chunks, n=3, lang=kw_lang)
    
    # 轉換為輸出格式 - 包含完整內容
    output_records = []
    
    # 添加結果處理進度條
    if TQDM_AVAILABLE:
        result_iter = tqdm(enumerate(results), total=len(results), 
                          desc="處理結果", unit="chunk")
    else:
        result_iter = enumerate(results)
        print(f"[INFO] 處理 {len(results)} 個結果...")
        
    for i, result in result_iter:
        source = result.get("source", "unknown")
        try:
            page = int(result.get("page", 0) or 0)
        except Exception:
            page = 0
            
        full_text = chunks[i]["text"]  # 使用原始完整文本
        keywords = result.get("keywords", [f"batch_kw_{j+1}" for j in range(3)])
        
        out_record = {
            "chunk_id": i,
            "source": source,
            "page": page,
            "text": full_text,  # 🎯 完整文字內容
            "keywords": keywords,
            "preview": full_text[:150],
            "content_type": _detect_content_type(full_text),
            "text_length": len(full_text),
            "keywords_count": len(keywords),
            "has_error": False,
        }
        
        # 保留額外信息
        if "quality_score" in result:
            out_record["quality_score"] = result["quality_score"]
        if "_quality" in result:
            out_record["_quality"] = result["_quality"]
        if "length" in result:
            out_record["original_length"] = result["length"]
            
        output_records.append(out_record)
    
    print(f"[INFO] 批量處理完成，生成 {len(output_records)} 條記錄")
    return output_records


def main():
    parser = argparse.ArgumentParser(description="改進版關鍵字生成工具")
    parser.add_argument("--index", default="indices", help="索引目錄")
    parser.add_argument("--input-file", help="指定特定的chunks文件 (可選)")
    parser.add_argument("--out", default="outputs/data/keywords_optimized.jsonl", help="輸出文件")
    parser.add_argument("--langs", default="zh,en", help="語言提示，第一個作為主要語言")
    parser.add_argument("--max-chunks", type=int, default=0, help="限制處理chunks數量 (0=全部)")
    parser.add_argument("--workers", type=int, default=32, help="並行worker數量 (預設32，最佳效能)")
    parser.add_argument("--max-chars", type=int, default=1400, help="發送給LLM前的文本截斷長度")
    parser.add_argument("--batch-mode", action="store_true", help="使用批量上下文處理模式")
    parser.add_argument("--fast", action="store_true", help="快速模式：32 workers + 最佳化設定")
    
    args = parser.parse_args()

    # 快速模式設定
    if args.fast:
        args.workers = 32
        args.batch_mode = False  # 高併發時不用batch模式
        print(f"[FAST] 啟用快速模式：32 workers，最佳化併發處理")

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

    print(f"[INFO] 使用 {args.workers} 個並行workers進行關鍵字生成")

    # 為高併發優化環境變數
    if args.workers >= 16:
        os.environ.setdefault("OLLAMA_NUM_PARALLEL", str(args.workers))
        print(f"[INFO] 已設定 OLLAMA_NUM_PARALLEL={args.workers} 最佳化並發處理")
    
    # 檢查tqdm可用性並提供回退方案
    use_progress_bar = TQDM_AVAILABLE
    if not use_progress_bar:
        print(f"[WARN] tqdm不可用，將使用文字進度顯示")
    else:
        print(f"[INFO] 使用進度條顯示處理進度")
    
    with open(args.out, "w", encoding="utf-8") as fout:
        if args.batch_mode:
            # 批量上下文模式
            print(f"[INFO] 使用批量上下文處理模式")
            results = _batch_process_with_context(chunks, kw_lang, args.max_chars)
            for record in results:
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            
        elif args.workers == 1:
            # 順序處理 - 改進版進度條
            start_time = time.time()
            error_count_live = 0
            
            if TQDM_AVAILABLE:
                # 簡化的進度條
                with tqdm(enumerate(chunks), 
                         total=len(chunks), 
                         desc="關鍵字生成-順序",
                         unit="chunk") as progress:
                    
                    for i, rec in progress:
                        _, outrec = _one_job(i, rec, kw_lang=kw_lang, max_chars=args.max_chars)
                        fout.write(json.dumps(outrec, ensure_ascii=False) + "\n")
                        
                        # 更新錯誤統計
                        if outrec.get("has_error", False):
                            error_count_live += 1
                        
                        # 每10個更新一次描述
                        if (i + 1) % 10 == 0:
                            success_count = (i + 1) - error_count_live
                            progress.set_description(f"關鍵字生成-順序 [✓{success_count} ✗{error_count_live}]")
            else:
                # 無進度條版本
                for i, rec in enumerate(chunks):
                    _, outrec = _one_job(i, rec, kw_lang=kw_lang, max_chars=args.max_chars)
                    fout.write(json.dumps(outrec, ensure_ascii=False) + "\n")
                    
                    if outrec.get("has_error", False):
                        error_count_live += 1
                        
                    # 每50個顯示一次進度
                    if (i + 1) % 50 == 0:
                        progress_pct = ((i + 1) / len(chunks)) * 100
                        success_count = (i + 1) - error_count_live
                        print(f"[PROGRESS] {progress_pct:.1f}% ({i+1}/{len(chunks)}) "
                              f"成功:{success_count} 錯誤:{error_count_live}")
            
            elapsed = time.time() - start_time
            chunks_per_sec = len(chunks) / elapsed if elapsed > 0 else 0
            print(f"[PERF] 順序處理完成！耗時: {elapsed:.2f}s, 速度: {chunks_per_sec:.1f} chunks/s")
                
        else:
            # 高效並行處理 - 32 workers最佳化
            start_time = time.time()
            with ThreadPoolExecutor(max_workers=args.workers) as ex:
                futures = []
                for i, rec in enumerate(chunks):
                    futures.append(ex.submit(_one_job, i, rec, kw_lang, args.max_chars))
                
                results = []
                processed_count = 0
                error_count_live = 0
                
                if TQDM_AVAILABLE:
                    # 使用簡化的 tqdm 避免格式問題
                    print(f"[INFO] 開始並行處理 {len(chunks)} 個chunks (有進度條)...")
                    
                    with tqdm(total=len(futures), 
                             desc=f"關鍵字生成-{args.workers}w", 
                             unit="chunk") as pbar:
                        
                        for fut in as_completed(futures):
                            _, outrec = fut.result()
                            results.append(outrec)
                            processed_count += 1
                            
                            # 更新錯誤統計
                            if outrec.get("has_error", False):
                                error_count_live += 1
                            
                            # 每10個更新一次描述
                            if processed_count % 10 == 0:
                                success_count = processed_count - error_count_live
                                pbar.set_description(f"關鍵字生成-{args.workers}w [✓{success_count} ✗{error_count_live}]")
                            
                            pbar.update(1)
                else:
                    # 無進度條版本 - 提供清晰的文字進度
                    print(f"[INFO] 開始並行處理 {len(chunks)} 個chunks...")
                    last_update = 0
                    
                    for fut in as_completed(futures):
                        _, outrec = fut.result()
                        results.append(outrec)
                        processed_count += 1
                        
                        if outrec.get("has_error", False):
                            error_count_live += 1
                        
                        # 每處理完50個或每5秒顯示一次進度
                        current_time = time.time()
                        if processed_count % 50 == 0 or (current_time - last_update) > 5:
                            success_count = processed_count - error_count_live
                            progress_pct = (processed_count / len(chunks)) * 100
                            elapsed = current_time - start_time
                            rate = processed_count / elapsed if elapsed > 0 else 0
                            
                            print(f"[PROGRESS] {progress_pct:5.1f}% ({processed_count:3d}/{len(chunks)}) "
                                  f"[{rate:4.1f} chunk/s] 成功:{success_count:3d} 錯誤:{error_count_live:2d}")
                            last_update = current_time
                
                # 按chunk_id順序排序輸出
                results.sort(key=lambda x: x.get('chunk_id', 0))
                for record in results:
                    fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            
            elapsed = time.time() - start_time
            chunks_per_sec = len(chunks) / elapsed if elapsed > 0 else 0
            print(f"[PERF] 處理完成！耗時: {elapsed:.2f}s, 速度: {chunks_per_sec:.1f} chunks/s")
            print(f"[PERF] 平均每worker處理: {len(chunks)/args.workers:.1f} chunks")

    print(f"[OK] 已寫入 {len(chunks)} 條完整記錄到 {args.out}")
    
    # 顯示處理統計 - 包含文字內容統計
    content_types = {}
    error_count = 0
    keyword_quality_stats = {"good": 0, "fallback": 0, "error": 0}
    text_length_stats = []
    total_keywords = 0
    
    with open(args.out, "r", encoding="utf-8") as f:
        for line in f:
            try:
                record = json.loads(line)
                content_type = record.get("content_type", "unknown")
                content_types[content_type] = content_types.get(content_type, 0) + 1
                
                # 統計文字長度
                text_length = record.get("text_length", 0)
                if text_length > 0:
                    text_length_stats.append(text_length)
                
                # 統計關鍵字數量
                keywords_count = record.get("keywords_count", 0)
                total_keywords += keywords_count
                
                if record.get("has_error", False):
                    error_count += 1
                    keyword_quality_stats["error"] += 1
                else:
                    keywords = record.get("keywords", [])
                    # 檢查關鍵字品質
                    if any("fallback" in kw or "error" in kw or "supplementary" in kw for kw in keywords):
                        keyword_quality_stats["fallback"] += 1
                    else:
                        keyword_quality_stats["good"] += 1
            except:
                pass
    
    # 文字長度統計
    if text_length_stats:
        avg_length = sum(text_length_stats) / len(text_length_stats)
        min_length = min(text_length_stats)
        max_length = max(text_length_stats)
        print(f"[STATS] 文字長度: 平均={avg_length:.0f}, 範圍={min_length}-{max_length} 字元")
    
    print(f"[STATS] 內容類型分布: {content_types}")
    print(f"[STATS] 關鍵字品質: 優秀({keyword_quality_stats['good']}) | "
          f"後備({keyword_quality_stats['fallback']}) | 錯誤({keyword_quality_stats['error']})")
    print(f"[STATS] 總關鍵字數: {total_keywords} 個 (平均 {total_keywords/len(chunks):.1f} 個/chunk)")
    
    if error_count > 0:
        print(f"[WARN] 處理過程中有 {error_count} 個錯誤")
    
    # 成功率統計
    success_rate = (len(chunks) - error_count) / len(chunks) * 100 if len(chunks) > 0 else 0
    print(f"[SUMMARY] 成功處理率: {success_rate:.1f}% ({len(chunks)-error_count}/{len(chunks)})")
    
    # 輸出檔案格式說明
    print(f"\n📋 輸出檔案格式說明:")
    print(f"  ✅ 包含完整chunks文字內容 (text字段)")
    print(f"  ✅ 包含生成的關鍵字 (keywords字段)")  
    print(f"  ✅ 包含來源和頁面信息 (source, page字段)")
    print(f"  ✅ 包含內容統計信息 (text_length, keywords_count字段)")
    print(f"  ✅ 可直接用於後續問題生成流程")
    
    return success_rate > 90  # 返回是否成功


if __name__ == "__main__":
    main()