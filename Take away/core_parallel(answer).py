#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
並行答案生成模組 - 高性能版本
"""

import os
import json
import time
import argparse
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import logging

try:
    from tqdm.auto import tqdm
except ImportError:
    tqdm = None

# 修正後的 Import 路徑
from .prompts import build_answer_prompt
from .clients import ask_answer_llm

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HighPerformanceAnswerGenerator:
    """高性能答案生成器"""
    
    def __init__(self, 
                 index_dir: str,
                 model_name: Optional[str] = None,
                 max_context_chunks: int = 3,
                 temperature: float = 0.3):
        self.index_dir = Path(index_dir)
        self.model_name = model_name or os.getenv("MODEL_ANSWER", "llama3.1:8b-instruct")
        self.max_context_chunks = max_context_chunks
        self.temperature = temperature
        
        # 載入並快取所有 chunks
        self.chunks_cache = self._load_and_cache_chunks()
        logger.info(f"Cached {len(self.chunks_cache)} chunks in memory")
        
    def _load_and_cache_chunks(self) -> Dict[int, Dict[str, Any]]:
        """一次性載入所有 chunks 到記憶體"""
        chunks_file = self.index_dir / "chunks.txt"
        
        if not chunks_file.exists():
            raise FileNotFoundError(f"Chunks file not found: {chunks_file}")
        
        chunks_data = {}
        
        with open(chunks_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if content.strip().startswith('{'):
            # JSONL 格式
            for i, line in enumerate(content.strip().split('\n')):
                if line.strip():
                    try:
                        chunk = json.loads(line)
                        chunks_data[i] = chunk
                    except json.JSONDecodeError:
                        continue
        else:
            # BLOCK 格式
            import re
            pattern = r'\[(.*?)\s*\|\s*page\s*(\d+)\](.*?)(?=\[|$)'
            matches = re.findall(pattern, content, re.DOTALL)
            
            for i, (source, page, text) in enumerate(matches):
                chunks_data[i] = {
                    'source': source.strip(),
                    'page': int(page),
                    'text': text.strip(),
                    'chunk_id': i
                }
        
        return chunks_data
    
    def get_context_chunks(self, target_chunk_id: int) -> List[Dict[str, Any]]:
        """快速獲取 context chunks"""
        chunks = []
        
        # 主要 chunk
        if target_chunk_id in self.chunks_cache:
            chunks.append(self.chunks_cache[target_chunk_id])
        
        # 相鄰 chunks
        for offset in range(1, self.max_context_chunks):
            if len(chunks) >= self.max_context_chunks:
                break
                
            prev_id = target_chunk_id - offset
            if prev_id >= 0 and prev_id in self.chunks_cache:
                chunks.insert(0, self.chunks_cache[prev_id])
                
            if len(chunks) >= self.max_context_chunks:
                break
                
            next_id = target_chunk_id + offset
            if next_id in self.chunks_cache:
                chunks.append(self.chunks_cache[next_id])
        
        return chunks[:self.max_context_chunks]

def process_single_question(generator: HighPerformanceAnswerGenerator,
                          question_item: Dict[str, Any],
                          retry_count: int = 3) -> Tuple[bool, Dict[str, Any]]:
    """處理單個問題"""
    chunk_id = question_item['chunk_id']
    source = question_item['source']
    page = question_item['page']
    question_data = question_item['question_data']
    
    question_text = question_data['text']
    question_lang = question_data.get('lang', 'zh')
    source_type = question_data.get('source_type', 'base')
    keyword = question_data.get('keyword', '')
    
    # 獲取 context
    context_chunks = generator.get_context_chunks(chunk_id)
    
    if not context_chunks:
        return False, {
            "error": f"No chunks found for chunk_id: {chunk_id}",
            "question": question_text
        }
    
    # 建構 prompt
    prompt = build_answer_prompt(
        question=question_text,
        chunks=context_chunks,
        language=question_lang
    )
    
    # 重試機制
    for attempt in range(retry_count):
        try:
            answer_text = ask_answer_llm(
                prompt=prompt,
                question=question_text,
                language=question_lang
            )
            
            has_citation = any(indicator in answer_text.lower() 
                             for indicator in ["根據", "文件", "according to", "based on"])
            
            confidence = 0.7
            if has_citation:
                confidence += 0.2
            if 20 <= len(answer_text) <= 500:
                confidence += 0.1
                
            result = {
                "chunk_id": chunk_id,
                "source": source,
                "page": page,
                "question_data": question_data,
                "source_type": source_type,
                "keyword": keyword,
                "question": question_text,
                "answer": answer_text.strip(),
                "chunks_used": [f"chunk_{chunk['chunk_id']}" for chunk in context_chunks],
                "confidence": min(confidence, 1.0),
                "lang": question_lang,
                "has_citation": has_citation,
                "attempt": attempt + 1
            }
            
            return True, result
            
        except Exception as e:
            if attempt == retry_count - 1:
                return False, {
                    "chunk_id": chunk_id,
                    "source": source,
                    "page": page,
                    "question": question_text,
                    "error": f"Failed after {retry_count} attempts: {str(e)}",
                    "source_type": source_type,
                    "keyword": keyword
                }
            else:
                time.sleep(0.5 * (attempt + 1))
                continue
    
    return False, {"error": "Unexpected error in process_single_question"}

def gpu_monitor_thread(stop_event: threading.Event, stats: Dict[str, Any]):
    """GPU 監控線程"""
    try:
        import subprocess
        while not stop_event.is_set():
            try:
                result = subprocess.run([
                    'nvidia-smi', 
                    '--query-gpu=utilization.gpu,memory.used,memory.total',
                    '--format=csv,noheader,nounits'
                ], capture_output=True, text=True, timeout=2)
                
                if result.returncode == 0:
                    line = result.stdout.strip().split('\n')[0]
                    gpu_util, mem_used, mem_total = map(int, line.split(','))
                    
                    stats['gpu_util_max'] = max(stats.get('gpu_util_max', 0), gpu_util)
                    stats['vram_used_max'] = max(stats.get('vram_used_max', 0), mem_used)
                    stats['vram_total'] = mem_total
                    
            except Exception:
                pass
            
            time.sleep(1)
    except ImportError:
        pass

def parallel_answer_generation(questions_file: str,
                             index_dir: str, 
                             output_file: str,
                             workers: int = 32,
                             max_questions: Optional[int] = None,
                             model_name: Optional[str] = None) -> None:
    """大規模並行答案生成"""
    logger.info(f"🚀 Starting parallel answer generation with {workers} workers")
    logger.info(f"💾 Model: {model_name or 'default'}")
    
    generator = HighPerformanceAnswerGenerator(index_dir, model_name)
    
    # 載入所有問題
    all_questions = []
    with open(questions_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                q_group = json.loads(line)
                for question_data in q_group['questions']:
                    all_questions.append({
                        'chunk_id': q_group['chunk_id'],
                        'source': q_group['source'],
                        'page': q_group['page'],
                        'question_data': question_data
                    })
    
    if max_questions:
        all_questions = all_questions[:max_questions]
    
    logger.info(f"📊 Total questions to process: {len(all_questions)}")
    
    # GPU 監控
    gpu_stats = {}
    gpu_stop_event = threading.Event()
    gpu_thread = threading.Thread(target=gpu_monitor_thread, args=(gpu_stop_event, gpu_stats))
    gpu_thread.start()
    
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    os.environ["OLLAMA_NUM_PARALLEL"] = str(workers)
    
    start_time = time.time()
    successful_answers = 0
    failed_answers = 0
    
    try:
        with open(output_file, 'w', encoding='utf-8') as out_f:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(process_single_question, generator, q_item)
                    for q_item in all_questions
                ]
                
                iterator = as_completed(futures)
                if tqdm:
                    iterator = tqdm(iterator, total=len(futures), 
                                  desc="Generating answers", unit="Q")
                
                for future in iterator:
                    success, result = future.result()
                    
                    if success:
                        successful_answers += 1
                        out_f.write(json.dumps(result, ensure_ascii=False) + '\n')
                        out_f.flush()
                    else:
                        failed_answers += 1
                        logger.warning(f"Failed: {result.get('error', 'Unknown error')}")
                        
                        result['status'] = 'failed'
                        out_f.write(json.dumps(result, ensure_ascii=False) + '\n')
                        out_f.flush()
    
    finally:
        gpu_stop_event.set()
        gpu_thread.join()
    
    end_time = time.time()
    total_time = end_time - start_time
    throughput = len(all_questions) / total_time if total_time > 0 else 0
    
    logger.info(f"🎉 Answer generation completed!")
    logger.info(f"📊 Performance Report:")
    logger.info(f"   ✅ Successful: {successful_answers}")
    logger.info(f"   ❌ Failed: {failed_answers}")
    logger.info(f"   ⏱️  Total time: {total_time:.2f}s")
    logger.info(f"   🚀 Throughput: {throughput:.2f} Q/s")
    logger.info(f"   🔥 Workers: {workers}")
    
    if gpu_stats:
        logger.info(f"   🎮 GPU utilization (max): {gpu_stats.get('gpu_util_max', 'N/A')}%")
        logger.info(f"   💾 VRAM usage (max): {gpu_stats.get('vram_used_max', 'N/A')} MB")
    
    logger.info(f"📁 Output saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(description="High-performance parallel answer generation")
    parser.add_argument("--questions", required=True, help="Input questions.jsonl file")
    parser.add_argument("--index", required=True, help="Index directory containing chunks.txt")
    parser.add_argument("--out", required=True, help="Output answers.jsonl file")
    parser.add_argument("--workers", type=int, default=32, help="Number of parallel workers")
    parser.add_argument("--max", type=int, help="Maximum number of questions to process")
    parser.add_argument("--model", help="Model name to use")
    
    args = parser.parse_args()
    
    parallel_answer_generation(
        questions_file=args.questions,
        index_dir=args.index,
        output_file=args.out,
        workers=args.workers,
        max_questions=args.max,
        model_name=args.model
    )

if __name__ == "__main__":
    main()