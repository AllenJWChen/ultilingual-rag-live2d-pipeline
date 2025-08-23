# -*- coding: utf-8 -*-
from __future__ import annotations
from textwrap import dedent

def build_keywords_prompt(text: str, n: int = 3, lang: str = "en") -> str:
    """
    建立關鍵字擷取 prompt - 改進版本
    
    改進重點：
    1. 更精確的領域術語抽取
    2. 避免過於泛用的關鍵字  
    3. 中英文一致性處理
    4. 技術文件特化優化
    """
    
    # 檢測內容語言傾向
    chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
    english_words = len([w for w in text.split() if w.isalpha() and len(w) > 2])
    
    # 自動語言判斷
    if lang == "auto":
        if chinese_chars > english_words * 2:
            lang = "zh"
        else:
            lang = "en"
    
    if lang.lower() == "zh":
        return dedent(f"""
        你是專業的技術文件分析師。從下列文字中抽取 {n} 個最具代表性的**專業術語**或**核心概念**。

        要求：
        1. 使用繁體中文術語（2-4個字）
        2. 優先選擇：公司名稱、產品型號、技術規格、行業術語
        3. 避免過於泛用的詞彙（如：技術、發展、市場）
        4. 避免年份、數字等時間性詞彙
        5. 只輸出JSON格式：["術語1", "術語2", "術語3"]

        範例：
        - 好的關鍵字：["台積電", "7奈米製程", "晶圓代工"]
        - 不好的關鍵字：["技術", "發展", "2024"]

        文字內容：
        {text}

        關鍵字JSON：
        """).strip()

    # 英文版本 - 針對技術文件優化
    return dedent(f"""
        You are a technical document analyst. Extract {n} highly specific **domain terms** or **key concepts** from the text below.

        Requirements:
        1. Use precise English terms (1-4 words max)
        2. Prioritize: company names, product models, technical specifications, industry terms
        3. Avoid generic words (technology, development, market, system)
        4. Avoid years, dates, or temporal references  
        5. Focus on actionable, searchable terms
        6. Output ONLY JSON format: ["term1", "term2", "term3"]

        Examples:
        - Good keywords: ["OLED displays", "Micro LED", "CES 2025"]
        - Poor keywords: ["technology", "development", "market"]

        Text content:
        {text}

        Keywords JSON:
        """).strip()


def build_contextual_keywords_prompt(text: str, context_keywords: list = None, n: int = 3, lang: str = "en") -> str:
    """
    上下文感知的關鍵字生成 - 考慮已有關鍵字的情況下生成互補關鍵字
    
    Args:
        text: 要分析的文字
        context_keywords: 已有的關鍵字列表（來自相鄰chunks或相同文件）
        n: 需要的關鍵字數量
        lang: 語言
    """
    
    context_info = ""
    if context_keywords:
        context_list = ", ".join(context_keywords[:10])  # 避免prompt過長
        if lang.lower() == "zh":
            context_info = f"\n已知相關關鍵字：{context_list}\n請生成**互補且不重複**的關鍵字。\n"
        else:
            context_info = f"\nExisting related keywords: {context_list}\nGenerate **complementary and non-duplicate** keywords.\n"
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    # 在要求部分插入上下文信息
    if lang.lower() == "zh":
        context_section = f"{context_info}特別注意：與已知關鍵字形成主題完整性，但不要重複。"
    else:
        context_section = f"{context_info}Focus on: Terms that complement existing keywords but provide new information."
    
    return base_prompt.replace("要求：", f"要求：\n{context_section}\n原要求：") if lang.lower() == "zh" else \
           base_prompt.replace("Requirements:", f"Requirements:\n{context_section}\nOriginal requirements:")


def build_adaptive_keywords_prompt(text: str, content_type: str = "auto", n: int = 3, lang: str = "en") -> str:
    """
    自適應關鍵字生成 - 根據內容類型調整策略
    
    Args:
        content_type: "technical", "business", "academic", "auto"
    """
    
    # 自動檢測內容類型
    if content_type == "auto":
        text_lower = text.lower()
        if any(indicator in text_lower for indicator in ["patent", "algorithm", "specification", "protocol"]):
            content_type = "technical"
        elif any(indicator in text_lower for indicator in ["market", "revenue", "business", "strategy"]):
            content_type = "business"  
        elif any(indicator in text_lower for indicator in ["research", "study", "analysis", "methodology"]):
            content_type = "academic"
        else:
            content_type = "general"
    
    # 根據內容類型調整提示詞
    specialized_instructions = {
        "technical": {
            "zh": "專注於技術規格、產品型號、製程參數、協議標準",
            "en": "Focus on technical specs, product models, process parameters, protocol standards"
        },
        "business": {
            "zh": "專注於公司名稱、商業模式、市場策略、產業趨勢",
            "en": "Focus on company names, business models, market strategies, industry trends"
        },
        "academic": {
            "zh": "專注於研究方法、理論概念、實驗結果、學術術語",
            "en": "Focus on research methods, theoretical concepts, experimental results, academic terms"
        },
        "general": {
            "zh": "專注於核心主題、關鍵概念、重要實體",
            "en": "Focus on core topics, key concepts, important entities"
        }
    }
    
    lang_key = "zh" if lang.lower() == "zh" else "en"
    additional_instruction = specialized_instructions[content_type][lang_key]
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    # 插入專門化指令
    if lang.lower() == "zh":
        return base_prompt.replace("要求：", f"內容類型：{content_type.upper()}\n特化要求：{additional_instruction}\n\n要求：")
    else:
        return base_prompt.replace("Requirements:", f"Content type: {content_type.upper()}\nSpecialized focus: {additional_instruction}\n\nRequirements:")