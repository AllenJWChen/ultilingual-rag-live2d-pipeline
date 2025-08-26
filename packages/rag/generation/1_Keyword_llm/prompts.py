# -*- coding: utf-8 -*-
"""
增強版語言感知關鍵字提示詞模組 (prompts.py)
🆕 主要新增：完整日文關鍵字生成支援
🔧 主要修復：改善英文關鍵字提示詞精確度

支援語言：中文、英文、日文、混合語言
"""

import re
from typing import List, Optional
from textwrap import dedent


def build_keywords_prompt(text: str, n: int = 3, lang: str = "en") -> str:
    """
    改進版關鍵字生成提示詞 - 支援中英日三語
    
    Args:
        text: 要分析的文字
        n: 需要的關鍵字數量
        lang: 目標語言 ("zh", "en", "ja", "mixed", "auto")
    """
    
    # 根據lang參數選擇合適的提示詞
    if lang.lower() in ["zh", "chinese"]:
        return build_chinese_keywords_prompt(text, n)
    elif lang.lower() in ["en", "english"]:
        return build_english_keywords_prompt(text, n)
    elif lang.lower() in ["ja", "japanese"]:  # 🆕 日文支援
        return build_japanese_keywords_prompt(text, n)
    elif lang.lower() in ["mixed", "bilingual", "multilingual"]:
        return build_mixed_keywords_prompt(text, n)
    else:
        # auto模式：根據文本內容自動選擇
        return build_auto_keywords_prompt(text, n)


def build_chinese_keywords_prompt(text: str, n: int = 3) -> str:
    """中文關鍵字生成提示詞"""
    return dedent(f"""
    你是專業的中文關鍵字提取專家。請為以下中文內容提取 {n} 個最重要的關鍵字。

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

    請仔細閱讀上述內容，提取**確實出現**在文本中的關鍵字：
    """).strip()


def build_english_keywords_prompt(text: str, n: int = 3) -> str:
    """英文關鍵字生成提示詞 - 修復版"""
    return dedent(f"""
    You are a professional English keyword extraction expert. Extract exactly {n} most important keywords from the following English content.

    ⚠️ CRITICAL REQUIREMENTS:
    1. Keywords MUST be **directly present** or **clearly related** to the actual content
    2. Use precise English terms (1-4 words maximum)
    3. Priority: Specific proper nouns > Technical terms > Core concepts
    4. **ABSOLUTELY FORBIDDEN**: Irrelevant terms (e.g., if content is about Darwin, DON'T generate "semiconductor")
    5. **ABSOLUTELY FORBIDDEN**: Generic words (technology, development, market, system, product, important, content)
    6. **ABSOLUTELY FORBIDDEN**: Years, dates, or temporal references
    7. **REQUIRED**: Output ONLY JSON array format: ["term1", "term2", "term3"]

    ✅ EXCELLENT Examples:
    - Content mentions "TSMC" → keywords include ["TSMC"]
    - Content mentions "species evolution" → keywords include ["evolution", "Darwin"]  
    - Content mentions "semiconductor industry" → keywords include ["semiconductor", "industry"]

    ❌ FORBIDDEN Examples:
    - Content about Darwin → WRONG to generate ["semiconductor"] (completely unrelated)
    - Content about biology → WRONG to generate ["AI", "technology"] (irrelevant)

    Text content:
    {text}

    Extract keywords that **actually appear** in the text. Output JSON array only:
    """).strip()


def build_japanese_keywords_prompt(text: str, n: int = 3) -> str:
    """🆕 日文關鍵字生成提示詞"""
    return dedent(f"""
    あなたは専門的な日本語キーワード抽出エキスパートです。以下の日本語コンテンツから最も重要な {n} 個のキーワードを抽出してください。

    ⚠️ 厳格な要求：
    1. キーワードは文章中に**直接現れる**か、内容と**密接に関連**している必要があります
    2. 正確な日本語用語を使用（1-6文字が最適）
    3. 優先順位：固有名詞 > 技術用語 > 核心概念
    4. **絶対禁止**：無関係な用語（例：ダーウィンの内容で「半導体」を生成しない）
    5. **絶対禁止**：汎用的すぎる語（技術、発展、市場、システム、製品）
    6. **絶対禁止**：年、日付、時間関連の語彙
    7. 出力形式はJSON配列である必要があります：["用語1", "用語2", "用語3"]

    ✅ 良い例：
    - 内容に「TSMC」が含まれる → キーワードに["TSMC"]を含む
    - 内容に「種の進化」が含まれる → キーワードに["進化", "ダーウィン"]を含む
    - 内容に「半導体産業」が含まれる → キーワードに["半導体"]を含む

    ❌ 間違った例：
    - ダーウィンの内容 → 間違って["半導体"]を生成（全く無関係）
    - 生物学の内容 → 間違って["AI", "技術"]を生成（関係なし）

    テキスト内容：
    {text}

    上記の内容を注意深く読み、**実際に現れる**キーワードを抽出してください：
    """).strip()


def build_mixed_keywords_prompt(text: str, n: int = 3) -> str:
    """中英日混合内容關鍵字生成提示詞"""
    return dedent(f"""
    あなたは多言語キーワード抽出の専門家です。以下の中英日混合コンテンツから最も重要な {n} 個のキーワードを抽出してください。
    You are a professional multilingual keyword extraction expert. Extract {n} most important keywords from the following mixed Chinese-English-Japanese content.
    你是專業的多語言關鍵字提取專家。請為以下中英日混合內容提取 {n} 個最重要的關鍵字。

    ⚠️ 嚴格要求 / STRICT REQUIREMENTS / 厳格な要求：
    1. 關鍵字必須**直接出現**在文本中或與內容**密切相關** / Keywords MUST be **directly present** or **clearly related** / キーワードは**直接現れる**か**密接に関連**している必要があります
    2. 可使用中文、英文或日文詞彙，選擇最準確的語言 / Use Chinese, English, or Japanese terms, whichever is most precise / 中国語、英語、日本語の用語を使用し、最も正確な言語を選択
    3. 優先級：專有名詞 > 技術術語 > 核心概念 / Priority: Proper nouns > Technical terms > Core concepts / 優先順位：固有名詞 > 技術用語 > 核心概念
    4. **絕對禁止**不相關詞彙 / **ABSOLUTELY FORBIDDEN**: Irrelevant terms / **絶対禁止**：無関係な用語
    5. **絕對禁止**過於泛用的詞 / **ABSOLUTELY FORBIDDEN**: Generic words / **絶対禁止**：汎用的すぎる語
    6. 輸出格式：JSON數組 / Output format: JSON array / 出力形式：JSON配列 ["詞1/term1/用語1", "詞2/term2/用語2", "詞3/term3/用語3"]

    ✅ 良好示例 / GOOD Examples / 良い例：
    - 內容包含"TSMC台積電" → ["TSMC", "台積電", "半導体"]
    - Content contains "人工智慧AI" → ["人工智慧", "AI", "machine learning"]
    - コンテンツに"DisplayディスプレイCES"が含まれる → ["Display", "ディスプレイ", "CES"]

    ❌ 錯誤示例 / BAD Examples / 間違った例：
    - 內容講半導體，生成["生物学"] / Content about semiconductors, generating ["biology"] / 半導体の内容で["生物学"]を生成

    文本內容 / Text content / テキスト内容：
    {text}

    請提取**確實相關**的關鍵字 / Extract **actually relevant** keywords / **実際に関連する**キーワードを抽出：
    """).strip()


def build_auto_keywords_prompt(text: str, n: int = 3) -> str:
    """自動檢測語言並生成關鍵字的提示詞 - 支援日文"""
    # 檢測文本主要語言
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    english_chars = len(re.findall(r'[a-zA-Z]', text))
    japanese_chars = len(re.findall(r'[\u3040-\u309f\u30a0-\u30ff]', text))  # 平假名+片假名
    total_chars = chinese_chars + english_chars + japanese_chars
    
    if total_chars == 0:
        # 無法檢測，使用英文提示詞
        return build_english_keywords_prompt(text, n)
    
    chinese_ratio = chinese_chars / total_chars
    english_ratio = english_chars / total_chars
    japanese_ratio = japanese_chars / total_chars
    
    # 日文優先檢測
    if japanese_ratio > 0.2:
        return build_japanese_keywords_prompt(text, n)
    elif chinese_ratio > 0.6:
        return build_chinese_keywords_prompt(text, n)
    elif english_ratio > 0.6:
        return build_english_keywords_prompt(text, n)
    else:
        return build_mixed_keywords_prompt(text, n)


def build_contextual_keywords_prompt(text: str, context_keywords: List[str] = None, 
                                   n: int = 3, lang: str = "en") -> str:
    """
    上下文感知的關鍵字生成 - 支援中英日三語
    
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
        elif lang.lower() in ["ja", "japanese"]:
            context_info = f"\n既知の関連キーワード：{context_list}\n**補完的で重複しない**キーワードを生成してください。\n"
        else:
            context_info = f"\nExisting related keywords: {context_list}\nGenerate **complementary and non-duplicate** keywords.\n"
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    # 在要求部分插入上下文信息
    if lang.lower() in ["zh", "chinese"]:
        context_section = f"{context_info}特別注意：與已知關鍵字形成主題完整性，但不要重複。"
    elif lang.lower() in ["ja", "japanese"]:
        context_section = f"{context_info}特別注意：既知のキーワードと主題の整合性を保ちながら、重複を避ける。"
    else:
        context_section = f"{context_info}Focus on: Terms that complement existing keywords but provide new information."
    
    return base_prompt.replace("要求：", f"要求：\n{context_section}\n原要求：") if "要求：" in base_prompt else \
           base_prompt.replace("厳格な要求：", f"厳格な要求：\n{context_section}\n元の要求：") if "厳格な要求：" in base_prompt else \
           base_prompt.replace("Requirements:", f"Requirements:\n{context_section}\nOriginal requirements:")


def build_adaptive_keywords_prompt(text: str, content_type: str = "auto", 
                                 n: int = 3, lang: str = "en") -> str:
    """
    自適應關鍵字生成 - 根據內容類型調整策略，支援日文
    
    Args:
        content_type: "technical", "business", "academic", "auto"
    """
    
    # 自動檢測內容類型
    if content_type == "auto":
        text_lower = text.lower()
        japanese_text = text  # 保持原文用於日文檢測
        
        tech_indicators = ["patent", "algorithm", "specification", "protocol", "display", "semiconductor", "特許", "アルゴリズム", "仕様", "プロトコル", "ディスプレイ", "半導体"]
        business_indicators = ["market", "revenue", "business", "strategy", "company", "investment", "市場", "収益", "ビジネス", "戦略", "会社", "投資"]
        academic_indicators = ["research", "study", "analysis", "methodology", "experiment", "研究", "分析", "方法論", "実験", "論文"]
        
        if any(indicator in text_lower or indicator in japanese_text for indicator in tech_indicators):
            content_type = "technical"
        elif any(indicator in text_lower or indicator in japanese_text for indicator in business_indicators):
            content_type = "business"  
        elif any(indicator in text_lower or indicator in japanese_text for indicator in academic_indicators):
            content_type = "academic"
        else:
            content_type = "general"
    
    # 根據內容類型調整提示詞
    specialized_instructions = {
        "technical": {
            "zh": "專注於技術規格、產品型號、製程參數、協議標準、專利技術",
            "en": "Focus on technical specs, product models, process parameters, protocol standards, patent technologies",
            "ja": "技術仕様、製品モデル、プロセスパラメータ、プロトコル標準、特許技術に焦点を当てる"
        },
        "business": {
            "zh": "專注於公司名稱、商業模式、市場策略、產業趨勢、投資相關",
            "en": "Focus on company names, business models, market strategies, industry trends, investment aspects",
            "ja": "会社名、ビジネスモデル、市場戦略、業界トレンド、投資関連に焦点を当てる"
        },
        "academic": {
            "zh": "專注於研究方法、理論概念、實驗結果、學術術語、作者姓名",
            "en": "Focus on research methods, theoretical concepts, experimental results, academic terms, author names",
            "ja": "研究方法、理論概念、実験結果、学術用語、著者名に焦点を当てる"
        },
        "general": {
            "zh": "專注於核心主題、關鍵概念、重要實體、主要人物",
            "en": "Focus on core topics, key concepts, important entities, main figures",
            "ja": "核心主題、重要概念、重要な実体、主要人物に焦点を当てる"
        }
    }
    
    lang_key = "ja" if lang.lower() in ["ja", "japanese"] else ("zh" if lang.lower() in ["zh", "chinese"] else "en")
    additional_instruction = specialized_instructions[content_type][lang_key]
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    # 插入專門化指令
    if lang.lower() in ["zh", "chinese"]:
        specialized_section = f"內容類型：{content_type.upper()}\n特化要求：{additional_instruction}\n\n"
        return base_prompt.replace("你是一個", f"{specialized_section}你是一個")
    elif lang.lower() in ["ja", "japanese"]:
        specialized_section = f"コンテンツタイプ：{content_type.upper()}\n特化要求：{additional_instruction}\n\n"
        return base_prompt.replace("あなたは", f"{specialized_section}あなたは")
    else:
        specialized_section = f"Content type: {content_type.upper()}\nSpecialized focus: {additional_instruction}\n\n"
        return base_prompt.replace("You are a", f"{specialized_section}You are a")


def build_quality_enhanced_keywords_prompt(text: str, quality_score: float = 0.5, 
                                         n: int = 3, lang: str = "en") -> str:
    """
    基於品質分數的增強提示詞 - 支援日文
    
    Args:
        quality_score: chunk品質分數 (0-1)
    """
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    if quality_score > 0.8:
        # 高品質chunk，要求更多關鍵字和更高精度
        if lang.lower() in ["zh", "chinese"]:
            enhancement = "\n⭐ 高品質內容檢測：請提取更多專業術語和核心概念，確保關鍵字的專業性和準確性。"
        elif lang.lower() in ["ja", "japanese"]:
            enhancement = "\n⭐ 高品質コンテンツ検出：より多くの専門用語と核心概念を抽出し、キーワードの専門性と正確性を確保してください。"
        else:
            enhancement = "\n⭐ High-quality content detected: Extract more professional terms and core concepts, ensure keyword precision and accuracy."
        
        # 增加關鍵字數量
        n_enhanced = min(n + 1, 6)
        base_prompt = base_prompt.replace(f"{n} 個", f"{n_enhanced} 個").replace(f"extract {n}", f"extract {n_enhanced}").replace(f"{n} 個の", f"{n_enhanced} 個の")
        
    elif quality_score < 0.6:
        # 低品質chunk，專注於基本概念
        if lang.lower() in ["zh", "chinese"]:
            enhancement = "\n⚠️ 內容品質較低：請專注於最基本和最明確的概念，避免複雜或模糊的術語。"
        elif lang.lower() in ["ja", "japanese"]:
            enhancement = "\n⚠️ コンテンツ品質が低い：最も基本的で明確な概念に焦点を当て、複雑または曖昧な用語を避けてください。"
        else:
            enhancement = "\n⚠️ Lower quality content: Focus on most basic and clear concepts, avoid complex or ambiguous terms."
    else:
        enhancement = ""
    
    return base_prompt + enhancement


def build_domain_specific_keywords_prompt(text: str, domain: str = "general", 
                                        n: int = 3, lang: str = "en") -> str:
    """
    領域特定的關鍵字提示詞 - 支援日文
    
    Args:
        domain: "medical", "legal", "technology", "finance", "academic", "general"
    """
    
    domain_instructions = {
        "medical": {
            "zh": "醫學領域專用：專注於疾病名稱、藥物名稱、解剖術語、治療方法、醫學概念",
            "en": "Medical domain: Focus on disease names, drug names, anatomical terms, treatment methods, medical concepts",
            "ja": "医学領域専用：疾患名、薬剤名、解剖学用語、治療方法、医学概念に焦点を当てる"
        },
        "legal": {
            "zh": "法律領域專用：專注於法律條文、案例名稱、法律概念、程序術語、法院判決",
            "en": "Legal domain: Focus on legal provisions, case names, legal concepts, procedural terms, court decisions",
            "ja": "法律領域専用：法律条文、判例名、法的概念、手続き用語、裁判所判決に焦点を当てる"
        },
        "technology": {
            "zh": "科技領域專用：專注於技術名稱、產品型號、技術標準、公司名稱、創新概念",
            "en": "Technology domain: Focus on technical names, product models, technical standards, company names, innovation concepts",
            "ja": "技術領域専用：技術名称、製品モデル、技術標準、会社名、革新概念に焦点を当てる"
        },
        "finance": {
            "zh": "金融領域專用：專注於金融工具、市場術語、公司名稱、投資概念、經濟指標",
            "en": "Finance domain: Focus on financial instruments, market terms, company names, investment concepts, economic indicators",
            "ja": "金融領域専用：金融商品、市場用語、会社名、投資概念、経済指標に焦点を当てる"
        },
        "academic": {
            "zh": "學術領域專用：專注於研究主題、作者姓名、理論名稱、方法論、實驗結果",
            "en": "Academic domain: Focus on research topics, author names, theory names, methodologies, experimental results",
            "ja": "学術領域専用：研究主題、著者名、理論名、方法論、実験結果に焦点を当てる"
        },
        "general": {
            "zh": "通用領域：專注於核心概念、重要實體、關鍵術語",
            "en": "General domain: Focus on core concepts, important entities, key terms",
            "ja": "一般領域：核心概念、重要な実体、重要用語に焦点を当てる"
        }
    }
    
    lang_key = "ja" if lang.lower() in ["ja", "japanese"] else ("zh" if lang.lower() in ["zh", "chinese"] else "en")
    domain_instruction = domain_instructions.get(domain, domain_instructions["general"])[lang_key]
    
    base_prompt = build_keywords_prompt(text, n, lang)
    
    # 插入領域特定指令
    if lang.lower() in ["zh", "chinese"]:
        domain_section = f"🎯 {domain_instruction}\n\n"
        return base_prompt.replace("你是一個", f"{domain_section}你是一個")
    elif lang.lower() in ["ja", "japanese"]:
        domain_section = f"🎯 {domain_instruction}\n\n"
        return base_prompt.replace("あなたは", f"{domain_section}あなたは")
    else:
        domain_section = f"🎯 {domain_instruction}\n\n"
        return base_prompt.replace("You are a", f"{domain_section}You are a")


# ========== 批量處理相關提示詞 ==========

def build_batch_keywords_prompt(chunks: List[dict], n: int = 3, lang: str = "en") -> str:
    """
    批量關鍵字生成的提示詞 - 支援日文
    專為批量處理設計，考慮chunks間的關聯性
    """
    
    if lang.lower() in ["zh", "chinese"]:
        prompt_header = f"你是專業的批量關鍵字提取專家。請為以下 {len(chunks)} 個文本片段分別生成 {n} 個關鍵字。"
        requirements = """
⚠️ 批量處理要求：
1. 每個片段的關鍵字必須**獨立且相關**
2. 考慮片段間的主題連貫性，但避免重複
3. 使用準確的中文詞彙
4. 輸出格式：[["片段1關鍵字1", "片段1關鍵字2", ...], ["片段2關鍵字1", ...], ...]

文本片段：
"""
        footer = "\n請為每個片段生成關鍵字："
    elif lang.lower() in ["ja", "japanese"]:
        prompt_header = f"あなたは専門的な一括キーワード抽出エキスパートです。以下の {len(chunks)} 個のテキスト断片に対して、それぞれ {n} 個のキーワードを生成してください。"
        requirements = """
⚠️ 一括処理要求：
1. 各断片のキーワードは**独立して関連性**がある必要があります
2. 断片間の主題の一貫性を考慮しつつ、重複を避けてください
3. 正確な日本語用語を使用してください
4. 出力形式：[["断片1キーワード1", "断片1キーワード2", ...], ["断片2キーワード1", ...], ...]

テキスト断片：
"""
        footer = "\n各断片のキーワードを生成してください："
    else:
        prompt_header = f"You are a professional batch keyword extraction expert. Please generate {n} keywords for each of the following {len(chunks)} text chunks."
        requirements = """
⚠️ Batch processing requirements:
1. Keywords for each chunk must be **independent and relevant**
2. Consider thematic coherence between chunks but avoid duplication
3. Use precise terms
4. Output format: [["chunk1_kw1", "chunk1_kw2", ...], ["chunk2_kw1", ...], ...]

Text chunks:
"""
        footer = "\nGenerate keywords for each chunk:"
    
    prompt = prompt_header + requirements
    
    for i, chunk in enumerate(chunks):
        text = chunk.get("text", "")[:500]  # 限制長度避免prompt過長
        if lang.lower() in ["zh", "chinese"]:
            prompt += f"\n--- 片段 {i+1} ---\n{text}\n"
        elif lang.lower() in ["ja", "japanese"]:
            prompt += f"\n--- 断片 {i+1} ---\n{text}\n"
        else:
            prompt += f"\n--- Chunk {i+1} ---\n{text}\n"
    
    prompt += footer
    return prompt


# ========== 錯誤處理和後備提示詞 ==========

def build_fallback_keywords_prompt(text: str, error_context: str = "", 
                                 n: int = 3, lang: str = "en") -> str:
    """
    後備關鍵字生成提示詞 - 支援日文
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
    
    elif lang.lower() in ["ja", "japanese"]:
        return f"""簡素化キーワード抽出タスク。以下の内容から最も基本的な {n} 個のキーワードを抽出してください。

注意：前の処理が失敗しました（{error_context}）。最も簡単で直接的な方法を使用してください。

要求：
1. テキスト中の最も明白な名詞または概念を選択
2. JSON形式で出力：["用語1", "用語2", "用語3"]
3. 抽出が困難な場合は、一般的な記述語を使用

テキスト：
{text}

簡素化キーワード："""
    
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
    """驗證關鍵字提示詞輸出格式是否正確"""
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
    test_text_ja = "TSMCは世界最大の半導体ファウンドリで、先進的な7nmプロセス技術を使用しています。"
    test_text_mixed = "台積電TSMC半導体ファウンドリusing advanced manufacturing先進製造技術。"
    
    print("=== 中文提示詞測試 ===")
    print(build_chinese_keywords_prompt(test_text_zh, 3))
    
    print("\n=== 英文提示詞測試 ===")  
    print(build_english_keywords_prompt(test_text_en, 3))
    
    print("\n=== 日文提示詞測試 ===")
    print(build_japanese_keywords_prompt(test_text_ja, 3))
    
    print("\n=== 混合語言提示詞測試 ===")
    print(build_mixed_keywords_prompt(test_text_mixed, 3))
    
    print("\n=== 自動檢測提示詞測試 ===")
    print(build_auto_keywords_prompt(test_text_ja, 3))