# -*- coding: utf-8 -*-
"""Question LLM package."""

# prompts_dataset 在目前專案中不是必需；讓它成為可選，避免封包 import 失敗
try:
    from .prompts_dataset import build_question_prompt  # optional
except Exception:
    build_question_prompt = None  # 提供佔位，保相容性

from .clients import ask_question_llm  # 問題生成用的客戶端

__all__ = ["build_question_prompt", "ask_question_llm"]
