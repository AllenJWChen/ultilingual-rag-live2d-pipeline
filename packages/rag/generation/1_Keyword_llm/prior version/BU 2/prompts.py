# -*- coding: utf-8 -*-
"""
語言感知關鍵字提示詞模組 (prompts.py)
基於原有 prompts.py 架構，增加語言感知功能

主要功能：
1. 根據檢測到的語言選擇合適的提示詞
2. 支援中文、英文、混合語言的關鍵字生成
3. 針對不同內容類型優化提示策略
4. 保持與現有 clients.py 的兼容性
"""

import re
from typing import List, Optional


def build_keywords_prompt(text: str, n: int = 3, lang: str = "en") -> str:
    """
    改進版關鍵字生成提示詞 - 支援語言感知
    
    Args:
        text: 要分析的文字
        n: 需要的關鍵字數量
        lang: 目標語言 ("zh", "en", "mixed", "auto")
    """
    
    # 根據lang參數選擇合適的提示詞
    if lang.lower() in ["zh", "chinese"]:
        return build_chinese_keywords_prompt(text, n)
    elif lang.lower() in ["en", "english"]:
        return build_english_keywords_prompt(text, n)
    elif lang.lower() in ["mixed", "bilingual"]:
        return build_mixed_keywords_prompt(text, n)
    else:
        # auto模式：根據文本內容自動選擇
        return build_auto_keywords_prompt(text, n)


def build_chinese_keywords_prompt(text: str, n: int = 3) -> str:
    """
    中文關鍵字生成提示詞
    """
    return f"""你是一個專業的中文關鍵字提取專家。請為以下中文內容提取 {n} 個最重要的關鍵字。

⚠️ 嚴格要求：
1. 關鍵字必須**直接出現**在文本中或與內容**密切相關**
2. 使用準確的中文詞彙（1-4個字為佳）
3. 優先級：專有名詞 > 技術術語 > 核心概念
4. **絕對禁止**：不相關的詞彙（例如：內容講Darwin，不要生成"半導體"）
5. **絕對禁止**：過於泛用的詞（如：技術、發展、市場、系統、產品）
6. **絕對禁止**：年份、日期或時間相關詞彙
7. 輸出格式必須是JSON數組：["詞1", "詞2", "詞3"]

✅ 良好示例：
- 內容提及"台積電" → 關鍵字包含["台積電"]
- 內容提及"物種演化" → 關鍵字包含["演化", "達爾文"]
- 內容提及"半導體產業" → 關鍵字包含["半導體"]

❌ 錯誤示例：
- 內容講達爾文 → 錯誤生成["半導體"]（完全無關）
- 內容講生物學 → 錯誤生成["人工智慧", "技術"]（不相關）

文本內容：
{text}

請仔細閱讀上述內容，提取**確實出現**在文本中的關鍵字："""


def build_english_keywords_prompt(text: str, n: int = 3) -> str:
    """
    英文關鍵字生成提示詞
    """
    return f"""You are a professional English keyword extraction expert. Please extract {n} most important keywords from the following English content.

⚠️ STRICT REQUIREMENTS:
1. Keywords MUST be **directly present** or **clearly related** to the actual content
2. Use precise English terms (1-4 words max)
3. Priority: Specific proper nouns > Technical terms > Topic concepts  
4. **ABSOLUTELY FORBIDDEN**: Irrelevant terms (e.g., if content is about Darwin, DON'T generate "semiconductor")
5. **ABSOLUTELY FORBIDDEN**: Generic words (technology, development, market, system, product)
6. **ABSOLUTELY FORBIDDEN**: Years, dates, or temporal references
7. Output ONLY JSON format: ["term1", "term2", "term3"]

✅ GOOD Examples:
- Content mentions "TSMC" → keywords include ["TSMC"]  
- Content mentions "species evolution" → keywords include ["evolution", "Darwin"]
- Content mentions "semiconductor industry" → keywords include ["semiconductor"]

❌ BAD Examples:
- Content about Darwin → WRONG to generate ["semiconductor"] (completely unrelated)
- Content about biology → WRONG to generate ["AI", "technology"] (not relevant)

Text content:
{text}

Carefully read the content above and extract keywords that **actually appear** in the text:"""


def build_mixed_keywords_prompt(text: str, n: int = 3) -> str:
    """
    中英混合內容關鍵字生成提示詞
    """
    return f"""你是專業的雙語關鍵字提取專家。請為以下中英文混合內容提取 {n} 個最重要的關鍵字。
You are a professional bilingual keyword extraction expert. Please extract {n} most important keywords from the following mixed Chinese-English content.

⚠️ 嚴格要求 / STRICT REQUIREMENTS:
1. 關鍵字必須**直接出現**在文本中或與內容**密切相關** / Keywords MUST be **directly present** or **clearly related** to actual content
2. 可以是中文詞彙或英文詞彙，選擇最準確的語言 / Use Chinese or English terms, whichever is more precise
3. 優先級：專有名詞 > 技術術語 > 核心概念 / Priority: Proper nouns > Technical terms > Core concepts
4. **絕對禁止**不相關詞彙 / **ABSOLUTELY FORBIDDEN**: Irrelevant terms
5. **絕對禁止**過於泛用的詞 / **ABSOLUTELY FORBIDDEN**: Generic words
6. 輸出格式：JSON數組 / Output format: JSON array ["詞1/term1", "詞2/term2", "詞3/term3"]

✅ 良好示例 / GOOD Examples:
- 內容包含"TSMC台積電" → ["TSMC", "台積電", "半導體"]
- Content contains "人工智慧AI" → ["人工智慧", "AI", "machine learning"]

❌ 錯誤示例 / BAD Examples:  
- 內容講半導體，生成["生物學"] / Content about semiconductors, generating ["biology"]

文本內容 / Text content:
{text}

請提取**確實相關**的關鍵字 / Extract **actually relevant** keywords:"""


def build_auto_keywords_prompt(text: str, n: int = 3) -> str:
    """
    自動檢測語言並生成關鍵字的提示詞
    """
    # 檢測文本主要語言
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    total_chars = chinese_chars + english_chars
    
    if total_chars == 0:
        # 無法檢測，使用英文提示詞
        return build_english_keywords_prompt(text, n)
    
    chinese_ratio = chinese_chars / total_chars
    english_ratio = english_chars / total_chars
    
    if chinese_ratio > 0.6:
        return build_chinese_keywords_prompt(text, n)
    elif english_ratio > 0.6:
        return build_english_keywords_prompt(text, n)
    else:
        return build_mixed_keywords_prompt(text, n)


def build_contextual_keywords_prompt(text: str, context_keywords: List[str] = None, 
                                   n: int = 3, lang: str = "en") -> str:
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
        if lang.lower() in ["zh", "chinese"]:
            context_info = f"\n已知相關關鍵字：{context_list}\n請生成**互補且不重複**的關鍵字。\n"
        else:
            context_info = f"\nExisting related keywords: {context_list}\nGenerate **complementary and non-duplicate** keywords.\n"
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    # 在要求部分插入上下文信息
    if lang.lower() in ["zh", "chinese"]:
        context_section = f"{context_info}特別注意：與已知關鍵字形成主題完整性，但不要重複。"
    else:
        context_section = f"{context_info}Focus on: Terms that complement existing keywords but provide new information."
    
    return base_prompt.replace("要求：", f"要求：\n{context_section}\n原要求：") if "要求：" in base_prompt else \
           base_prompt.replace("Requirements:", f"Requirements:\n{context_section}\nOriginal requirements:")


def build_adaptive_keywords_prompt(text: str, content_type: str = "auto", 
                                 n: int = 3, lang: str = "en") -> str:
    """
    自適應關鍵字生成 - 根據內容類型調整策略
    
    Args:
        content_type: "technical", "business", "academic", "auto"
    """
    
    # 自動檢測內容類型
    if content_type == "auto":
        text_lower = text.lower()
        if any(indicator in text_lower for indicator in ["patent", "algorithm", "specification", "protocol", "display", "semiconductor"]):
            content_type = "technical"
        elif any(indicator in text_lower for indicator in ["market", "revenue", "business", "strategy", "company", "investment"]):
            content_type = "business"  
        elif any(indicator in text_lower for indicator in ["research", "study", "analysis", "methodology", "experiment", "論文", "研究"]):
            content_type = "academic"
        else:
            content_type = "general"
    
    # 根據內容類型調整提示詞
    specialized_instructions = {
        "technical": {
            "zh": "專注於技術規格、產品型號、製程參數、協議標準、專利技術",
            "en": "Focus on technical specs, product models, process parameters, protocol standards, patent technologies"
        },
        "business": {
            "zh": "專注於公司名稱、商業模式、市場策略、產業趨勢、投資相關",
            "en": "Focus on company names, business models, market strategies, industry trends, investment aspects"
        },
        "academic": {
            "zh": "專注於研究方法、理論概念、實驗結果、學術術語、作者姓名",
            "en": "Focus on research methods, theoretical concepts, experimental results, academic terms, author names"
        },
        "general": {
            "zh": "專注於核心主題、關鍵概念、重要實體、主要人物",
            "en": "Focus on core topics, key concepts, important entities, main figures"
        }
    }
    
    lang_key = "zh" if lang.lower() in ["zh", "chinese"] else "en"
    additional_instruction = specialized_instructions[content_type][lang_key]
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    # 插入專門化指令
    if lang.lower() in ["zh", "chinese"]:
        specialized_section = f"內容類型：{content_type.upper()}\n特化要求：{additional_instruction}\n\n"
        return base_prompt.replace("你是一個", f"{specialized_section}你是一個")
    else:
        specialized_section = f"Content type: {content_type.upper()}\nSpecialized focus: {additional_instruction}\n\n"
        return base_prompt.replace("You are a", f"{specialized_section}You are a")


def build_quality_enhanced_keywords_prompt(text: str, quality_score: float = 0.5, 
                                         n: int = 3, lang: str = "en") -> str:
    """
    基於品質分數的增強提示詞
    
    Args:
        quality_score: chunk品質分數 (0-1)
    """
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    if quality_score > 0.8:
        # 高品質chunk，要求更多關鍵字和更高精度
        if lang.lower() in ["zh", "chinese"]:
            enhancement = "\n⭐ 高品質內容檢測：請提取更多專業術語和核心概念，確保關鍵字的專業性和準確性。"
        else:
            enhancement = "\n⭐ High-quality content detected: Extract more professional terms and core concepts, ensure keyword precision and accuracy."
        
        # 增加關鍵字數量
        n_enhanced = min(n + 1, 6)
        base_prompt = base_prompt.replace(f"{n} 個", f"{n_enhanced} 個").replace(f"extract {n}", f"extract {n_enhanced}")
        
    elif quality_score < 0.6:
        # 低品質chunk，專注於基本概念
        if lang.lower() in ["zh", "chinese"]:
            enhancement = "\n⚠️ 內容品質較低：請專注於最基本和最明確的概念，避免複雜或模糊的術語。"
        else:
            enhancement = "\n⚠️ Lower quality content: Focus on most basic and clear concepts, avoid complex or ambiguous terms."
    else:
        enhancement = ""
    
    return base_prompt + enhancement


def build_domain_specific_keywords_prompt(text: str, domain: str = "general", 
                                        n: int = 3, lang: str = "en") -> str:
    """
    領域特定的關鍵字提示詞
    
    Args:
        domain: "medical", "legal", "technology", "finance", "academic", "general"
    """
    
    domain_instructions = {
        "medical": {
            "zh": "醫學領域專用：專注於疾病名稱、藥物名稱、解剖術語、治療方法、醫學概念",
            "en": "Medical domain: Focus on disease names, drug names, anatomical terms, treatment methods, medical concepts"
        },
        "legal": {
            "zh": "法律領域專用：專注於法律條文、案例名稱、法律概念、程序術語、法院判決",
            "en": "Legal domain: Focus on legal provisions, case names, legal concepts, procedural terms, court decisions"
        },
        "technology": {
            "zh": "科技領域專用：專注於技術名稱、產品型號、技術標準、公司名稱、創新概念",
            "en": "Technology domain: Focus on technical names, product models, technical standards, company names, innovation concepts"
        },
        "finance": {
            "zh": "金融領域專用：專注於金融工具、市場術語、公司名稱、投資概念、經濟指標",
            "en": "Finance domain: Focus on financial instruments, market terms, company names, investment concepts, economic indicators"
        },
        "academic": {
            "zh": "學術領域專用：專注於研究主題、作者姓名、理論名稱、方法論、實驗結果",
            "en": "Academic domain: Focus on research topics, author names, theory names, methodologies, experimental results"
        },
        "general": {
            "zh": "通用領域：專注於核心概念、重要實體、關鍵術語",
            "en": "General domain: Focus on core concepts, important entities, key terms"
        }
    }
    
    lang_key = "zh" if lang.lower() in ["zh", "chinese"] else "en"
    domain_instruction = domain_instructions.get(domain, domain_instructions["general"])[lang_key]
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    # 插入領域特定指令
    if lang.lower() in ["zh", "chinese"]:
        domain_section = f"🎯 {domain_instruction}\n\n"
        return base_prompt.replace("你是一個", f"{domain_section}你是一個")
    else:
        domain_section = f"🎯 {domain_instruction}\n\n"
        return base_prompt.replace("You are a", f"{domain_section}You are a")


# ========== 批量處理相關提示詞 ==========

def build_batch_keywords_prompt(chunks: List[dict], n: int = 3, lang: str = "en") -> str:
    """
    批量關鍵字生成的提示詞
    專為批量處理設計，考慮chunks間的關聯性
    """
    
    if lang.lower() in ["zh", "chinese"]:
        prompt = f"""你是專業的批量關鍵字提取專家。請為以下 {len(chunks)} 個文本片段分別生成 {n} 個關鍵字。

⚠️ 批量處理要求：
1. 每個片段的關鍵字必須**獨立且相關**
2. 考慮片段間的主題連貫性，但避免重複
3. 使用準確的中文詞彙
4. 輸出格式：[["片段1關鍵字1", "片段1關鍵字2", ...], ["片段2關鍵字1", ...], ...]

文本片段：
"""
    else:
        prompt = f"""You are a professional batch keyword extraction expert. Please generate {n} keywords for each of the following {len(chunks)} text chunks.

⚠️ Batch processing requirements:
1. Keywords for each chunk must be **independent and relevant**
2. Consider thematic coherence between chunks but avoid duplication
3. Use precise English terms
4. Output format: [["chunk1_kw1", "chunk1_kw2", ...], ["chunk2_kw1", ...], ...]

Text chunks:
"""
    
    for i, chunk in enumerate(chunks):
        text = chunk.get("text", "")[:500]  # 限制長度避免prompt過長
        prompt += f"\n--- 片段 {i+1} / Chunk {i+1} ---\n{text}\n"
    
    if lang.lower() in ["zh", "chinese"]:
        prompt += "\n請為每個片段生成關鍵字："
    else:
        prompt += "\nGenerate keywords for each chunk:"
    
    return prompt


# ========== 錯誤處理和後備提示詞 ==========

def build_fallback_keywords_prompt(text: str, error_context: str = "", 
                                 n: int = 3, lang: str = "en") -> str:
    """
    後備關鍵字生成提示詞（當主要方法失敗時使用）
    """
    
    if lang.lower() in ["zh", "chinese"]:
        return f"""簡化關鍵字提取任務。請為以下內容提取 {n} 個最基本的關鍵字。

注意：之前的處理失敗了（{error_context}），請使用最簡單直接的方法。

要求：
1. 選擇文本中最明顯的名詞或概念
2. 輸出JSON格式：["詞1", "詞2", "詞3"]
3. 如果難以提取，使用通用描述詞

文本：
{text}

簡化關鍵字："""
    
    else:
        return f"""Simplified keyword extraction task. Please extract {n} most basic keywords from the following content.

Note: Previous processing failed ({error_context}), please use the most straightforward approach.

Requirements:
1. Select most obvious nouns or concepts from the text
2. Output JSON format: ["term1", "term2", "term3"]
3. If difficult to extract, use general descriptive terms

Text:
{text}

Simplified keywords:"""


# ========== 測試和驗證函數 ==========

def validate_keywords_prompt_output(output: str, expected_count: int = 3) -> bool:
    """
    驗證關鍵字提示詞輸出格式是否正確
    """
    try:
        import json
        keywords = json.loads(output.strip())
        return isinstance(keywords, list) and len(keywords) <= expected_count * 2
    except:
        return False


if __name__ == "__main__":
    # 測試不同語言的提示詞
    test_text_zh = "台積電是全球最大的半導體代工廠，採用先進的7奈米製程技術。"
    test_text_en = "TSMC is the world's largest semiconductor foundry, using advanced 7nm process technology."
    test_text_mixed = "台積電TSMC使用advanced manufacturing先進製造技術。"
    
    print("=== 中文提示詞測試 ===")
    print(build_chinese_keywords_prompt(test_text_zh, 3))
    
    print("\n=== 英文提示詞測試 ===")  
    print(build_english_keywords_prompt(test_text_en, 3))
    
    print("\n=== 混合語言提示詞測試 ===")
    print(build_mixed_keywords_prompt(test_text_mixed, 3))
    
    print("\n=== 自動檢測提示詞測試 ===")
    print(build_auto_keywords_prompt(test_text_zh, 3))