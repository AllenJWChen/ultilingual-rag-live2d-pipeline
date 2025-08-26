# -*- coding: utf-8 -*-
"""
語言感知關鍵字客戶端模組 (clients.py)
基於原有 clients.py 架構，增加語言感知功能

主要功能：
1. 與語言感知的 prompts.py 集成
2. 支援根據語言和內容類型選擇不同的生成策略
3. 保持與現有 core.py 的兼容性
4. 增強錯誤處理和重試機制
"""

import json
import re
import time
import requests
from typing import List, Dict, Optional, Union
from .prompts import (
    build_keywords_prompt,
    build_adaptive_keywords_prompt,
    build_contextual_keywords_prompt,
    build_quality_enhanced_keywords_prompt,
    build_domain_specific_keywords_prompt,
    build_fallback_keywords_prompt
)


# ========== 語言感知配置 ==========

LANGUAGE_AWARE_CONFIG = {
    "chinese": {
        "model_preference": "chinese_optimized",
        "temperature": 0.3,
        "max_tokens": 200,
        "timeout": 30,
        "retry_count": 3
    },
    "english": {
        "model_preference": "english_optimized", 
        "temperature": 0.2,
        "max_tokens": 150,
        "timeout": 25,
        "retry_count": 3
    },
    "mixed": {
        "model_preference": "multilingual",
        "temperature": 0.25,
        "max_tokens": 250,
        "timeout": 35,
        "retry_count": 3
    },
    "auto": {
        "model_preference": "general",
        "temperature": 0.3,
        "max_tokens": 200,
        "timeout": 30,
        "retry_count": 3
    }
}


# ========== 核心生成函數 ==========

def generate_keywords(text: str, n: int = 3, lang: str = "en", 
                     content_type: Optional[str] = None,
                     quality_score: Optional[float] = None,
                     domain: Optional[str] = None,
                     context_keywords: Optional[List[str]] = None) -> List[str]:
    """
    語言感知的關鍵字生成函數
    
    Args:
        text: 輸入文本
        n: 關鍵字數量
        lang: 語言 ("zh", "en", "mixed", "auto")
        content_type: 內容類型 ("technical", "business", "academic", etc.)
        quality_score: 文本品質分數 (0-1)
        domain: 專業領域 ("medical", "legal", "technology", etc.)
        context_keywords: 上下文關鍵字（來自相鄰chunks）
    """
    
    if not text or not text.strip():
        return _generate_fallback_keywords(lang, n)
    
    # 選擇最適合的提示詞生成策略
    prompt = _select_optimal_prompt(
        text=text,
        n=n,
        lang=lang,
        content_type=content_type,
        quality_score=quality_score,
        domain=domain,
        context_keywords=context_keywords
    )
    
    # 獲取語言特定的配置
    config = LANGUAGE_AWARE_CONFIG.get(lang, LANGUAGE_AWARE_CONFIG["auto"])
    
    # 執行LLM調用
    try:
        keywords = _call_llm_with_retry(
            prompt=prompt,
            config=config,
            expected_count=n
        )
        
        # 後處理和驗證
        keywords = _postprocess_keywords(keywords, lang, n)
        
        return keywords
        
    except Exception as e:
        print(f"[ERROR] 關鍵字生成失敗: {e}")
        return _generate_fallback_keywords(lang, n, str(e))


def generate_keywords_batch(chunks: List[Dict], n: int = 3, lang: str = "en") -> List[Dict]:
    """
    語言感知的批量關鍵字生成
    
    Args:
        chunks: chunk字典列表，每個包含 'text' 字段
        n: 每個chunk的關鍵字數量
        lang: 基礎語言設定
    """
    
    if not chunks:
        return []
    
    print(f"[BATCH] 開始批量處理 {len(chunks)} 個chunks")
    
    # 分析chunks的語言分布
    language_analysis = _analyze_chunks_languages(chunks)
    print(f"[BATCH] 語言分布: {language_analysis}")
    
    results = []
    
    for i, chunk in enumerate(chunks):
        try:
            # 為每個chunk獲取語言感知參數
            chunk_lang = _detect_chunk_language_preference(chunk, lang)
            chunk_content_type = chunk.get("content_type", "auto")
            chunk_quality = chunk.get("quality_score", 0.5)
            
            # 生成關鍵字
            keywords = generate_keywords(
                text=chunk.get("text", ""),
                n=n,
                lang=chunk_lang,
                content_type=chunk_content_type,
                quality_score=chunk_quality
            )
            
            # 構建結果記錄
            result = {
                "chunk_id": i,
                "source": chunk.get("source", "unknown"),
                "page": chunk.get("page", 0),
                "keywords": keywords,
                "detected_language": chunk_lang,
                "processing_success": True
            }
            
            results.append(result)
            
        except Exception as e:
            print(f"[BATCH ERROR] Chunk {i} 處理失敗: {e}")
            
            # 創建錯誤記錄
            error_result = {
                "chunk_id": i,
                "source": chunk.get("source", "unknown"),
                "page": chunk.get("page", 0),
                "keywords": _generate_fallback_keywords(lang, n, str(e)),
                "detected_language": lang,
                "processing_success": False,
                "error": str(e)
            }
            
            results.append(error_result)
    
    success_count = sum(1 for r in results if r.get("processing_success", False))
    print(f"[BATCH] 完成: {success_count}/{len(results)} 成功")
    
    return results


# ========== 輔助函數 ==========

def _select_optimal_prompt(text: str, n: int, lang: str, 
                          content_type: Optional[str] = None,
                          quality_score: Optional[float] = None,
                          domain: Optional[str] = None,
                          context_keywords: Optional[List[str]] = None) -> str:
    """
    根據參數選擇最優的提示詞生成策略
    """
    
    # 優先級：領域特定 > 上下文感知 > 品質增強 > 內容類型自適應 > 基礎
    
    if domain and domain != "general":
        return build_domain_specific_keywords_prompt(text, domain, n, lang)
    
    if context_keywords:
        return build_contextual_keywords_prompt(text, context_keywords, n, lang)
    
    if quality_score is not None:
        return build_quality_enhanced_keywords_prompt(text, quality_score, n, lang)
    
    if content_type and content_type != "auto":
        return build_adaptive_keywords_prompt(text, content_type, n, lang)
    
    # 默認使用基礎語言感知提示詞
    return build_keywords_prompt(text, n, lang)


def _detect_chunk_language_preference(chunk: Dict, default_lang: str) -> str:
    """
    檢測chunk的語言偏好
    """
    # 如果chunk包含語言信息（來自語言感知分塊器），優先使用
    if "main_language" in chunk:
        main_lang = chunk["main_language"]
        lang_mapping = {
            "chinese": "zh",
            "english": "en", 
            "mixed": "mixed",
            "unknown": "auto"
        }
        return lang_mapping.get(main_lang, default_lang)
    
    # 如果有keyword_language信息，直接使用
    if "keyword_language" in chunk:
        return chunk["keyword_language"]
    
    # 如果有language_stats，根據比例決定
    if "language_stats" in chunk:
        stats = chunk["language_stats"]
        chinese_pct = stats.get("chinese", 0)
        english_pct = stats.get("english", 0)
        
        if chinese_pct > 60:
            return "zh"
        elif english_pct > 60:
            return "en"
        elif chinese_pct > 30 and english_pct > 30:
            return "mixed"
    
    # 簡單文本分析
    text = chunk.get("text", "")
    if text:
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        total_chars = chinese_chars + english_chars
        
        if total_chars > 0:
            chinese_ratio = chinese_chars / total_chars
            if chinese_ratio > 0.6:
                return "zh"
            elif chinese_ratio < 0.4:
                return "en"
            else:
                return "mixed"
    
    return default_lang


def _analyze_chunks_languages(chunks: List[Dict]) -> Dict[str, int]:
    """
    分析chunks的語言分布
    """
    language_dist = {}
    
    for chunk in chunks:
        lang = _detect_chunk_language_preference(chunk, "unknown")
        language_dist[lang] = language_dist.get(lang, 0) + 1
    
    return language_dist


def _call_llm_with_retry(prompt: str, config: Dict, expected_count: int) -> List[str]:
    """
    帶重試機制的LLM調用
    
    注意：這裡需要根據你實際使用的LLM服務調整
    """
    
    max_retries = config.get("retry_count", 3)
    timeout = config.get("timeout", 30)
    
    for attempt in range(max_retries):
        try:
            # 這裡需要根據你實際的LLM服務進行調整
            # 例如：如果使用 Ollama
            response = _call_ollama_api(prompt, config, timeout)
            
            # 或者如果使用 OpenAI
            # response = _call_openai_api(prompt, config, timeout)
            
            # 或者如果使用其他服務
            # response = _call_custom_llm_api(prompt, config, timeout)
            
            return response
            
        except Exception as e:
            print(f"[LLM] 嘗試 {attempt + 1}/{max_retries} 失敗: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指數退避
            else:
                raise e


def _call_ollama_api(prompt: str, config: Dict, timeout: int) -> List[str]:
    """
    修復版 Ollama API 調用
    解決 "Extra data: line 2 column 1" 錯誤
    """
    try:
        # Ollama API 配置
        url = "http://localhost:11434/api/generate"
        
        payload = {
            "model": "llama3.1:latest",  # 確保模型名稱正確
            "prompt": prompt,
            "stream": False,             # 🔑 關鍵修復：關閉流式輸出
            "options": {
                "temperature": config.get("temperature", 0.3),
                "num_predict": 200,      # 限制輸出長度
                "stop": ["\n\n"]         # 停止標記
            }
        }
        
        headers = {
            "Content-Type": "application/json"
        }
        
        # 發送請求
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            try:
                # 解析 JSON 響應
                result = response.json()
                text_response = result.get("response", "").strip()
                
                print(f"[DEBUG] LLM原始響應: {text_response[:100]}...")  # 調試信息
                
                # 🔧 強化的關鍵字解析
                keywords = _parse_llm_response(text_response)
                
                if keywords and len(keywords) >= 1:
                    return keywords
                else:
                    print("[FALLBACK] 解析失敗，使用後備關鍵字")
                    return ["fallback_keyword_1", "fallback_keyword_2", "fallback_keyword_3"]
                    
            except json.JSONDecodeError as e:
                print(f"[ERROR] JSON解析失敗: {e}")
                print(f"[ERROR] 原始響應內容: {response.text}")
                # 嘗試從原始文本中提取
                return _emergency_keyword_extract(response.text)
        else:
            print(f"[ERROR] HTTP錯誤: {response.status_code}")
            raise Exception(f"API調用失敗: {response.status_code}")
            
    except requests.RequestException as e:
        print(f"[ERROR] 請求失敗: {e}")
        raise Exception(f"網絡請求失敗: {e}")


def _parse_llm_response(text_response: str) -> List[str]:
    """
    解析 LLM 響應，提取關鍵字
    處理各種可能的響應格式
    """
    if not text_response:
        return []
    
    # 方法1: 尋找 JSON 數組
    import re
    json_pattern = r'\[(.*?)\]'
    json_matches = re.findall(json_pattern, text_response, re.DOTALL)
    
    for json_str in json_matches:
        try:
            # 重構 JSON 字符串
            json_array = f'[{json_str}]'
            keywords = json.loads(json_array)
            
            if isinstance(keywords, list):
                valid_keywords = []
                for kw in keywords:
                    if isinstance(kw, str) and kw.strip():
                        valid_keywords.append(kw.strip().strip('"\''))
                
                if valid_keywords:
                    print(f"[SUCCESS] JSON解析成功: {valid_keywords}")
                    return valid_keywords[:5]  # 最多返回5個
                    
        except json.JSONDecodeError:
            continue
    
    # 方法2: 尋找引號包圍的詞
    quoted_pattern = r'"([^"]+)"'
    quoted_words = re.findall(quoted_pattern, text_response)
    
    if quoted_words:
        clean_words = [w.strip() for w in quoted_words if w.strip() and len(w.strip()) > 1]
        if clean_words:
            print(f"[SUCCESS] 引號解析成功: {clean_words}")
            return clean_words[:5]
    
    # 方法3: 按行分割並清理
    lines = text_response.split('\n')
    potential_keywords = []
    
    for line in lines:
        line = line.strip()
        if line and not line.startswith('[') and not line.startswith('{'):
            # 移除數字、標點等
            cleaned = re.sub(r'^\d+[.)]\s*', '', line)  # 移除編號
            cleaned = cleaned.strip('.,;:"\'')
            
            if cleaned and 1 < len(cleaned) < 30:
                potential_keywords.append(cleaned)
    
    if potential_keywords:
        print(f"[SUCCESS] 行分割解析成功: {potential_keywords}")
        return potential_keywords[:5]
    
    print("[FAILED] 所有解析方法都失敗了")
    return []


def _emergency_keyword_extract(raw_response: str) -> List[str]:
    """
    應急關鍵字提取 - 當所有解析都失敗時的最後手段
    """
    print("[EMERGENCY] 使用應急關鍵字提取")
    
    # 嘗試找到任何看起來像關鍵字的內容
    import re
    
    # 提取所有可能的詞彙
    words = re.findall(r'[a-zA-Z\u4e00-\u9fff]{2,}', raw_response)
    
    # 過濾常見詞和太短的詞
    stopwords = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'had', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'man', 'new', 'now', 'old', 'see', 'two', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use'}
    
    filtered_words = [w for w in words if w.lower() not in stopwords and len(w) > 2]
    
    if filtered_words:
        return filtered_words[:3]
    else:
        return ["emergency_kw1", "emergency_kw2", "emergency_kw3"]


# 🧪 測試函數 - 用來驗證修復是否生效
def test_ollama_fix():
    """
    測試修復後的 Ollama 調用
    """
    print("🧪 測試 Ollama 修復...")
    
    test_prompt = '''請為以下內容提取3個關鍵字，輸出JSON格式：["關鍵字1", "關鍵字2", "關鍵字3"]

內容：台積電是全球最大的半導體代工廠。

關鍵字：'''
    
    config = {"temperature": 0.3}
    
    try:
        result = _call_ollama_api(test_prompt, config, 30)
        print(f"✅ 測試成功！結果: {result}")
        return True
    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        return False


# 使用方法：
if __name__ == "__main__":
    test_ollama_fix()


def _call_openai_api(prompt: str, config: Dict, timeout: int) -> List[str]:
    """
    調用 OpenAI API（示例實現）
    需要安裝: pip install openai
    """
    try:
        import openai
        
        # 設置 OpenAI API key（需要從環境變量或配置中獲取）
        openai.api_key = os.getenv("OPENAI_API_KEY")
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # 或其他模型
            messages=[{"role": "user", "content": prompt}],
            temperature=config.get("temperature", 0.3),
            max_tokens=config.get("max_tokens", 200),
            timeout=timeout
        )
        
        text_response = response.choices[0].message.content.strip()
        
        # 解析響應
        try:
            keywords = json.loads(text_response)
            if isinstance(keywords, list):
                return [str(kw).strip() for kw in keywords if kw]
        except json.JSONDecodeError:
            return _parse_non_json_response(text_response)
            
    except Exception as e:
        raise Exception(f"OpenAI API調用失敗: {e}")


def _parse_non_json_response(text: str) -> List[str]:
    """
    解析非JSON格式的響應
    """
    # 嘗試各種格式的解析
    keywords = []
    
    # 方法1: 查找引號包圍的詞
    quoted_words = re.findall(r'"([^"]*)"', text)
    if quoted_words:
        keywords.extend(quoted_words)
    
    # 方法2: 查找列表格式
    list_items = re.findall(r'[-*•]\s*(.+)', text)
    if list_items:
        keywords.extend([item.strip().strip('"\'') for item in list_items])
    
    # 方法3: 按逗號分割
    if not keywords:
        comma_separated = [item.strip().strip('"\'') for item in text.split(',')]
        keywords.extend(comma_separated)
    
    # 清理和過濾
    cleaned_keywords = []
    for kw in keywords:
        kw = kw.strip()
        if kw and len(kw) > 1 and len(kw) < 50:
            cleaned_keywords.append(kw)
    
    return cleaned_keywords[:6]  # 最多返回6個


def _postprocess_keywords(keywords: List[str], lang: str, expected_count: int) -> List[str]:
    """
    關鍵字後處理和驗證
    """
    if not keywords:
        return _generate_fallback_keywords(lang, expected_count)
    
    # 清理關鍵字
    cleaned = []
    for kw in keywords:
        if isinstance(kw, str):
            kw = kw.strip().strip('"\'.,;')
            # 移除數字開頭的編號
            kw = re.sub(r'^\d+[.)]\s*', '', kw)
            # 移除過短或過長的關鍵字
            if 1 < len(kw) < 50:
                cleaned.append(kw)
    
    # 去重但保持順序
    unique_keywords = []
    seen = set()
    for kw in cleaned:
        kw_lower = kw.lower()
        if kw_lower not in seen:
            unique_keywords.append(kw)
            seen.add(kw_lower)
    
    # 確保數量足夠
    if len(unique_keywords) < expected_count:
        fallback = _generate_fallback_keywords(lang, expected_count - len(unique_keywords))
        unique_keywords.extend(fallback)
    
    return unique_keywords[:expected_count * 2]  # 允許稍微超過期望數量


def _generate_fallback_keywords(lang: str, count: int = 3, error_context: str = "") -> List[str]:
    """
    生成語言特定的後備關鍵字
    """
    if lang in ["zh", "chinese"]:
        base_words = ["關鍵概念", "核心內容", "重要信息", "主要話題", "相關術語"]
    elif lang in ["en", "english"]:
        base_words = ["key_concept", "core_content", "main_topic", "important_info", "relevant_term"]
    elif lang == "mixed":
        base_words = ["核心概念", "key_concept", "重要內容", "main_topic", "相關信息"]
    else:
        base_words = ["concept", "topic", "content", "information", "term"]
    
    # 添加錯誤上下文標識（如果有）
    if error_context:
        error_suffix = "_error" if lang == "en" else "_錯誤"
        base_words = [f"{word}{error_suffix}" for word in base_words[:count]]
    
    # 確保有足夠數量
    while len(base_words) < count:
        base_words.extend(base_words[:count - len(base_words)])
    
    return base_words[:count]


# ========== 測試和調試函數 ==========

def test_language_detection():
    """
    測試語言檢測功能
    """
    test_chunks = [
        {"text": "這是一個中文測試文檔，包含技術內容。"},
        {"text": "This is an English test document with technical content."},
        {"text": "這是mixed內容，包含Chinese和English text。"},
        {"text": "TSMC台積電使用advanced manufacturing technology先進製造技術。"}
    ]
    
    print("=== 語言檢測測試 ===")
    for i, chunk in enumerate(test_chunks):
        detected = _detect_chunk_language_preference(chunk, "auto")
        print(f"Chunk {i+1}: '{chunk['text'][:30]}...' -> {detected}")


def test_keyword_generation():
    """
    測試關鍵字生成功能
    """
    test_cases = [
        {
            "text": "台積電是全球最大的半導體代工廠，採用先進的7奈米製程技術。",
            "lang": "zh",
            "expected": ["台積電", "半導體", "7奈米"]
        },
        {
            "text": "TSMC is the world's largest semiconductor foundry using advanced 7nm technology.",
            "lang": "en", 
            "expected": ["TSMC", "semiconductor", "7nm"]
        }
    ]
    
    print("\n=== 關鍵字生成測試 ===")
    for i, case in enumerate(test_cases):
        try:
            keywords = generate_keywords(
                text=case["text"],
                n=3,
                lang=case["lang"]
            )
            print(f"Test {i+1} ({case['lang']}): {keywords}")
        except Exception as e:
            print(f"Test {i+1} 失敗: {e}")


if __name__ == "__main__":
    # 運行測試
    test_language_detection()
    test_keyword_generation()