#!/usr/bin/env python3
"""
prompts_answer.py - Answer LLM 提示詞模組

根據不同語言和問題類型，建構適當的提示詞來生成高品質答案
"""

from typing import List, Dict, Any

def build_answer_prompt(question: str, chunks: List[Dict[str, Any]], language: str = "zh") -> str:
    """
    建構回答問題的提示詞
    
    Args:
        question: 要回答的問題
        chunks: 相關的文件片段列表
        language: 目標語言 ('zh', 'en')
        
    Returns:
        完整的提示詞字串
    """
    
    if language.lower() in ['zh', 'chinese', '中文']:
        return build_chinese_answer_prompt(question, chunks)
    else:
        return build_english_answer_prompt(question, chunks)

def build_chinese_answer_prompt(question: str, chunks: List[Dict[str, Any]]) -> str:
    """建構中文回答提示詞"""
    
    # 建構文件內容部分
    context_parts = []
    for i, chunk in enumerate(chunks):
        source = chunk.get('source', 'Unknown')
        page = chunk.get('page', 'N/A')
        text = chunk.get('text', '')
        
        context_parts.append(f"""文件 {i+1} (來源: {source}, 第{page}頁):
{text}""")
    
    context_text = "\n\n".join(context_parts)
    
    prompt = f"""你是一位專業的技術文件分析專家。請根據提供的文件內容，準確回答用戶的問題。

## 回答指引
1. **必須基於提供的文件內容回答**，不要編造資訊
2. **明確引用來源**，使用「根據文件X」或「文件中提到」等表達
3. **保持客觀準確**，如果文件中沒有相關資訊，請明確說明
4. **結構清晰**，使用適當的段落和條列
5. **語言自然**，避免生硬的翻譯腔

## 提供的文件內容

{context_text}

## 用戶問題
{question}

## 請回答
請基於上述文件內容回答問題。如果文件中沒有足夠資訊回答，請說明「文件中未提及相關資訊」。

回答："""

    return prompt

def build_english_answer_prompt(question: str, chunks: List[Dict[str, Any]]) -> str:
    """建構英文回答提示詞"""
    
    # 建構文件內容部分
    context_parts = []
    for i, chunk in enumerate(chunks):
        source = chunk.get('source', 'Unknown')
        page = chunk.get('page', 'N/A')
        text = chunk.get('text', '')
        
        context_parts.append(f"""Document {i+1} (Source: {source}, Page {page}):
{text}""")
    
    context_text = "\n\n".join(context_parts)
    
    prompt = f"""You are a professional technical document analyst. Please answer the user's question accurately based on the provided document content.

## Answer Guidelines
1. **Base your answer strictly on the provided documents** - do not fabricate information
2. **Cite sources clearly** using phrases like "According to Document X" or "As mentioned in the documents"
3. **Maintain objectivity** - if information is not available in the documents, state this clearly
4. **Structure clearly** with appropriate paragraphs and bullet points
5. **Use natural language** that is easy to understand

## Provided Documents

{context_text}

## User Question
{question}

## Your Answer
Please answer the question based on the above documents. If there is insufficient information in the documents, please state "The information is not mentioned in the provided documents."

Answer:"""

    return prompt

def build_critique_prompt(question: str, answer: str, chunks: List[Dict[str, Any]], language: str = "zh") -> str:
    """
    建構評估答案品質的提示詞
    用於 Critique_LLM 模組
    """
    
    if language.lower() in ['zh', 'chinese', '中文']:
        return build_chinese_critique_prompt(question, answer, chunks)
    else:
        return build_english_critique_prompt(question, answer, chunks)

def build_chinese_critique_prompt(question: str, answer: str, chunks: List[Dict[str, Any]]) -> str:
    """建構中文答案評估提示詞"""
    
    context_text = "\n".join([f"文件{i+1}: {chunk.get('text', '')}" for i, chunk in enumerate(chunks)])
    
    prompt = f"""你是一位嚴格的答案品質評估專家。請評估提供的答案品質。

## 評估標準 (每項1-5分)
1. **相關性 (Relevance)**: 答案是否直接回答了問題
2. **基於文件 (Groundedness)**: 答案是否基於提供的文件內容
3. **獨立性 (Standalone)**: 答案是否可以獨立理解，不需要額外上下文
4. **準確性 (Accuracy)**: 答案中的資訊是否準確無誤

## 提供的文件
{context_text}

## 問題
{question}

## 待評估的答案
{answer}

## 請評估
請對每個標準給出1-5分的評分，並提供簡短說明。總分需達到13分以上才算合格。

輸出格式：
```json
{{
    "relevance": 4,
    "groundedness": 5,
    "standalone": 4,
    "accuracy": 4,
    "total_score": 17,
    "pass": true,
    "comments": "答案完整回答了問題，基於文件內容，表達清晰。"
}}
```"""

    return prompt

def build_english_critique_prompt(question: str, answer: str, chunks: List[Dict[str, Any]]) -> str:
    """建構英文答案評估提示詞"""
    
    context_text = "\n".join([f"Document {i+1}: {chunk.get('text', '')}" for i, chunk in enumerate(chunks)])
    
    prompt = f"""You are a strict answer quality evaluator. Please assess the quality of the provided answer.

## Evaluation Criteria (1-5 points each)
1. **Relevance**: Does the answer directly address the question?
2. **Groundedness**: Is the answer based on the provided documents?
3. **Standalone**: Can the answer be understood independently without additional context?
4. **Accuracy**: Is the information in the answer factually correct?

## Provided Documents
{context_text}

## Question
{question}

## Answer to Evaluate
{answer}

## Please Evaluate
Give a score of 1-5 for each criterion with brief explanation. Total score must be 13+ to pass.

Output format:
```json
{{
    "relevance": 4,
    "groundedness": 5,
    "standalone": 4,
    "accuracy": 4,
    "total_score": 17,
    "pass": true,
    "comments": "The answer comprehensively addresses the question, is grounded in documents, and clearly expressed."
}}
```"""

    return prompt

# 專門針對不同問題類型的提示詞變體
def build_specialized_prompt(question: str, chunks: List[Dict[str, Any]], 
                           question_type: str, language: str = "zh") -> str:
    """
    根據問題類型建構專門的提示詞
    
    Args:
        question_type: 問題類型 ('summary', 'factual', 'comparison', 'analysis')
    """
    
    if question_type == "summary":
        return build_summary_prompt(question, chunks, language)
    elif question_type == "factual":
        return build_factual_prompt(question, chunks, language)
    elif question_type == "comparison":
        return build_comparison_prompt(question, chunks, language)
    elif question_type == "analysis":
        return build_analysis_prompt(question, chunks, language)
    else:
        return build_answer_prompt(question, chunks, language)

def build_summary_prompt(question: str, chunks: List[Dict[str, Any]], language: str = "zh") -> str:
    """摘要類問題的專門提示詞"""
    base_prompt = build_answer_prompt(question, chunks, language)
    
    if language.lower() in ['zh', 'chinese', '中文']:
        addition = "\n\n特別注意：這是一個摘要問題，請提供簡潔但全面的總結，突出重點資訊。"
    else:
        addition = "\n\nSpecial Note: This is a summary question. Please provide a concise but comprehensive summary highlighting key information."
    
    return base_prompt + addition

def build_factual_prompt(question: str, chunks: List[Dict[str, Any]], language: str = "zh") -> str:
    """事實類問題的專門提示詞"""
    base_prompt = build_answer_prompt(question, chunks, language)
    
    if language.lower() in ['zh', 'chinese', '中文']:
        addition = "\n\n特別注意：這是一個事實查詢問題，請提供準確的具體資訊，包括數據、名稱、日期等。"
    else:
        addition = "\n\nSpecial Note: This is a factual query. Please provide accurate specific information including data, names, dates, etc."
    
    return base_prompt + addition

def build_comparison_prompt(question: str, chunks: List[Dict[str, Any]], language: str = "zh") -> str:
    """比較類問題的專門提示詞"""
    base_prompt = build_answer_prompt(question, chunks, language)
    
    if language.lower() in ['zh', 'chinese', '中文']:
        addition = "\n\n特別注意：這是一個比較問題，請清楚地對比不同項目的特點、優缺點或差異。"
    else:
        addition = "\n\nSpecial Note: This is a comparison question. Please clearly contrast the features, pros/cons, or differences between items."
    
    return base_prompt + addition

def build_analysis_prompt(question: str, chunks: List[Dict[str, Any]], language: str = "zh") -> str:
    """分析類問題的專門提示詞"""
    base_prompt = build_answer_prompt(question, chunks, language)
    
    if language.lower() in ['zh', 'chinese', '中文']:
        addition = "\n\n特別注意：這是一個分析問題，請提供深入的洞察，包括原因、影響、趨勢或建議。"
    else:
        addition = "\n\nSpecial Note: This is an analysis question. Please provide in-depth insights including causes, impacts, trends, or recommendations."
    
    return base_prompt + addition