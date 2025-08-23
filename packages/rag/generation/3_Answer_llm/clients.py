#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Answer LLM Clients - 相容您現有的 llm_clients.py 架構

提供與您的 Question LLM 相同的介面設計
支援 MOCK 和 OPENAI_COMPAT 模式
"""

import os
import json
from typing import Dict, Any, Optional

# 環境變數 - 沿用您的設計
LLM_MODE = os.getenv("LLM_MODE", "OPENAI_COMPAT").upper().strip()
BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
API_KEY = os.getenv("OPENAI_API_KEY", "sk-mock")
MODEL_ANSWER = os.getenv("MODEL_ANSWER", os.getenv("MODEL_QUESTION", "llama3.1:8b-instruct"))

try:
    import httpx  # 與您的實作保持一致
except Exception:
    httpx = None  # type: ignore

def _mock_answer_payload(question: str, language: str = "zh") -> str:
    """回傳 MOCK 模式的答案"""
    if language.lower() in ['zh', 'chinese', '中文']:
        mock_answer = f"根據提供的文件內容，針對問題「{question}」，我的回答是：這是一個測試回答，用於驗證系統流程。文件中提及的相關資訊包括技術細節、應用場景和實作方法等內容。"
    else:
        mock_answer = f"Based on the provided document content, regarding the question '{question}', my answer is: This is a test response to verify the system workflow. The relevant information mentioned in the document includes technical details, application scenarios, and implementation methods."
    
    return mock_answer

def ask_answer_llm(prompt: str, question: str = "", language: str = "zh") -> str:
    """
    呼叫 Answer LLM 生成答案
    
    Args:
        prompt: 完整的提示詞 (包含 context + question)
        question: 問題文本 (用於 MOCK 模式)
        language: 回答語言
        
    Returns:
        答案文本
    """
    if LLM_MODE == "MOCK":
        return _mock_answer_payload(question, language)

    if httpx is None:
        raise RuntimeError("Please `pip install httpx` or set LLM_MODE=MOCK to test without HTTP calls.")

    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {
        "model": MODEL_ANSWER,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,  # 稍微提高創造性
        "max_tokens": 600    # 答案可以稍微長一些
    }
    
    resp = httpx.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# 提供與您的架構一致的介面
class LLMClient:
    """LLM Client 類別 - 提供統一介面"""
    
    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or MODEL_ANSWER
        
    def generate(self, prompt: str, max_tokens: int = 600, temperature: float = 0.3, **kwargs) -> Dict[str, Any]:
        """
        生成回答 - 與您的 AnswerGenerator 介面相容
        
        Returns:
            Dict with 'text' key containing the generated answer
        """
        question = kwargs.get('question', '')
        language = kwargs.get('language', 'zh')
        
        try:
            answer_text = ask_answer_llm(prompt, question, language)
            return {
                'text': answer_text,
                'model': self.model_name,
                'success': True
            }
        except Exception as e:
            return {
                'text': f"生成答案時發生錯誤: {str(e)}",
                'model': self.model_name,
                'success': False,
                'error': str(e)
            }

def get_llm_client(model_name: Optional[str] = None) -> LLMClient:
    """獲取 LLM 客戶端 - 統一入口點"""
    return LLMClient(model_name)

# 向後相容性
def generate_answer(prompt: str, question: str = "", language: str = "zh") -> str:
    """向後相容的答案生成函數"""
    return ask_answer_llm(prompt, question, language)

__all__ = [
    "ask_answer_llm", 
    "get_llm_client", 
    "LLMClient", 
    "generate_answer"
]