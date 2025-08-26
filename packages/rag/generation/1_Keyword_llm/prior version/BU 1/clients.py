# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import json
from typing import List, Optional

# 改進版本：導入新的prompt函數
from .prompts import build_keywords_prompt, build_adaptive_keywords_prompt

# 環境變數配置
LLM_MODE = os.getenv("LLM_MODE", "OPENAI_COMPAT").upper().strip()
MODEL_KEYWORDS = os.getenv("MODEL_KEYWORDS", "llama3.1:latest")

# -------------- 改進版本：更智能的關鍵字清理 --------------
def _postprocess_keywords(raw_items: List[str], n: int, text: str = "") -> List[str]:
    """
    改進版關鍵字後處理：更嚴格的品質控制
    """
    cleaned: List[str] = []
    
    # 禁用詞列表（太過泛用的詞彙）
    generic_terms = {
        # 英文泛用詞
        "technology", "development", "market", "system", "solution", "product", 
        "company", "industry", "business", "service", "application", "platform",
        "research", "analysis", "study", "report", "data", "information",
        
        # 中文泛用詞  
        "技術", "發展", "市場", "系統", "解決方案", "產品", "公司", "行業",
        "商業", "服務", "應用", "平台", "研究", "分析", "報告", "資料"
    }
    
    # 時間性詞彙模式
    temporal_pattern = re.compile(r'^\d{4}年?$|^\d+月$|^第\d+季$|^Q[1-4]$', re.IGNORECASE)
    
    for k in raw_items:
        # 基本清理
        k = k.strip().strip("，,;、.。:：-—\"'「」『』()（）[]【】<>《》")
        
        # 過濾條件
        if not k:
            continue
        if len(k) < 2:  # 太短
            continue
        if re.fullmatch(r"[\W_]+", k):  # 只有符號
            continue
        if k.lower() in generic_terms:  # 泛用詞
            continue
        if temporal_pattern.match(k):  # 時間性詞彙
            continue
        if re.match(r'^\d+\.?\d*[%萬億千百十]?$', k):  # 純數字
            continue
        
        # 去重（保留順序）
        if k not in cleaned:
            cleaned.append(k)
    
    # 如果清理後不夠，用fallback策略
    if len(cleaned) < n:
        fallback_keywords = _extract_fallback_keywords(text, n - len(cleaned))
        cleaned.extend(fallback_keywords)
    
    return cleaned[:max(1, n)]


def _extract_fallback_keywords(text: str, needed: int) -> List[str]:
    """
    Fallback策略：從文本中提取高頻且有意義的詞彙
    """
    # 提取候選詞
    candidates = []
    
    # 中文詞彙（2-4字）
    chinese_terms = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
    candidates.extend(chinese_terms)
    
    # 英文詞彙（大寫開頭的專有名詞優先）
    english_terms = re.findall(r'[A-Z][a-zA-Z]{1,15}', text)  # 專有名詞
    candidates.extend(english_terms)
    
    # 技術縮寫（全大寫2-5字母）
    acronyms = re.findall(r'\b[A-Z]{2,5}\b', text)
    candidates.extend(acronyms)
    
    # 統計頻次並過濾
    freq_count = {}
    for term in candidates:
        if len(term) >= 2 and not re.match(r'^\d+$', term):
            freq_count[term] = freq_count.get(term, 0) + 1
    
    # 按頻次排序，取前N個
    sorted_terms = sorted(freq_count.items(), key=lambda x: (-x[1], x[0]))
    return [term for term, _ in sorted_terms[:needed]]


def _split_keywords(s: str) -> List[str]:
    """
    改進版關鍵字分割：處理JSON格式和多種分隔符
    """
    # 嘗試解析JSON格式
    s = s.strip()
    if s.startswith('[') and s.endswith(']'):
        try:
            json_result = json.loads(s)
            if isinstance(json_result, list):
                return [str(item).strip() for item in json_result if str(item).strip()]
        except json.JSONDecodeError:
            pass
    
    # 移除JSON標記但保留內容
    s = re.sub(r'^\[|\]$', '', s)
    s = re.sub(r'^[\'""]|[\'""]$', '', s)
    
    # 多種分隔符分割
    parts = re.split(r'[,\n，、;；]\s*[\'""]?', s)
    return [p.strip().strip('\'"\"') for p in parts if p.strip()]


# -------------- MOCK模式改進 --------------
def _generate_keywords_mock(text: str, n: int, lang: str) -> List[str]:
    """
    改進版MOCK模式：更智能的本地關鍵字提取
    """
    return _extract_fallback_keywords(text, n)


# -------------- OpenAI兼容模式改進 --------------
def _generate_keywords_openai_compat(text: str, n: int, lang: str, content_type: str = "auto") -> List[str]:
    """
    改進版OpenAI兼容模式：使用新的prompt策略
    """
    try:
        from openai import OpenAI
        client = OpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("OPENAI_API_KEY", "ollama"),
        )
    except Exception:
        return _generate_keywords_mock(text, n, lang)

    # 使用自適應prompt
    prompt = build_adaptive_keywords_prompt(text, content_type, n, lang)
    
    try:
        resp = client.chat.completions.create(
            model=MODEL_KEYWORDS,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,  # 降低溫度提高一致性
            max_tokens=150,   # 增加tokens以獲得更好的回應
        )
        
        output = resp.choices[0].message.content.strip()
        
        # 處理回應
        items = _split_keywords(output)
        return _postprocess_keywords(items, n, text)
        
    except Exception as e:
        print(f"[WARN] OpenAI API調用失敗: {e}, 使用fallback")
        return _generate_keywords_mock(text, n, lang)


# -------------- 主要接口改進 --------------
def generate_keywords(text: str, n: int = 3, lang: str = "auto", content_type: str = "auto") -> List[str]:
    """
    改進版關鍵字生成主函數
    
    Args:
        text: 輸入文本
        n: 關鍵字數量
        lang: 語言 ("auto", "zh", "en") 
        content_type: 內容類型 ("auto", "technical", "business", "academic")
    
    Returns:
        List[str]: 生成的關鍵字列表
    """
    if not text or not text.strip():
        return [f"empty_text_{i+1}" for i in range(n)]
    
    # 自動語言檢測改進
    if lang == "auto":
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        
        if chinese_chars > english_chars:
            lang = "zh"
        else:
            lang = "en"
    
    # 根據模式選擇生成方法
    mode = LLM_MODE
    if mode == "MOCK":
        return _generate_keywords_mock(text, n, lang)
    
    try:
        return _generate_keywords_openai_compat(text, n, lang, content_type)
    except Exception as e:
        print(f"[ERROR] 關鍵字生成失敗: {e}")
        return _generate_keywords_mock(text, n, lang)


def generate_keywords_batch(chunks: List[dict], n: int = 3, lang: str = "auto") -> List[dict]:
    """
    批量關鍵字生成 - 考慮上下文相關性
    
    Args:
        chunks: 包含text字段的chunk列表  
        n: 每個chunk的關鍵字數量
        lang: 語言
    
    Returns:
        List[dict]: 添加了keywords字段的chunk列表
    """
    results = []
    context_keywords = []  # 累積的關鍵字上下文
    
    for i, chunk in enumerate(chunks):
        text = chunk.get("text", "")
        
        # 檢測內容類型
        content_type = "auto"
        if "display" in text.lower() or "screen" in text.lower():
            content_type = "technical"
        elif "market" in text.lower() or "revenue" in text.lower():
            content_type = "business"
            
        # 生成關鍵字
        keywords = generate_keywords(text, n, lang, content_type)
        
        # 更新上下文（保留最近的關鍵字作為上下文）
        context_keywords.extend(keywords)
        context_keywords = list(dict.fromkeys(context_keywords))[-20:]  # 保留最近20個不重複關鍵字
        
        # 創建結果
        result = chunk.copy()
        result["keywords"] = keywords
        results.append(result)
    
    return results


__all__ = ["generate_keywords", "generate_keywords_batch"]