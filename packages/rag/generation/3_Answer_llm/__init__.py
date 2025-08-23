"""
Answer LLM 模組
簡潔的檔名設計 - 路徑即文檔
"""

from .prompts import build_answer_prompt, build_critique_prompt
from .clients import ask_answer_llm, get_llm_client
from .core import AnswerGenerator, process_questions_file, main as core_main
from .core_parallel import HighPerformanceAnswerGenerator, parallel_answer_generation, main as parallel_main

__all__ = [
    # 提示詞
    "build_answer_prompt",
    "build_critique_prompt", 
    
    # LLM 客戶端
    "ask_answer_llm",
    "get_llm_client",
    
    # 基礎版本
    "AnswerGenerator",
    "process_questions_file",
    "core_main",
    
    # 高性能並行版本
    "HighPerformanceAnswerGenerator",
    "parallel_answer_generation", 
    "parallel_main",
]