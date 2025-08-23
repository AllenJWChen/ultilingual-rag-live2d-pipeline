#!/usr/bin/env python3
"""
Answer LLM 核心模組
"""

import json
import os
import argparse
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

# 修正後的 Import 路徑
from .clients import get_llm_client
from .prompts import build_answer_prompt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AnswerGenerator:
    def __init__(self, 
                 index_dir: str, 
                 model_name: Optional[str] = None,
                 max_chunk_context: int = 5,
                 temperature: float = 0.3):
        self.index_dir = Path(index_dir)
        self.model_name = model_name
        self.max_chunk_context = max_chunk_context
        self.temperature = temperature
        
        # 載入 chunks 資料
        self.chunks_data = self._load_chunks()
        
        # 初始化 LLM client
        self.llm_client = get_llm_client(model_name)
        
    def _load_chunks(self) -> Dict[int, Dict[str, Any]]:
        """載入 chunks.txt 資料"""
        chunks_file = self.index_dir / "chunks.txt"
        chunks_data = {}
        
        if not chunks_file.exists():
            raise FileNotFoundError(f"Chunks file not found: {chunks_file}")
            
        logger.info(f"Loading chunks from {chunks_file}")
        
        with open(chunks_file, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            f.seek(0)
            
        if first_line.startswith('{'):
            chunks_data = self._parse_jsonl_chunks(chunks_file)
        else:
            chunks_data = self._parse_block_chunks(chunks_file)
            
        logger.info(f"Loaded {len(chunks_data)} chunks")
        return chunks_data
    
    def _parse_jsonl_chunks(self, file_path: Path) -> Dict[int, Dict[str, Any]]:
        """解析 JSONL 格式的 chunks"""
        chunks = {}
        with open(file_path, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if line.strip():
                    chunk_data = json.loads(line)
                    chunks[i] = chunk_data
        return chunks
    
    def _parse_block_chunks(self, file_path: Path) -> Dict[int, Dict[str, Any]]:
        """解析 BLOCK 格式的 chunks"""
        chunks = {}
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        import re
        pattern = r'\[(.*?)\s*\|\s*page\s*(\d+)\](.*?)(?=\[|$)'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for i, (source, page, text) in enumerate(matches):
            chunks[i] = {
                'source': source.strip(),
                'page': int(page),
                'text': text.strip(),
                'chunk_id': i
            }
            
        return chunks
    
    def get_chunk_by_id(self, chunk_id: int) -> Optional[Dict[str, Any]]:
        return self.chunks_data.get(chunk_id)
    
    def get_context_chunks(self, target_chunk_id: int, max_chunks: int = 5) -> List[Dict[str, Any]]:
        """獲取回答問題需要的 context chunks"""
        chunks = []
        
        target_chunk = self.get_chunk_by_id(target_chunk_id)
        if target_chunk:
            chunks.append(target_chunk)
        
        for offset in range(1, max_chunks):
            if len(chunks) >= max_chunks:
                break
                
            prev_id = target_chunk_id - offset
            if prev_id >= 0 and prev_id in self.chunks_data:
                chunks.insert(0, self.chunks_data[prev_id])
                
            if len(chunks) >= max_chunks:
                break
                
            next_id = target_chunk_id + offset
            if next_id in self.chunks_data:
                chunks.append(self.chunks_data[next_id])
                
        return chunks[:max_chunks]
    
    def generate_answer(self, question: str, chunk_id: int, question_lang: str = "zh") -> Dict[str, Any]:
        """生成單個問題的答案"""
        context_chunks = self.get_context_chunks(chunk_id, self.max_chunk_context)
        
        if not context_chunks:
            logger.warning(f"No chunks found for chunk_id: {chunk_id}")
            return {
                "question": question,
                "answer": "無法找到相關資料來回答此問題。",
                "chunks_used": [],
                "confidence": 0.0,
                "lang": question_lang,
                "has_citation": False
            }
        
        prompt = build_answer_prompt(
            question=question,
            chunks=context_chunks,
            language=question_lang
        )
        
        try:
            response = self.llm_client.generate(
                prompt=prompt,
                max_tokens=600,
                temperature=self.temperature
            )
            
            answer_text = response.get('text', '').strip()
            has_citation = self._check_citation(answer_text)
            confidence = self._estimate_confidence(answer_text, context_chunks)
            
            return {
                "question": question,
                "answer": answer_text,
                "chunks_used": [f"chunk_{chunk['chunk_id']}" for chunk in context_chunks],
                "confidence": confidence,
                "lang": question_lang,
                "has_citation": has_citation
            }
            
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return {
                "question": question,
                "answer": f"生成答案時發生錯誤: {str(e)}",
                "chunks_used": [f"chunk_{chunk_id}"],
                "confidence": 0.0,
                "lang": question_lang,
                "has_citation": False
            }
    
    def _check_citation(self, answer: str) -> bool:
        citation_indicators = [
            "根據提供的資料", "根據文件", "文件中提到", "資料顯示",
            "according to", "based on", "the document states", "as mentioned"
        ]
        return any(indicator in answer.lower() for indicator in citation_indicators)
    
    def _estimate_confidence(self, answer: str, chunks: List[Dict]) -> float:
        confidence = 0.5
        
        if self._check_citation(answer):
            confidence += 0.2
            
        if 10 <= len(answer) <= 500:
            confidence += 0.1
            
        if any(keyword in answer for keyword in ["數據", "研究", "結果", "方法", "data", "research", "result"]):
            confidence += 0.2
            
        return min(confidence, 1.0)

def process_questions_file(questions_file: str, 
                          index_dir: str,
                          output_file: str,
                          max_questions: Optional[int] = None,
                          model_name: Optional[str] = None) -> None:
    """處理整個 questions.jsonl 檔案"""
    generator = AnswerGenerator(index_dir, model_name)
    
    with open(questions_file, 'r', encoding='utf-8') as f:
        questions_data = [json.loads(line) for line in f if line.strip()]
    
    logger.info(f"Loaded {len(questions_data)} question groups")
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    processed_count = 0
    
    with open(output_file, 'w', encoding='utf-8') as out_f:
        for q_group in questions_data:
            chunk_id = q_group['chunk_id']
            source = q_group['source']
            page = q_group['page']
            
            for question_data in q_group['questions']:
                if max_questions and processed_count >= max_questions:
                    logger.info(f"Reached max questions limit: {max_questions}")
                    return
                
                question_text = question_data['text']
                question_lang = question_data.get('lang', 'zh')
                source_type = question_data.get('source_type', 'base')
                keyword = question_data.get('keyword', '')
                
                logger.info(f"Processing Q{processed_count + 1} ({source_type}): {question_text[:50]}...")
                
                answer_result = generator.generate_answer(
                    question=question_text,
                    chunk_id=chunk_id,
                    question_lang=question_lang
                )
                
                output_data = {
                    "chunk_id": chunk_id,
                    "source": source,
                    "page": page,
                    "question_data": question_data,
                    "source_type": source_type,
                    "keyword": keyword,
                    **answer_result
                }
                
                out_f.write(json.dumps(output_data, ensure_ascii=False) + '\n')
                out_f.flush()
                
                processed_count += 1
                
                if processed_count % 10 == 0:
                    logger.info(f"Processed {processed_count} questions")
    
    logger.info(f"Answer generation completed! Generated {processed_count} answers")
    logger.info(f"Output saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description="Generate answers for questions using RAG")
    parser.add_argument("--questions", required=True, help="Input questions.jsonl file")
    parser.add_argument("--index", required=True, help="Index directory containing chunks.txt")
    parser.add_argument("--out", required=True, help="Output answers.jsonl file")
    parser.add_argument("--max", type=int, help="Maximum number of questions to process")
    parser.add_argument("--model", help="Model name to use")
    
    args = parser.parse_args()
    
    process_questions_file(
        questions_file=args.questions,
        index_dir=args.index,
        output_file=args.out,
        max_questions=args.max,
        model_name=args.model
    )

if __name__ == "__main__":
    main()