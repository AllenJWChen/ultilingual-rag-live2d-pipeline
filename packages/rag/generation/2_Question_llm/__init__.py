# -*- coding: utf-8 -*-
"""Question LLM package."""
from .prompts_dataset import build_question_prompt
from .llm_clients import ask_question_llm

__all__ = ["build_question_prompt", "ask_question_llm"]
