# -*- coding: utf-8 -*-
"""
語言感知 Keyword LLM runner - 基於現有架構的增強版
修正版本：遵循原有的 core.py, clients.py, prompts.py 三層架構

主要改進：
1. 集成語言檢測到原有 core.py 流程中
2. 根據chunk語言信息智能調整關鍵字生成策略
3. 保持與現有clients.py和prompts.py的兼容性
4. 增強統計和品質監控功能
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
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

# 使用現有的client模組
from .clients import generate_keywords, generate_keywords_batch


# ========== 語言檢測和策略選擇 ==========

def detect_chunk_language(text: str) -> Tuple[str, Dict[str, float]]:
    """
    檢測chunk的主要語言
    返回: (主要語言, 語言統計)
    """
    if not text.strip():
        return "unknown", {"chinese": 0, "english": 0, "other": 100}
    
    # 統計不同類型字符
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    total_meaningful = chinese_chars + english_chars
    
    if total_meaningful == 0:
        return "unknown", {"chinese": 0, "english": 0, "other": 100}
    
    chinese_ratio = chinese_chars / total_meaningful
    english_ratio = english_chars / total_meaningful
    
    stats = {
        "chinese": chinese_ratio * 100,
        "english": english_ratio * 100,
        "other": max(0, 100 - (chinese_ratio + english_ratio) * 100)
    }
    
    # 判定主要語言
    if chinese_ratio > 0.6:
        return "chinese", stats
    elif english_ratio > 0.6:
        return "english", stats
    elif chinese_ratio > 0.3 and english_ratio > 0.3:
        return "mixed", stats
    else:
        return "unknown", stats


def get_language_aware_params(chunk: Dict) -> Dict:
    """
    根據chunk語言信息獲取優化參數
    """
    # 如果chunk已經包含語言信息（來自語言感知分塊器），直接使用
    if "main_language" in chunk:
        main_lang = chunk["main_language"]
        lang_stats = chunk.get("language_stats", {})
    else:
        # 否則進行語言檢測
        main_lang, lang_stats = detect_chunk_language(chunk.get("text", ""))
    
    # 語言特定的關鍵字生成策略
    language_strategies = {
        "chinese": {
            "keyword_lang": "zh",
            "max_chars": 1000,      # 中文chunk較長，可發送更多內容
            "n_keywords": 4,        # 中文概念密度高，生成更多關鍵字
            "strategy": "chinese_focused"
        },
        "english": {
            "keyword_lang": "en", 
            "max_chars": 1400,      # 英文保持原有長度
            "n_keywords": 3,        # 英文標準數量
            "strategy": "english_focused"
        },
        "mixed": {
            "keyword_lang": "mixed",  # 使用混合語言策略
            "max_chars": 1200,       # 混合內容取中間值
            "n_keywords": 5,         # 混合內容生成更多以覆蓋雙語
            "strategy": "bilingual"
        },
        "unknown": {
            "keyword_lang": "auto",
            "max_chars": 1200,
            "n_keywords": 3,
            "strategy": "adaptive"
        }
    }
    
    # 如果是mixed或unknown，進一步分析
    if main_lang in ["mixed", "unknown"]:
        chinese_pct = lang_stats.get("chinese", 0)
        english_pct = lang_stats.get("english", 0)
        
        if chinese_pct > 50:
            strategy = language_strategies["chinese"].copy()
        elif english_pct > 50:
            strategy = language_strategies["english"].copy()
        else:
            strategy = language_strategies["mixed"].copy()
    else:
        strategy = language_strategies.get(main_lang, language_strategies["unknown"]).copy()
    
    # 根據chunk品質調整參數
    quality_score = chunk.get("quality_score", 0.5)
    if quality_score > 0.8:
        strategy["n_keywords"] += 1  # 高品質chunk生成更多關鍵字
    elif quality_score < 0.6:
        strategy["max_chars"] = int(strategy["max_chars"] * 0.8)  # 低品質chunk減少輸入
    
    # 添加語言信息到策略中
    strategy.update({
        "detected_language": main_lang,
        "language_stats": lang_stats,
        "quality_score": quality_score
    })
    
    return strategy


# ========== 改進版載入函數 ==========

def _load_language_aware_chunks(path: str) -> List[Dict]:
    """載入支援語言信息的chunks"""
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
                
            # 構建chunk數據，保留所有原有字段
            chunk_data = {
                "text": text,
                "source": obj.get("source", obj.get("file", "unknown")),
                "page": int(obj.get("page", 0) or 0),
            }
            
            # 保留語言感知分塊器的信息
            for key in ["quality_score", "length", "_quality", "main_language", 
                       "language_stats", "global_language", "language_params"]:
                if key in obj:
                    chunk_data[key] = obj[key]
                    
            items.append(chunk_data)
    
    return items


def _load_from_txt(path: str) -> List[Dict]:
    """保持原有的txt格式支援（向後兼容）"""
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
                except:
                    pass
            else:
                # plain text, assume unknown source
                if s:
                    tmp.append({"text": s, "source": "unknown", "page": 0})
    return tmp


def load_chunks(index_dir: str, input_file: str = None) -> List[Dict]:
    """
    改進版chunk載入 - 優先支援語言感知chunks
    """
    if input_file:
        # 如果指定了具體文件
        file_path = input_file if os.path.isabs(input_file) else os.path.join(index_dir, input_file)
        if os.path.exists(file_path):
            if file_path.endswith('.jsonl'):
                return _load_language_aware_chunks(file_path)
            else:
                return _load_from_txt(file_path)
    
    # 自動查找，優先使用語言感知版本
    language_aware_path = os.path.join(index_dir, "chunks_language_aware.jsonl")
    optimized_path = os.path.join(index_dir, "chunks_optimized.jsonl")
    txt_path = os.path.join(index_dir, "chunks.txt")
    
    # 按優先級嘗試
    for path_to_try, load_func in [
        (language_aware_path, _load_language_aware_chunks),
        (optimized_path, _load_language_aware_chunks),
        (txt_path, _load_from_txt)
    ]:
        if os.path.exists(path_to_try):
            print(f"[INFO] 使用 {path_to_try}")
            chunks = load_func(path_to_try)
            if chunks:
                return chunks
    
    return []


# ========== 改進版工作函數 ==========

def _trim(s: str, max_chars: int) -> str:
    """智能文本截取"""
    if max_chars <= 0 or len(s) <= max_chars:
        return s
    
    # 嘗試在句子邊界截取
    truncated = s[:max_chars]
    sentence_ends = ['。', '！', '？', '.', '!', '?']
    best_cut = max_chars
    
    for i in range(len(truncated) - 1, max(0, max_chars - 200), -1):
        if truncated[i] in sentence_ends:
            best_cut = i + 1
            break
    
    return s[:best_cut].strip()


def _detect_content_type(text: str) -> str:
    """
    自動檢測內容類型以改進關鍵字生成
    """
    text_lower = text.lower()
    
    # 技術文件指標
    tech_indicators = ["display", "led", "oled", "cpu", "gpu", "algorithm", "protocol", 
                      "specification", "patent", "manufacturing"]
    # 商業文件指標  
    business_indicators = ["market", "revenue", "business", "strategy", "competition", 
                          "growth", "investment", "company"]
    # 學術文件指標
    academic_indicators = ["research", "study", "analysis", "methodology", "experiment", 
                          "conclusion", "hypothesis", "theory"]
    
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


def _language_aware_job(idx: int, rec: Dict, base_kw_lang: str, max_chars: int,
                       retries: int = 2, backoff: float = 1.2) -> Tuple[int, Dict]:
    """
    語言感知的關鍵字生成任務
    """
    full_text = (rec.get("text") or "").strip()
    if not full_text:
        return idx, _make_error_record(idx, rec, "Empty text", base_kw_lang)
    
    # 獲取語言感知參數
    lang_params = get_language_aware_params(rec)
    
    # 使用語言特定的參數
    actual_kw_lang = lang_params["keyword_lang"]
    actual_max_chars = lang_params["max_chars"]
    actual_n_keywords = lang_params["n_keywords"]
    
    text_for_llm = _trim(full_text, actual_max_chars)
    content_type = _detect_content_type(full_text)
    
    source = rec.get("source", rec.get("file", "unknown"))
    try:
        page = int(rec.get("page", 0) or 0)
    except Exception:
        page = 0
    
    last_err = None
    for attempt in range(retries + 1):
        try:
            # 調用現有的generate_keywords函數，但傳入語言感知參數
            kws = generate_keywords(
                text_for_llm, 
                n=actual_n_keywords, 
                lang=actual_kw_lang, 
                content_type=content_type
            )
            
            # 驗證關鍵字
            kws = [k for k in kws if isinstance(k, str) and k.strip()]
            if not kws:
                kws = _generate_fallback_keywords(actual_kw_lang, 3)
            elif len(kws) < 3:
                kws.extend(_generate_fallback_keywords(actual_kw_lang, 3 - len(kws)))
            
            return idx, _make_success_record(idx, rec, kws, content_type, lang_params)
            
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep((attempt + 1) * backoff)
            else:
                fallback_kws = _generate_fallback_keywords(actual_kw_lang, 3)
                return idx, _make_error_record(idx, rec, str(last_err), actual_kw_lang, fallback_kws)

    return idx, _make_error_record(idx, rec, "unknown_error", base_kw_lang)


def _generate_fallback_keywords(lang: str, count: int = 3) -> List[str]:
    """生成語言特定的後備關鍵字"""
    if "zh" in lang.lower():
        return [f"中文關鍵字{i+1}" for i in range(count)]
    elif "en" in lang.lower():
        return [f"english_keyword_{i+1}" for i in range(count)]
    elif "mixed" in lang.lower():
        return [f"混合關鍵字{i+1}" if i % 2 == 0 else f"mixed_keyword_{i+1}" 
                for i in range(count)]
    else:
        return [f"fallback_kw_{i+1}" for i in range(count)]


def _make_success_record(idx: int, chunk: Dict, keywords: List[str], 
                        content_type: str, lang_params: Dict) -> Dict:
    """創建成功記錄，包含語言信息"""
    full_text = chunk.get("text", "")
    
    record = {
        "chunk_id": idx,
        "source": chunk.get("source", "unknown"),
        "page": chunk.get("page", 0),
        "text": full_text,
        "keywords": keywords,
        "preview": full_text[:150],
        "content_type": content_type,
        "text_length": len(full_text),
        "keywords_count": len(keywords),
        "has_error": False,
        
        # 語言感知信息
        "detected_language": lang_params["detected_language"],
        "language_stats": lang_params["language_stats"],
        "keyword_language": lang_params["keyword_lang"],
        "generation_strategy": lang_params["strategy"],
        "language_aware_processing": True
    }
    
    # 保留原有的品質和語言信息
    for key in ["quality_score", "_quality", "main_language", "global_language"]:
        if key in chunk:
            record[key] = chunk[key]
    
    return record


def _make_error_record(idx: int, chunk: Dict, error: str, 
                      kw_lang: str, fallback_kws: List[str] = None) -> Dict:
    """創建錯誤記錄"""
    if fallback_kws is None:
        fallback_kws = _generate_fallback_keywords(kw_lang, 3)
    
    lang_params = get_language_aware_params(chunk)
    record = _make_success_record(idx, chunk, fallback_kws, "unknown", lang_params)
    record.update({
        "has_error": True,
        "error": error,
        "generation_strategy": "fallback"
    })
    
    return record


# ========== 批量處理函數 ==========

def _batch_process_language_aware(chunks: List[Dict], kw_lang: str, max_chars: int) -> List[Dict]:
    """
    語言感知的批量處理
    """
    print(f"[INFO] 使用語言感知批量處理模式")
    
    # 準備數據並進行語言感知預處理
    processed_chunks = []
    language_distribution = {}
    
    if TQDM_AVAILABLE:
        chunk_iter = tqdm(enumerate(chunks), total=len(chunks), desc="語言分析", unit="chunk")
    else:
        chunk_iter = enumerate(chunks)
        print(f"[INFO] 分析 {len(chunks)} 個chunks的語言信息...")
    
    for i, chunk in chunk_iter:
        # 獲取語言感知參數
        lang_params = get_language_aware_params(chunk)
        
        # 統計語言分布
        detected_lang = lang_params["detected_language"]
        language_distribution[detected_lang] = language_distribution.get(detected_lang, 0) + 1
        
        # 準備處理數據
        chunk_copy = chunk.copy()
        chunk_copy["text"] = _trim(chunk["text"], lang_params["max_chars"])
        chunk_copy["_lang_params"] = lang_params  # 暫存語言參數
        processed_chunks.append(chunk_copy)
    
    print(f"[LANG] 語言分布統計: {language_distribution}")
    
    # 調用現有的批量生成函數
    print(f"[INFO] 開始批量關鍵字生成...")
    results = generate_keywords_batch(processed_chunks, n=3, lang=kw_lang)
    
    # 轉換為輸出格式，添加語言感知信息
    output_records = []
    
    if TQDM_AVAILABLE:
        result_iter = tqdm(enumerate(results), total=len(results), 
                          desc="處理結果", unit="chunk")
    else:
        result_iter = enumerate(results)
        print(f"[INFO] 處理 {len(results)} 個結果...")
        
    for i, result in result_iter:
        original_chunk = chunks[i]
        lang_params = processed_chunks[i]["_lang_params"]
        
        source = result.get("source", "unknown")
        try:
            page = int(result.get("page", 0) or 0)
        except Exception:
            page = 0
            
        full_text = original_chunk["text"]
        keywords = result.get("keywords", _generate_fallback_keywords(kw_lang, 3))
        
        out_record = {
            "chunk_id": i,
            "source": source,
            "page": page,
            "text": full_text,
            "keywords": keywords,
            "preview": full_text[:150],
            "content_type": _detect_content_type(full_text),
            "text_length": len(full_text),
            "keywords_count": len(keywords),
            "has_error": False,
            
            # 語言感知信息
            "detected_language": lang_params["detected_language"],
            "language_stats": lang_params["language_stats"],
            "keyword_language": lang_params["keyword_lang"],
            "generation_strategy": lang_params["strategy"],
            "language_aware_processing": True
        }
        
        # 保留原有信息
        for key in ["quality_score", "_quality", "main_language"]:
            if key in original_chunk:
                out_record[key] = original_chunk[key]
                
        output_records.append(out_record)
    
    print(f"[INFO] 語言感知批量處理完成，生成 {len(output_records)} 條記錄")
    return output_records


# ========== 主處理函數 ==========

def main():
    parser = argparse.ArgumentParser(description="語言感知關鍵字生成工具 (core.py)")
    parser.add_argument("--index", default="indices", help="索引目錄")
    parser.add_argument("--input-file", help="指定特定的chunks文件 (可選)")
    parser.add_argument("--out", default="outputs/data/keywords_language_aware.jsonl", help="輸出文件")
    parser.add_argument("--langs", default="auto", help="基礎語言提示 (auto=自動檢測)")
    parser.add_argument("--max-chunks", type=int, default=0, help="限制處理chunks數量 (0=全部)")
    parser.add_argument("--workers", type=int, default=32, help="並行worker數量 (預設32，最佳效能)")
    parser.add_argument("--max-chars", type=int, default=1400, help="基礎文本截斷長度")
    parser.add_argument("--batch-mode", action="store_true", help="使用批量處理模式")
    parser.add_argument("--fast", action="store_true", help="快速模式：32 workers + 最佳化設定")
    parser.add_argument("--language-aware", action="store_true", default=True, help="啟用語言感知處理 (預設)")
    
    args = parser.parse_args()

    # 快速模式設定
    if args.fast:
        args.workers = 32
        args.batch_mode = False
        print(f"[FAST] 啟用快速模式：32 workers，最佳化語言感知處理")

    # 語言設定
    kw_lang = args.langs if args.langs != "auto" else "auto"

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    # 載入chunks
    chunks = load_chunks(args.index, args.input_file)
    if args.max_chunks and args.max_chunks > 0:
        chunks = chunks[:args.max_chunks]
    
    print(f"[INFO] 從 '{args.index}' 載入了 {len(chunks)} 個chunks")
    if args.input_file:
        print(f"[INFO] 使用指定文件: {args.input_file}")
    
    # 顯示chunks統計
    language_aware_count = len([c for c in chunks if "main_language" in c])
    if language_aware_count > 0:
        print(f"[INFO] 包含語言信息的chunks: {language_aware_count}/{len(chunks)}")
        
        # 統計語言分布
        lang_dist = {}
        for c in chunks:
            if "main_language" in c:
                lang = c["main_language"]
                lang_dist[lang] = lang_dist.get(lang, 0) + 1
        print(f"[LANG] 預存語言分布: {lang_dist}")
    
    if not chunks:
        print("[ERROR] 沒有找到有效的chunks")
        return

    # 處理chunks
    start_time = time.time()
    
    if args.batch_mode:
        # 批量處理模式
        processed_records = _batch_process_language_aware(chunks, kw_lang, args.max_chars)
        
        # 直接寫入文件
        with open(args.out, "w", encoding="utf-8") as fout:
            for record in processed_records:
                fout.write(json.dumps(record, ensure_ascii=False) + "\n")
    else:
        # 並行處理模式
        results = []
        
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [
                executor.submit(_language_aware_job, i, chunk, kw_lang, args.max_chars)
                for i, chunk in enumerate(chunks)
            ]
            
            with open(args.out, "w", encoding="utf-8") as fout:
                processed_count = 0
                error_count = 0
                
                if TQDM_AVAILABLE:
                    pbar = tqdm(total=len(chunks), desc="生成關鍵字", unit="chunk")
                
                for fut in as_completed(futures):
                    try:
                        _, outrec = fut.result()
                        results.append(outrec)
                        
                        if outrec.get("has_error", False):
                            error_count += 1
                        
                        processed_count += 1
                        
                        if TQDM_AVAILABLE:
                            pbar.set_postfix({
                                "errors": error_count,
                                "success": f"{((processed_count-error_count)/processed_count*100):.1f}%"
                            })
                            pbar.update(1)
                        else:
                            if processed_count % 50 == 0:
                                success_rate = (processed_count - error_count) / processed_count * 100
                                print(f"[PROGRESS] {processed_count}/{len(chunks)} ({success_rate:.1f}% 成功)")
                    
                    except Exception as e:
                        error_count += 1
                        print(f"[ERROR] 處理失敗: {e}")
                
                if TQDM_AVAILABLE:
                    pbar.close()
                
                # 按chunk_id順序排序並寫入
                results.sort(key=lambda x: x.get('chunk_id', 0))
                for record in results:
                    fout.write(json.dumps(record, ensure_ascii=False) + "\n")

    elapsed = time.time() - start_time
    chunks_per_sec = len(chunks) / elapsed if elapsed > 0 else 0
    print(f"[PERF] 處理完成：耗時: {elapsed:.2f}s, 速度: {chunks_per_sec:.1f} chunks/s")

    print(f"[OK] 已寫入 {len(chunks)} 條完整記錄到 {args.out}")
    
    # 生成統計報告
    _generate_language_aware_statistics(args.out)


def _generate_language_aware_statistics(output_file: str):
    """生成語言感知統計報告"""
    stats = {
        "total_chunks": 0,
        "language_distribution": {},
        "keyword_language_distribution": {},
        "generation_strategy_distribution": {},
        "quality_distribution": {"high": 0, "medium": 0, "low": 0},
        "content_type_distribution": {},
        "error_stats": {"total_errors": 0, "error_rate": 0},
        "keyword_stats": {"total_keywords": 0, "avg_keywords_per_chunk": 0},
        "language_aware_stats": {
            "chunks_with_language_info": 0,
            "avg_chinese_ratio": 0,
            "avg_english_ratio": 0
        }
    }
    
    total_chinese_ratio = 0
    total_english_ratio = 0
    language_info_count = 0
    total_keywords = 0
    
    try:
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                    stats["total_chunks"] += 1
                    
                    # 語言分布
                    detected_lang = record.get("detected_language", "unknown")
                    stats["language_distribution"][detected_lang] = \
                        stats["language_distribution"].get(detected_lang, 0) + 1
                    
                    # 關鍵字語言分布
                    kw_lang = record.get("keyword_language", "unknown")
                    stats["keyword_language_distribution"][kw_lang] = \
                        stats["keyword_language_distribution"].get(kw_lang, 0) + 1
                    
                    # 生成策略分布
                    strategy = record.get("generation_strategy", "unknown")
                    stats["generation_strategy_distribution"][strategy] = \
                        stats["generation_strategy_distribution"].get(strategy, 0) + 1
                    
                    # 品質分布
                    quality = record.get("_quality", "unknown")
                    if quality in stats["quality_distribution"]:
                        stats["quality_distribution"][quality] += 1
                    
                    # 內容類型分布
                    content_type = record.get("content_type", "unknown")
                    stats["content_type_distribution"][content_type] = \
                        stats["content_type_distribution"].get(content_type, 0) + 1
                    
                    # 錯誤統計
                    if record.get("has_error", False):
                        stats["error_stats"]["total_errors"] += 1
                    
                    # 關鍵字統計
                    kw_count = record.get("keywords_count", 0)
                    total_keywords += kw_count
                    
                    # 語言感知統計
                    if record.get("language_aware_processing", False):
                        language_info_count += 1
                        lang_stats = record.get("language_stats", {})
                        total_chinese_ratio += lang_stats.get("chinese", 0)
                        total_english_ratio += lang_stats.get("english", 0)
                
                except json.JSONDecodeError:
                    continue
        
        # 計算平均值和比率
        if stats["total_chunks"] > 0:
            stats["error_stats"]["error_rate"] = \
                stats["error_stats"]["total_errors"] / stats["total_chunks"] * 100
            stats["keyword_stats"]["total_keywords"] = total_keywords
            stats["keyword_stats"]["avg_keywords_per_chunk"] = \
                total_keywords / stats["total_chunks"]
            
            stats["language_aware_stats"]["chunks_with_language_info"] = language_info_count
            if language_info_count > 0:
                stats["language_aware_stats"]["avg_chinese_ratio"] = \
                    total_chinese_ratio / language_info_count
                stats["language_aware_stats"]["avg_english_ratio"] = \
                    total_english_ratio / language_info_count
        
        # 保存統計報告
        stats_file = output_file.replace('.jsonl', '_language_aware_stats.json')
        with open(stats_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        # 打印關鍵統計
        print(f"\n📊 語言感知關鍵字生成統計:")
        print(f"   處理chunks: {stats['total_chunks']} 個")
        print(f"   成功率: {100 - stats['error_stats']['error_rate']:.1f}%")
        print(f"   平均每chunk關鍵字: {stats['keyword_stats']['avg_keywords_per_chunk']:.1f} 個")
        
        print(f"   語言檢測分布:")
        for lang, count in stats["language_distribution"].items():
            if count > 0:
                pct = count / stats["total_chunks"] * 100
                print(f"     {lang}: {count} ({pct:.1f}%)")
        
        print(f"   關鍵字語言分布:")
        for lang, count in stats["keyword_language_distribution"].items():
            if count > 0:
                pct = count / stats["total_chunks"] * 100
                print(f"     {lang}: {count} ({pct:.1f}%)")
        
        print(f"   生成策略分布:")
        for strategy, count in stats["generation_strategy_distribution"].items():
            if count > 0:
                pct = count / stats["total_chunks"] * 100
                print(f"     {strategy}: {count} ({pct:.1f}%)")
        
        if language_info_count > 0:
            avg_zh = stats["language_aware_stats"]["avg_chinese_ratio"]
            avg_en = stats["language_aware_stats"]["avg_english_ratio"]
            print(f"   平均語言比例: 中文 {avg_zh:.1f}%, 英文 {avg_en:.1f}%")
        
        print(f"   統計報告已保存: {stats_file}")
    
    except Exception as e:
        print(f"[WARN] 統計報告生成失敗: {e}")


if __name__ == "__main__":
    main()