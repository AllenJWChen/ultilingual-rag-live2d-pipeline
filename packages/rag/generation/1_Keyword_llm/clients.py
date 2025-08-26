# ================================
# 修復版 clients.py (無語法錯誤)
# 路徑: packages/rag/generation/1_Keyword_llm/clients.py
# ================================

# -*- coding: utf-8 -*-
"""
完整修復版語言感知關鍵字客戶端模組 (clients.py)
🔧 修復語法錯誤並適配 1_Keyword_llm 路徑結構
"""

import json
import re
import time
import requests
from typing import List, Dict, Optional, Union

# 修復 import 路徑
try:
    from .prompts import (
        build_keywords_prompt,
        build_adaptive_keywords_prompt,
        build_contextual_keywords_prompt,
        build_quality_enhanced_keywords_prompt,
        build_domain_specific_keywords_prompt,
        build_fallback_keywords_prompt
    )
except ImportError:
    # 如果相對路徑失敗，嘗試絕對路徑
    try:
        from packages.rag.generation.keyword_llm.prompts import (
            build_keywords_prompt,
            build_adaptive_keywords_prompt,
            build_contextual_keywords_prompt,
            build_quality_enhanced_keywords_prompt,
            build_domain_specific_keywords_prompt,
            build_fallback_keywords_prompt
        )
    except ImportError:
        print("Warning: 無法導入 prompts 模組，使用基礎提示詞")
        def build_keywords_prompt(text: str, n: int = 3, lang: str = "en") -> str:
            if lang in ["zh", "chinese"]:
                return f"請從以下文本中提取{n}個關鍵字，輸出JSON格式：{text}"
            elif lang in ["ja", "japanese"]:
                return f"以下のテキストから{n}個のキーワードを抽出し、JSON形式で出力してください：{text}"
            else:
                return f"Extract {n} keywords from the following text in JSON format: {text}"


# ========== 語言感知配置 ==========

LANGUAGE_AWARE_CONFIG = {
    "chinese": {
        "temperature": 0.3,
        "max_tokens": 200,
        "timeout": 30,
        "retry_count": 3
    },
    "english": {
        "temperature": 0.2,
        "max_tokens": 150,
        "timeout": 25,
        "retry_count": 3
    },
    "japanese": {
        "temperature": 0.25,
        "max_tokens": 180,
        "timeout": 30,
        "retry_count": 3
    },
    "mixed": {
        "temperature": 0.25,
        "max_tokens": 250,
        "timeout": 35,
        "retry_count": 3
    },
    "auto": {
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
    """修復版語言感知關鍵字生成函數"""
    
    if not text or not text.strip():
        return _generate_fallback_keywords(lang, n)
    
    # 選擇提示詞
    prompt = _select_optimal_prompt(
        text=text, n=n, lang=lang, content_type=content_type,
        quality_score=quality_score, domain=domain, 
        context_keywords=context_keywords
    )
    
    # 獲取配置
    config = LANGUAGE_AWARE_CONFIG.get(lang, LANGUAGE_AWARE_CONFIG["auto"])
    
    # 語言特定優化
    if lang in ["en", "english"]:
        config = config.copy()
        config["temperature"] = 0.1
    elif lang in ["ja", "japanese"]:
        config = config.copy()
        config["temperature"] = 0.15
    
    # 執行LLM調用
    try:
        keywords = _call_llm_with_retry(
            prompt=prompt, config=config, expected_count=n, lang=lang
        )
        
        keywords = _postprocess_keywords(keywords, lang, n)
        
        if _is_valid_keywords(keywords, lang):
            return keywords
        else:
            return _generate_fallback_keywords(lang, n, "invalid_extraction")
        
    except Exception as e:
        return _generate_fallback_keywords(lang, n, str(e))


def generate_keywords_batch(chunks: List[Dict], n: int = 3, lang: str = "en") -> List[Dict]:
    """批量關鍵字生成"""
    
    if not chunks:
        return []
    
    print(f"批量處理 {len(chunks)} 個chunks...")
    
    results = []
    
    for i, chunk in enumerate(chunks):
        try:
            chunk_lang = _detect_chunk_language_preference(chunk, lang)
            
            keywords = generate_keywords(
                text=chunk.get("text", ""),
                n=n,
                lang=chunk_lang
            )
            
            processing_success = _is_valid_keywords(keywords, chunk_lang)
            
            result = {
                "chunk_id": i,
                "source": chunk.get("source", "unknown"),
                "page": chunk.get("page", 0),
                "keywords": keywords,
                "detected_language": chunk_lang,
                "processing_success": processing_success
            }
            
            results.append(result)
            
        except Exception as e:
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
    print(f"完成: {success_count}/{len(results)} 成功 ({success_count/len(results)*100:.1f}%)")
    
    return results


# ========== 輔助函數 ==========

def _select_optimal_prompt(text: str, n: int, lang: str, **kwargs) -> str:
    """選擇最優提示詞"""
    return build_keywords_prompt(text, n, lang)


def _detect_chunk_language_preference(chunk: Dict, default_lang: str) -> str:
    """檢測chunk語言偏好"""
    
    if "main_language" in chunk:
        main_lang = chunk["main_language"]
        lang_mapping = {
            "chinese": "zh", "english": "en", "japanese": "ja",
            "mixed": "mixed", "unknown": "auto"
        }
        return lang_mapping.get(main_lang, default_lang)
    
    text = chunk.get("text", "")
    if text:
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text))
        total_chars = chinese_chars + english_chars + japanese_chars
        
        if total_chars > 0:
            japanese_ratio = japanese_chars / total_chars
            chinese_ratio = chinese_chars / total_chars
            english_ratio = english_chars / total_chars
            
            if japanese_ratio > 0.3:
                return "ja"
            elif chinese_ratio > 0.6:
                return "zh"
            elif english_ratio > 0.6:
                return "en"
            else:
                return "mixed"
    
    return default_lang


def _call_llm_with_retry(prompt: str, config: Dict, expected_count: int, lang: str = "en") -> List[str]:
    """帶重試的LLM調用"""
    
    max_retries = config.get("retry_count", 3)
    timeout = config.get("timeout", 30)
    
    for attempt in range(max_retries):
        try:
            if lang in ["en", "english"]:
                response = _call_ollama_api_english_optimized(prompt, config, timeout)
            elif lang in ["ja", "japanese"]:
                response = _call_ollama_api_japanese_optimized(prompt, config, timeout)
            else:
                response = _call_ollama_api_fixed(prompt, config, timeout)
            
            return response
            
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise e


def _call_ollama_api_fixed(prompt: str, config: Dict, timeout: int) -> List[str]:
    """修復版Ollama API調用"""
    
    try:
        url = "http://localhost:11434/api/generate"
        
        payload = {
            "model": "llama3.1:latest",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": config.get("temperature", 0.3),
                "num_predict": config.get("max_tokens", 200),
                "stop": ["\n\n", "---", "###"],
                "top_k": 40,
                "top_p": 0.9,
                "repeat_penalty": 1.1
            }
        }
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            try:
                result = response.json()
                text_response = result.get("response", "").strip()
                keywords = _parse_llm_response_enhanced(text_response)
                return keywords if keywords else []
                    
            except json.JSONDecodeError:
                return _emergency_keyword_extract(response.text)
        else:
            raise Exception(f"API調用失敗: {response.status_code}")
            
    except requests.RequestException as e:
        raise Exception(f"網絡請求失敗: {e}")


def _call_ollama_api_english_optimized(prompt: str, config: Dict, timeout: int) -> List[str]:
    """英文優化版API調用"""
    
    try:
        url = "http://localhost:11434/api/generate"
        
        payload = {
            "model": "llama3.1:latest",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.05,
                "num_predict": 80,
                "stop": ["\n", "---", "Note:", "Remember:", "Content:", "Text:"],
                "top_k": 10,
                "top_p": 0.7,
                "repeat_penalty": 1.3,
                "seed": 42
            }
        }
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            result = response.json()
            text_response = result.get("response", "").strip()
            keywords = _parse_english_keywords_enhanced(text_response)
            return keywords if keywords else []
                
        else:
            raise Exception(f"英文API調用失敗: {response.status_code}")
            
    except Exception as e:
        raise Exception(f"英文請求失敗: {e}")


def _call_ollama_api_japanese_optimized(prompt: str, config: Dict, timeout: int) -> List[str]:
    """日文優化版API調用"""
    
    try:
        url = "http://localhost:11434/api/generate"
        
        payload = {
            "model": "llama3.1:latest",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.15,
                "num_predict": 120,
                "stop": ["\n\n", "---", "注意:", "記住:", "內容:", "テキスト:"],
                "top_k": 25,
                "top_p": 0.8,
                "repeat_penalty": 1.15,
                "seed": 123
            }
        }
        
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers, timeout=timeout)
        
        if response.status_code == 200:
            result = response.json()
            text_response = result.get("response", "").strip()
            keywords = _parse_japanese_keywords_enhanced(text_response)
            return keywords if keywords else []
                
        else:
            raise Exception(f"日文API調用失敗: {response.status_code}")
            
    except Exception as e:
        raise Exception(f"日文請求失敗: {e}")


def _parse_llm_response_enhanced(text_response: str) -> List[str]:
    """增強版LLM響應解析"""
    
    if not text_response:
        return []
    
    # 處理 "Here are the" 開頭的響應
    if "Here are the" in text_response and "keywords" in text_response:
        pattern = r'Here are the.*?keywords[^:]*:?\s*(.*?)(?:\n\n|$)'
        match = re.search(pattern, text_response, re.DOTALL | re.IGNORECASE)
        if match:
            keywords_text = match.group(1).strip()
            keywords = _extract_keywords_from_text(keywords_text)
            if keywords:
                return keywords
    
    # JSON陣列解析
    json_patterns = [
        r'\[(.*?)\]',
        r'keywords?\s*[:\-]\s*\[(.*?)\]',
        r'回答\s*[：:]\s*\[(.*?)\]'
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, text_response, re.DOTALL | re.IGNORECASE)
        for match in matches:
            try:
                if isinstance(match, tuple):
                    keywords = [kw.strip().strip('"\'') for kw in match if kw.strip()]
                else:
                    json_str = f'[{match}]'
                    keywords = json.loads(json_str)
                    keywords = [str(kw).strip().strip('"\'') for kw in keywords if kw]
                
                if keywords:
                    return keywords[:6]
            except json.JSONDecodeError:
                continue
    
    # 引號詞匹配
    quoted_patterns = [r'"([^"]+)"', r'「([^」]+)」', r'『([^』]+)』', r"'([^']+)'"]
    
    quoted_words = []
    for pattern in quoted_patterns:
        matches = re.findall(pattern, text_response)
        quoted_words.extend([w.strip() for w in matches if w.strip()])
    
    if quoted_words:
        clean_words = [w for w in quoted_words if 1 < len(w) < 50]
        if clean_words:
            return clean_words[:6]
    
    # 行分割解析
    lines = [line.strip() for line in text_response.split('\n') if line.strip()]
    potential_keywords = []
    
    for line in lines:
        if any(skip in line.lower() for skip in ['here are', 'keywords', 'extracted', 'format', 'json']):
            continue
        
        cleaned = re.sub(r'^\d+[.)]\s*', '', line)
        cleaned = re.sub(r'^[-*•]\s*', '', cleaned)
        cleaned = cleaned.strip('.,;:"\'')
        
        if cleaned and 2 <= len(cleaned) <= 40:
            potential_keywords.append(cleaned)
    
    return potential_keywords[:6] if potential_keywords else []


def _parse_english_keywords_enhanced(text_response: str) -> List[str]:
    """英文關鍵字專用解析器"""
    
    if not text_response:
        return []
    
    # 處理 "Here are the extracted keywords in JSON format:" 響應
    if "JSON format" in text_response:
        json_start = text_response.lower().find("json format")
        if json_start != -1:
            json_part = text_response[json_start + 11:].strip()
            json_match = re.search(r'\[(.*?)\]', json_part, re.DOTALL)
            if json_match:
                try:
                    json_str = f'[{json_match.group(1)}]'
                    keywords = json.loads(json_str)
                    keywords = [str(kw).strip().strip('"\'') for kw in keywords if kw]
                    if keywords:
                        # 修復語法錯誤：正確的字符串結束
                        valid_keywords = []
                        for kw in keywords:
                            if re.match(r'^[a-zA-Z][a-zA-Z\s\-_]{1,30}$', kw):
                                valid_keywords.append(kw.title())
                        return valid_keywords[:5]
                except json.JSONDecodeError:
                    pass
    
    # 處理 "Here are the 4 most important keywords" 響應
    if "most important keywords" in text_response:
        important_start = text_response.lower().find("most important keywords")
        if important_start != -1:
            content = text_response[important_start + 23:].strip()
            numbered_pattern = r'\d+\.\s*"?([^"\n]+)"?'
            numbered_matches = re.findall(numbered_pattern, content)
            if numbered_matches:
                valid_keywords = []
                for kw in numbered_matches:
                    kw = kw.strip().strip('.,;:"\'')
                    if re.match(r'^[a-zA-Z][a-zA-Z\s\-_]{1,30}$', kw):
                        valid_keywords.append(kw.title())
                if valid_keywords:
                    return valid_keywords[:5]
    
    # 使用通用解析
    return _parse_llm_response_enhanced(text_response)


def _parse_japanese_keywords_enhanced(text_response: str) -> List[str]:
    """日文關鍵字專用解析器"""
    
    if not text_response:
        return []
    
    # 日文特定模式
    japanese_indicators = ["キーワード", "重要な語", "主要語", "用語"]
    
    has_japanese_indicator = any(indicator in text_response for indicator in japanese_indicators)
    
    if has_japanese_indicator:
        json_patterns = [
            r'\[(.*?)\]',
            r'キーワード\s*[：:]\s*\[(.*?)\]',
            r'用語\s*[：:]\s*\[(.*?)\]'
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, text_response, re.DOTALL)
            for match in matches:
                try:
                    json_str = f'[{match}]'
                    keywords = json.loads(json_str)
                    keywords = [str(kw).strip().strip('"\'') for kw in keywords if kw]
                    if keywords:
                        valid_japanese = []
                        for kw in keywords:
                            if re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', kw):
                                valid_japanese.append(kw)
                        return valid_japanese[:6]
                except json.JSONDecodeError:
                    continue
    
    # 日文引號模式
    japanese_quotes = [
        r'「([^」]+)」',
        r'『([^』]+)』',
        r'"([^"]*[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff][^"]*)"'
    ]
    
    japanese_words = []
    for pattern in japanese_quotes:
        matches = re.findall(pattern, text_response)
        japanese_words.extend([w.strip() for w in matches if w.strip()])
    
    if japanese_words:
        valid_words = []
        for word in japanese_words:
            if 1 < len(word) < 20 and re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', word):
                valid_words.append(word)
        
        if valid_words:
            return valid_words[:6]
    
    # 提取包含日文字符的詞彙
    japanese_terms = re.findall(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]{2,10}', text_response)
    if japanese_terms:
        unique_terms = list(dict.fromkeys(japanese_terms))[:6]
        return unique_terms
    
    return []


def _extract_keywords_from_text(keywords_text: str) -> List[str]:
    """從描述性文本中提取關鍵字"""
    
    # JSON解析
    json_match = re.search(r'\[(.*?)\]', keywords_text, re.DOTALL)
    if json_match:
        try:
            json_str = f'[{json_match.group(1)}]'
            keywords = json.loads(json_str)
            return [str(kw).strip().strip('"\'') for kw in keywords if kw]
        except json.JSONDecodeError:
            pass
    
    # 編號列表解析
    numbered_pattern = r'\d+\.\s*"?([^"\n]+)"?'
    numbered_matches = re.findall(numbered_pattern, keywords_text)
    if numbered_matches:
        return [kw.strip().strip('.,;:"\'') for kw in numbered_matches]
    
    # 逗號分隔解析
    if ',' in keywords_text:
        parts = keywords_text.split(',')
        keywords = []
        for part in parts:
            cleaned = part.strip().strip('.,;:"\'')
            if cleaned and 1 < len(cleaned) < 50:
                keywords.append(cleaned)
        if keywords:
            return keywords
    
    return []


def _emergency_keyword_extract(raw_response: str) -> List[str]:
    """應急關鍵字提取"""
    words = re.findall(r'[a-zA-Z\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{2,}', raw_response)
    
    stopwords = {'the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 
                'keywords', 'extract', 'content', 'text', 'following', 'format', 'json'}
    
    filtered_words = [w for w in words if w.lower() not in stopwords and len(w) > 2]
    unique_words = list(dict.fromkeys(filtered_words))
    
    return unique_words[:3] if unique_words else []


def _is_valid_keywords(keywords: List[str], lang: str) -> bool:
    """檢查關鍵字是否有效"""
    
    if not keywords:
        return False
    
    # 檢查後備關鍵字指標
    fallback_indicators = [
        'fallback', 'emergency', 'error', 'supplementary',
        'Error', 'Emergency', 'Fallback', 'invalid',
        'Key_Concept', 'Main_Topic', 'Core_Content',
        '關鍵概念', '核心內容', '重要信息', '主要話題',
        'キーワード', '重要語', '主要概念', '核心内容',
        'emergency_kw', 'fallback_kw', 'supplementary_'
    ]
    
    # 如果所有關鍵字都包含後備指示詞，則認為無效
    fallback_count = 0
    for kw in keywords:
        if any(indicator in kw for indicator in fallback_indicators):
            fallback_count += 1
    
    # 如果超過一半是後備關鍵字，認為無效
    if fallback_count > len(keywords) * 0.5:
        return False
    
    # 語言特定驗證
    if lang in ["en", "english"]:
        valid_count = sum(1 for kw in keywords if re.search(r'[a-zA-Z]', kw))
        return valid_count > 0
    elif lang in ["zh", "chinese"]:
        valid_count = sum(1 for kw in keywords if re.search(r'[\u4e00-\u9fff]', kw))
        return valid_count > 0
    elif lang in ["ja", "japanese"]:
        valid_count = sum(1 for kw in keywords if re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', kw))
        return valid_count > 0
    
    return True


def _postprocess_keywords(keywords: List[str], lang: str, expected_count: int) -> List[str]:
    """關鍵字後處理和驗證"""
    
    if not keywords:
        return _generate_fallback_keywords(lang, expected_count)
    
    # 清理關鍵字
    cleaned = []
    for kw in keywords:
        if isinstance(kw, str):
            kw = kw.strip().strip('"\'.,;')
            # 移除數字開頭的編號
            kw = re.sub(r'^\d+[.)]\s*', '', kw)
            
            # 語言特定驗證
            if lang in ["en", "english"]:
                # 修復語法錯誤：正確的字符串結束
                if re.match(r'^[a-zA-Z][a-zA-Z\s\-_]{1,40}$', kw):
                    cleaned.append(kw.title())
            elif lang in ["zh", "chinese"]:
                if 1 < len(kw) < 20:
                    cleaned.append(kw)
            elif lang in ["ja", "japanese"]:
                if 1 < len(kw) < 15 and re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', kw):
                    cleaned.append(kw)
            else:
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
    
    result = unique_keywords[:expected_count * 2]
    return result if result else []


def _generate_fallback_keywords(lang: str, count: int = 3, error_context: str = "") -> List[str]:
    """生成語言特定的後備關鍵字"""
    
    if lang in ["en", "english"]:
        base_words = ["Key_Concept", "Main_Topic", "Core_Content", "Important_Info", "Relevant_Term"]
    elif lang in ["zh", "chinese"]:
        base_words = ["關鍵概念", "核心內容", "重要信息", "主要話題", "相關術語"]
    elif lang in ["ja", "japanese"]:
        base_words = ["キーワード", "重要語", "主要概念", "核心内容", "関連用語"]
    elif lang == "mixed":
        base_words = ["核心概念", "Key_Concept", "キーワード", "Main_Topic", "重要内容"]
    else:
        base_words = ["Concept", "Topic", "Content", "Information", "Term"]
    
    # 添加錯誤上下文標識
    if error_context:
        if lang in ["en", "english"]:
            error_suffix = "_Error"
        elif lang in ["ja", "japanese"]:
            error_suffix = "_エラー"
        else:
            error_suffix = "_錯誤"
        base_words = [f"{word}{error_suffix}" for word in base_words[:count]]
    
    # 確保有足夠數量
    while len(base_words) < count:
        base_words.extend(base_words[:count - len(base_words)])
    
    return base_words[:count]


# ========== 測試函數 ==========

def test_syntax_fix():
    """測試語法修復是否成功"""
    print("測試語法修復...")
    
    try:
        # 測試基本功能
        keywords = generate_keywords("TSMC semiconductor technology", n=3, lang="en")
        print(f"英文測試結果: {keywords}")
        
        keywords = generate_keywords("台積電半導體技術", n=3, lang="zh")
        print(f"中文測試結果: {keywords}")
        
        keywords = generate_keywords("TSMCは半導体技術", n=3, lang="ja")
        print(f"日文測試結果: {keywords}")
        
        print("語法修復測試通過")
        return True
        
    except Exception as e:
        print(f"語法修復測試失敗: {e}")
        return False


if __name__ == "__main__":
    test_syntax_fix()
