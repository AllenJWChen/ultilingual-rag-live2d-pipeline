#修復版 core.py - 適配 1_Keyword_llm 路徑
#主要修復：
#1. 簡化進度條
#2. 修復統計邏輯
#3. 適配路徑結構


import os
import json
import re
import time
import argparse
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm.auto import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# 修復 import 路徑
try:
    from .clients import generate_keywords, generate_keywords_batch, _is_valid_keywords
except ImportError:
    try:
        from clients import generate_keywords, generate_keywords_batch, _is_valid_keywords
    except ImportError:
        print("ERROR: 無法導入 clients 模組")
        exit(1)


def detect_chunk_language(text: str) -> Tuple[str, Dict[str, float]]:
    """檢測chunk的主要語言 - 支援中英日三語"""
    if not text.strip():
        return "unknown", {"chinese": 0, "english": 0, "japanese": 0, "other": 100}
    
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text))
    total_meaningful = chinese_chars + english_chars + japanese_chars
    
    if total_meaningful == 0:
        return "unknown", {"chinese": 0, "english": 0, "japanese": 0, "other": 100}
    
    chinese_ratio = chinese_chars / total_meaningful
    english_ratio = english_chars / total_meaningful
    japanese_ratio = japanese_chars / total_meaningful
    
    stats = {
        "chinese": chinese_ratio * 100,
        "english": english_ratio * 100,
        "japanese": japanese_ratio * 100,
        "other": max(0, 100 - (chinese_ratio + english_ratio + japanese_ratio) * 100)
    }
    
    if japanese_ratio > 0.3:
        return "japanese", stats
    elif chinese_ratio > 0.6:
        return "chinese", stats
    elif english_ratio > 0.6:
        return "english", stats
    elif chinese_ratio > 0.3 and english_ratio > 0.3:
        return "mixed", stats
    else:
        return "unknown", stats


def load_chunks(index_dir: str, input_file: str = None) -> List[Dict]:
    """載入chunks"""
    if input_file:
        file_path = input_file if os.path.isabs(input_file) else os.path.join(index_dir, input_file)
        if os.path.exists(file_path):
            return _load_jsonl(file_path)
    
    # 自動查找
    for filename in ["chunks_language_aware.jsonl", "chunks_optimized.jsonl", "chunks.txt"]:
        path = os.path.join(index_dir, filename)
        if os.path.exists(path):
            print(f"使用 {path}")
            return _load_jsonl(path)
    
    return []


def _load_jsonl(path: str) -> List[Dict]:
    """載入JSONL格式文件"""
    items = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line_no, line in enumerate(f, 1):
            s = line.strip()
            if not s:
                continue
            try:
                obj = json.loads(s)
                text = (obj.get("text") or "").strip()
                if text:
                    chunk_data = {
                        "text": text,
                        "source": obj.get("source", "unknown"),
                        "page": int(obj.get("page", 0) or 0),
                    }
                    # 保留額外信息
                    for key in ["quality_score", "main_language", "language_stats"]:
                        if key in obj:
                            chunk_data[key] = obj[key]
                    items.append(chunk_data)
            except Exception as e:
                if line_no <= 10:  # 只顯示前10個錯誤
                    print(f"[WARN] Line {line_no}: {e}")
    return items


def _language_aware_job(idx: int, rec: Dict, base_kw_lang: str, max_chars: int) -> Tuple[int, Dict]:
    """語言感知關鍵字生成任務"""
    full_text = (rec.get("text") or "").strip()
    if not full_text:
        return idx, _make_error_record(idx, rec, "Empty text")
    
    # 文本截斷
    text_for_llm = full_text[:max_chars] if len(full_text) > max_chars else full_text
    
    # 語言檢測
    detected_lang, lang_stats = detect_chunk_language(full_text)
    lang_mapping = {"chinese": "zh", "english": "en", "japanese": "ja", "mixed": "mixed"}
    actual_lang = lang_mapping.get(detected_lang, base_kw_lang)
    
    try:
        # 生成關鍵字
        keywords = generate_keywords(text_for_llm, n=3, lang=actual_lang)
        
        # 檢查有效性
        is_valid = _is_valid_keywords(keywords, actual_lang)
        
        return idx, _make_success_record(idx, rec, keywords, detected_lang, lang_stats, is_valid)
        
    except Exception as e:
        return idx, _make_error_record(idx, rec, str(e))


def _make_success_record(idx: int, chunk: Dict, keywords: List[str], 
                        detected_lang: str, lang_stats: Dict, is_valid: bool) -> Dict:
    """創建成功記錄"""
    full_text = chunk.get("text", "")
    
    record = {
        "chunk_id": idx,
        "source": chunk.get("source", "unknown"),
        "page": chunk.get("page", 0),
        "text": full_text,
        "keywords": keywords,
        "preview": full_text[:150],
        "text_length": len(full_text),
        "keywords_count": len(keywords),
        "has_error": not is_valid,
        "keywords_valid": is_valid,
        "detected_language": detected_lang,
        "language_stats": lang_stats,
        "language_aware_processing": True
    }
    
    # 保留原有信息
    for key in ["quality_score", "_quality", "main_language"]:
        if key in chunk:
            record[key] = chunk[key]
    
    return record


def _make_error_record(idx: int, chunk: Dict, error: str) -> Dict:
    """創建錯誤記錄"""
    full_text = chunk.get("text", "")
    
    return {
        "chunk_id": idx,
        "source": chunk.get("source", "unknown"),
        "page": chunk.get("page", 0),
        "text": full_text,
        "keywords": ["error_keyword_1", "error_keyword_2", "error_keyword_3"],
        "preview": full_text[:150],
        "text_length": len(full_text),
        "keywords_count": 3,
        "has_error": True,
        "keywords_valid": False,
        "error": error,
        "detected_language": "unknown",
        "language_stats": {},
        "language_aware_processing": True
    }


def main():
    parser = argparse.ArgumentParser(description="語言感知關鍵字生成工具")
    parser.add_argument("--index", default="indices", help="索引目錄")
    parser.add_argument("--input-file", help="指定chunks文件")
    parser.add_argument("--out", default="outputs/data/keywords_fixed.jsonl", help="輸出文件")
    parser.add_argument("--langs", default="auto", help="語言設定")
    parser.add_argument("--max-chunks", type=int, default=0, help="限制chunks數量")
    parser.add_argument("--workers", type=int, default=16, help="並行數量")
    parser.add_argument("--max-chars", type=int, default=1400, help="文本長度限制")
    parser.add_argument("--quiet", action="store_true", help="安靜模式")
    
    args = parser.parse_args()
    
    # 創建輸出目錄
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    
    # 載入chunks
    chunks = load_chunks(args.index, args.input_file)
    if args.max_chunks > 0:
        chunks = chunks[:args.max_chunks]
    
    if not args.quiet:
        print(f"載入 {len(chunks)} 個chunks")
    
    if not chunks:
        print("沒有找到chunks")
        return
    
    # 處理chunks
    start_time = time.time()
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(_language_aware_job, i, chunk, args.langs, args.max_chars)
            for i, chunk in enumerate(chunks)
        ]
        
        results = []
        processed_count = 0
        error_count = 0
        invalid_count = 0
        
        # 簡化進度顯示
        if TQDM_AVAILABLE and not args.quiet:
            # 極簡進度條
            pbar = tqdm(total=len(chunks), desc="處理中", 
                       bar_format='{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt}')
        else:
            pbar = None
        
        with open(args.out, "w", encoding="utf-8") as fout:
            for fut in as_completed(futures):
                try:
                    _, record = fut.result()
                    results.append(record)
                    
                    # 統計
                    if record.get("has_error", False):
                        error_count += 1
                    if not record.get("keywords_valid", True):
                        invalid_count += 1
                    
                    processed_count += 1
                    
                    if pbar:
                        pbar.update(1)
                    elif not args.quiet and processed_count % 50 == 0:
                        valid_count = processed_count - error_count - invalid_count
                        print(f"進度: {processed_count}/{len(chunks)} (有效: {valid_count})")
                
                except Exception as e:
                    error_count += 1
                    if not args.quiet:
                        print(f"處理錯誤: {e}")
            
            if pbar:
                pbar.close()
            
            # 排序並寫入
            results.sort(key=lambda x: x.get('chunk_id', 0))
            for record in results:
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    # 最終統計
    elapsed = time.time() - start_time
    valid_count = len(chunks) - error_count - invalid_count
    
    print(f"\n處理完成:")
    print(f"  總chunks: {len(chunks)}")
    print(f"  有效關鍵字: {valid_count} ({valid_count/len(chunks)*100:.1f}%)")
    print(f"  無效關鍵字: {invalid_count} ({invalid_count/len(chunks)*100:.1f}%)")
    print(f"  處理錯誤: {error_count} ({error_count/len(chunks)*100:.1f}%)")
    print(f"  處理時間: {elapsed:.2f}s ({len(chunks)/elapsed:.1f} chunks/s)")
    print(f"  輸出文件: {args.out}")


if __name__ == "__main__":
    main()