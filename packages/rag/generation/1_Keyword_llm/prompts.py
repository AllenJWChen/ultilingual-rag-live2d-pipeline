# -*- coding: utf-8 -*-
from __future__ import annotations
from textwrap import dedent

def build_keywords_prompt(text: str, n: int = 3, lang: str = "en") -> str:
    """
    建立關鍵字擷取 prompt。
    預設用英文關鍵字（跨語檢索較穩），如需中文可把 lang 改成 "zh"。
    """
    if lang.lower() == "zh":
        return dedent(f"""
        從下列文字中抽取 {n} 個最關鍵的「術語/名詞/主題」。請只輸出 JSON 陣列（字串），不得多餘說明。
        只用中文詞彙，每個關鍵字 1~4 個字詞。

        文字：
        {text}
        """).strip()

    # 預設 English keywords
    return dedent(f"""
    Extract {n} domain-specific keywords (nouns or short phrases) from the text below.
    Return ONLY a JSON array of strings (no explanations). Use concise English (1–3 words).

    Text:
    {text}
    """).strip()
