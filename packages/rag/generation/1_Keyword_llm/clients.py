# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from typing import List

# 環境變數：
#   LLM_MODE: "OPENAI_COMPAT" | "MOCK"  （預設 OPENAI_COMPAT）
#   OPENAI_BASE_URL: 例如 "http://localhost:11434/v1" （Ollama OpenAI 相容端點）
#   OPENAI_API_KEY: 例如 "ollama" （Ollama 會忽略但必填）
#   MODEL_KEYWORDS: 例如 "llama3.1:latest"

LLM_MODE = os.getenv("LLM_MODE", "OPENAI_COMPAT").upper().strip()
MODEL_KEYWORDS = os.getenv("MODEL_KEYWORDS", "llama3.1:latest")

# -------------- 共用：清理/截斷關鍵字 --------------
def _postprocess_keywords(raw_items: List[str], n: int) -> List[str]:
    cleaned: List[str] = []
    for k in raw_items:
        k = k.strip().strip("，,;、.。:：-—\"'「」『』()（）[]【】")
        # 過濾空字串 / 太短符號片段
        if not k or re.fullmatch(r"[\W_]+", k):
            continue
        # 去重（保留順序）
        if k not in cleaned:
            cleaned.append(k)
    return cleaned[:max(1, n)]

def _split_keywords(s: str) -> List[str]:
    # 常見分隔符：逗號 / 頓號 / 分號 / 換行
    parts = re.split(r"[,\n，、;；]+", s)
    return [p.strip() for p in parts if p.strip()]

# -------------- MOCK 模式（本地不調 LLM） --------------
def _generate_keywords_mock(text: str, n: int, lang: str) -> List[str]:
    # 粗略以詞頻取前幾個：中英文皆可用（非常簡單的 fallback）
    tokens = re.findall(r"[\u4e00-\u9fff]{1,6}|[A-Za-z][A-Za-z0-9_\-]{1,30}", text)
    freq = {}
    for t in tokens:
        # 忽略過短
        if len(t) < 2:
            continue
        freq[t] = freq.get(t, 0) + 1
    # 依頻次排序
    cand = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[: max(10, n)]
    return _postprocess_keywords([w for w, _ in cand], n)

# -------------- OpenAI-compatible（Ollama 等） --------------
def _generate_keywords_openai_compat(text: str, n: int, lang: str) -> List[str]:
    try:
        # OpenAI Python SDK（與 Ollama 的 /v1/chat/completions 相容）
        from openai import OpenAI
        client = OpenAI(
            base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
            api_key=os.getenv("OPENAI_API_KEY", "ollama"),
        )
    except Exception as e:
        # 若套件缺失就退回 MOCK
        return _generate_keywords_mock(text, n, lang)

    lang_part = "中文" if lang.lower() in ("zh", "zh-tw", "zh-cn") else "English"

    prompt = (
        f"請從下面內容萃取 **{n} 個**最能代表主題的關鍵字，語言使用：{lang_part}。\n"
        "只輸出以逗號分隔的關鍵字清單，**不要**解釋、不要加任何其他文字。\n"
        "--- 內容開始 ---\n"
        f"{text[:1600]}\n"
        "--- 內容結束 ---"
    )

    resp = client.chat.completions.create(
        model=MODEL_KEYWORDS,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=128,
    )
    out = resp.choices[0].message.content.strip()
    items = _split_keywords(out)
    return _postprocess_keywords(items, n)

# -------------- 外部呼叫介面 --------------
def generate_keywords(text: str, n: int = 3, lang: str = "auto") -> List[str]:
    """
    產出 n 個關鍵字（list[str]），根據 LLM_MODE 決定是
    - OPENAI_COMPAT：走 OpenAI 相容 API（例如 Ollama）
    - MOCK：本地簡單詞頻 fallback
    """
    if not text or not text.strip():
        return []

    mode = LLM_MODE
    if mode == "MOCK":
        return _generate_keywords_mock(text, n, lang)

    # 預設走 OPENAI_COMPAT
    try:
        return _generate_keywords_openai_compat(text, n, lang)
    except Exception:
        # 任意錯誤 fallback
        return _generate_keywords_mock(text, n, lang)

__all__ = ["generate_keywords"]
