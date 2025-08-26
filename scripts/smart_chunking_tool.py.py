# -*- coding: utf-8 -*-
"""
語言自適應智能分塊工具
主要改進：
1. 自動檢測內容語言（中文/英文/混合）
2. 根據語言動態調整chunk長度
3. 語言特定的邊界檢測
4. 改進的品質評分系統
"""

import os
import re
import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import argparse

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("[WARN] PyMuPDF未安裝，無法處理PDF檔案")

try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    print("[WARN] LangChain未安裝，使用簡化版分塊功能")

try:
    from tqdm.auto import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False


class LanguageAwareChunkBuilder:
    """語言感知的智能分塊器"""
    
    def __init__(self, 
                 base_chunk_size: int = 1200,
                 base_overlap: int = 150,
                 base_min_size: int = 100,
                 quality_threshold: float = 0.6):
        
        self.base_chunk_size = base_chunk_size
        self.base_overlap = base_overlap
        self.base_min_size = base_min_size
        self.quality_threshold = quality_threshold
        
        # 語言特定配置
        self.lang_config = {
            "chinese": {
                "size_multiplier": 1.3,    # 中文需要更多字符
                "overlap_multiplier": 1.2,
                "min_size_multiplier": 1.5,
                "sentence_enders": ['。', '！', '？', '…'],
                "clause_enders": ['；', '：'],
                "phrase_enders": ['，', '、']
            },
            "english": {
                "size_multiplier": 1.0,    # 英文保持原長度
                "overlap_multiplier": 1.0,
                "min_size_multiplier": 1.0,
                "sentence_enders": ['.', '!', '?'],
                "clause_enders": [';', ':'],
                "phrase_enders": [',']
            },
            "mixed": {
                "size_multiplier": 1.15,   # 混合內容取中間值
                "overlap_multiplier": 1.1,
                "min_size_multiplier": 1.25,
                "sentence_enders": ['。', '！', '？', '.', '!', '?', '…'],
                "clause_enders": ['；', '：', ';', ':'],
                "phrase_enders": ['，', '、', ',']
            }
        }
        
        print(f"[INIT] 語言自適應分塊器初始化完成")
        print(f"       基礎參數: chunk_size={base_chunk_size}, overlap={base_overlap}")
    
    def detect_content_language(self, text: str) -> Tuple[str, Dict[str, float]]:
        """
        檢測文本主要語言
        返回: (主要語言, 語言統計)
        """
        if not text.strip():
            return "unknown", {}
            
        # 統計不同類型字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        total_meaningful = chinese_chars + english_chars
        
        if total_meaningful == 0:
            return "unknown", {"chinese": 0, "english": 0, "other": 100}
        
        chinese_ratio = chinese_chars / total_meaningful
        english_ratio = english_chars / total_meaningful
        
        stats = {
            "chinese": chinese_ratio * 100,
            "english": english_ratio * 100,
            "other": max(0, 100 - (chinese_ratio + english_ratio) * 100)
        }
        
        # 判定主要語言
        if chinese_ratio > 0.6:
            return "chinese", stats
        elif english_ratio > 0.6:
            return "english", stats
        elif chinese_ratio > 0.3 and english_ratio > 0.3:
            return "mixed", stats
        else:
            return "unknown", stats
    
    def get_language_specific_params(self, lang: str) -> Dict[str, int]:
        """根據語言獲取分塊參數"""
        if lang not in self.lang_config:
            lang = "mixed"  # 默認使用混合配置
            
        config = self.lang_config[lang]
        return {
            "chunk_size": int(self.base_chunk_size * config["size_multiplier"]),
            "overlap": int(self.base_overlap * config["overlap_multiplier"]),
            "min_size": int(self.base_min_size * config["min_size_multiplier"]),
            "sentence_enders": config["sentence_enders"],
            "clause_enders": config["clause_enders"],
            "phrase_enders": config["phrase_enders"]
        }
    
    def smart_chunk_with_language_awareness(self, text: str) -> List[Dict]:
        """
        語言感知的智能分塊
        返回包含語言信息的chunk字典列表
        """
        if not text or len(text.strip()) < 10:
            return []
        
        # 檢測整體語言
        main_lang, lang_stats = self.detect_content_language(text)
        lang_params = self.get_language_specific_params(main_lang)
        
        print(f"[LANG] 檢測到主要語言: {main_lang}")
        print(f"       語言分布: 中文{lang_stats.get('chinese', 0):.1f}%, "
              f"英文{lang_stats.get('english', 0):.1f}%")
        print(f"       調整參數: chunk_size={lang_params['chunk_size']}, "
              f"min_size={lang_params['min_size']}")
        
        # 創建語言特定的文本分割器
        if LANGCHAIN_AVAILABLE:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=lang_params["chunk_size"],
                chunk_overlap=lang_params["overlap"],
                separators=["\n\n", "\n"] + lang_params["sentence_enders"] + 
                           lang_params["clause_enders"] + [" ", ""]
            )
            initial_chunks = splitter.split_text(text)
        else:
            # 簡化版分割
            initial_chunks = self._simple_split_text(text, lang_params)
        
        # 處理每個chunk並添加語言信息
        processed_chunks = []
        for i, chunk_text in enumerate(initial_chunks):
            if len(chunk_text.strip()) < lang_params["min_size"]:
                continue
            
            # 調整chunk邊界
            adjusted_chunk = self._adjust_chunk_boundary(chunk_text, lang_params)
            if not adjusted_chunk or len(adjusted_chunk) < lang_params["min_size"]:
                continue
            
            # 檢測這個chunk的具體語言
            chunk_lang, chunk_lang_stats = self.detect_content_language(adjusted_chunk)
            
            # 計算品質分數
            quality_score = self._calculate_language_aware_quality(
                adjusted_chunk, chunk_lang, lang_params
            )
            
            chunk_info = {
                "text": adjusted_chunk,
                "chunk_id": i,
                "length": len(adjusted_chunk),
                "quality_score": quality_score,
                "main_language": chunk_lang,
                "language_stats": chunk_lang_stats,
                "global_language": main_lang,
                "language_params": lang_params,
                "_quality": "high" if quality_score >= 0.8 else 
                           "medium" if quality_score >= 0.6 else "low"
            }
            
            processed_chunks.append(chunk_info)
        
        return processed_chunks
    
    def _simple_split_text(self, text: str, lang_params: Dict) -> List[str]:
        """簡化版文本分割（當LangChain不可用時）"""
        chunks = []
        chunk_size = lang_params["chunk_size"]
        overlap = lang_params["overlap"]
        
        words = text.split()
        current_chunk = []
        current_length = 0
        
        for word in words:
            word_length = len(word) + 1  # +1 for space
            
            if current_length + word_length > chunk_size and current_chunk:
                chunks.append(" ".join(current_chunk))
                # 保留重疊
                overlap_words = current_chunk[-overlap//10:] if len(current_chunk) > overlap//10 else []
                current_chunk = overlap_words + [word]
                current_length = sum(len(w) + 1 for w in current_chunk)
            else:
                current_chunk.append(word)
                current_length += word_length
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def _adjust_chunk_boundary(self, chunk: str, lang_params: Dict) -> str:
        """根據語言特性調整chunk邊界"""
        if len(chunk) <= lang_params["chunk_size"] * 0.8:
            return chunk
        
        max_length = int(lang_params["chunk_size"] * 0.95)
        if len(chunk) <= max_length:
            return chunk
        
        # 在最大長度附近尋找適合的分割點
        search_start = max(max_length - 200, max_length // 2)
        search_end = min(max_length + 100, len(chunk))
        search_text = chunk[search_start:search_end]
        
        best_cut = max_length
        
        # 按優先級尋找分割點
        for enders in [lang_params["sentence_enders"], 
                      lang_params["clause_enders"], 
                      lang_params["phrase_enders"]]:
            for ender in enders:
                pos = search_text.rfind(ender)
                if pos > 0:
                    actual_pos = search_start + pos + 1
                    if actual_pos > len(chunk) * 0.5:
                        best_cut = actual_pos
                        break
            if best_cut != max_length:
                break
        
        # 如果找不到合適分割點，在空格處分割
        if best_cut == max_length:
            space_pos = chunk.rfind(' ', max_length - 100, max_length)
            if space_pos > max_length * 0.7:
                best_cut = space_pos
        
        return chunk[:best_cut].strip()
    
    def _calculate_language_aware_quality(self, chunk: str, lang: str, 
                                        lang_params: Dict) -> float:
        """語言感知的品質評分"""
        if not chunk:
            return 0.0
        
        score = 1.0
        length = len(chunk)
        
        # 長度評分 - 根據語言調整
        min_size = lang_params["min_size"]
        ideal_size = lang_params["chunk_size"] * 0.7
        
        if length < min_size:
            score *= 0.3
        elif length < min_size * 2:
            score *= 0.7
        elif min_size * 2 <= length <= ideal_size:
            score *= 1.0  # 最佳長度範圍
        elif length > lang_params["chunk_size"] * 1.2:
            score *= 0.8  # 太長扣分
        
        # 邊界完整性評分
        endings = lang_params["sentence_enders"] + lang_params["clause_enders"]
        if chunk.rstrip().endswith(tuple(endings)):
            score *= 1.1  # 良好邊界加分
        
        # 語言純度評分
        chunk_lang, chunk_stats = self.detect_content_language(chunk)
        if chunk_lang == lang:
            score *= 1.05  # 語言一致性加分
        elif chunk_lang == "mixed" and lang in ["chinese", "english"]:
            score *= 0.95  # 混合內容小幅扣分
        
        # 內容密度評分
        meaningful_chars = len(re.findall(r'[\w\u4e00-\u9fff]', chunk))
        if meaningful_chars / length < 0.3:
            score *= 0.5  # 太多特殊字符或空白
        
        # 技術內容檢測（技術文檔通常品質較高）
        tech_indicators = len(re.findall(r'\b[A-Z]{2,}\b|\d+\.\d+|\([^)]*\d{4}[^)]*\)', chunk))
        if tech_indicators > 0:
            score *= min(1.2, 1 + tech_indicators * 0.02)
        
        return min(1.0, score)
    
    def process_text_file(self, file_path: Path) -> List[Dict]:
        """處理文本檔案"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
            
            chunks = self.smart_chunk_with_language_awareness(text)
            
            # 添加檔案信息
            for chunk in chunks:
                chunk["source"] = file_path.name
                chunk["page"] = 0
            
            return chunks
            
        except Exception as e:
            print(f"[ERROR] 處理文本檔案 {file_path} 失敗: {e}")
            return []
    
    def process_pdf_file(self, file_path: Path) -> List[Dict]:
        """處理PDF檔案"""
        if not PYMUPDF_AVAILABLE:
            print(f"[SKIP] PyMuPDF未安裝，跳過PDF檔案: {file_path}")
            return []
        
        chunks = []
        
        try:
            doc = fitz.open(str(file_path))
            
            for page_num in range(len(doc)):
                page = doc[page_num]
                text = page.get_text()
                
                if text.strip():
                    page_chunks = self.smart_chunk_with_language_awareness(text)
                    
                    # 添加頁面信息
                    for chunk in page_chunks:
                        chunk["source"] = file_path.name
                        chunk["page"] = page_num + 1
                    
                    chunks.extend(page_chunks)
            
            doc.close()
            return chunks
            
        except Exception as e:
            print(f"[ERROR] 處理PDF檔案 {file_path} 失敗: {e}")
            return []
    
    def process_directory(self, input_dir: Path, output_file: Path):
        """處理整個目錄"""
        if not input_dir.exists():
            print(f"[ERROR] 輸入目錄不存在: {input_dir}")
            return
        
        # 支援的檔案類型
        supported_extensions = {'.txt', '.md', '.pdf'}
        files = [f for f in input_dir.rglob('*') 
                if f.is_file() and f.suffix.lower() in supported_extensions]
        
        if not files:
            print(f"[WARN] 在目錄 {input_dir} 中未找到支援的檔案")
            return
        
        all_chunks = []
        stats = {
            "total_files": len(files),
            "processed_files": 0,
            "total_chunks": 0,
            "language_distribution": {"chinese": 0, "english": 0, "mixed": 0, "unknown": 0},
            "quality_distribution": {"high": 0, "medium": 0, "low": 0}
        }
        
        # 確保輸出目錄存在
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        print(f"[INFO] 開始處理 {len(files)} 個檔案...")
        
        file_iter = tqdm(files, desc="處理檔案") if TQDM_AVAILABLE else files
        
        for file_path in file_iter:
            print(f"[PROCESS] 處理檔案: {file_path.name}")
            
            if file_path.suffix.lower() == '.pdf':
                chunks = self.process_pdf_file(file_path)
            else:
                chunks = self.process_text_file(file_path)
            
            if chunks:
                all_chunks.extend(chunks)
                stats["processed_files"] += 1
                
                # 更新統計
                for chunk in chunks:
                    lang = chunk.get("main_language", "unknown")
                    quality = chunk.get("_quality", "low")
                    stats["language_distribution"][lang] += 1
                    stats["quality_distribution"][quality] += 1
        
        stats["total_chunks"] = len(all_chunks)
        
        # 寫入輸出檔案
        with open(output_file, 'w', encoding='utf-8') as f:
            for chunk in all_chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
        
        # 顯示統計結果
        print(f"\n📊 處理統計:")
        print(f"   處理檔案: {stats['processed_files']}/{stats['total_files']}")
        print(f"   生成chunks: {stats['total_chunks']} 個")
        print(f"   語言分布:")
        for lang, count in stats["language_distribution"].items():
            if count > 0:
                pct = count / stats["total_chunks"] * 100
                print(f"     {lang}: {count} ({pct:.1f}%)")
        print(f"   品質分布:")
        for quality, count in stats["quality_distribution"].items():
            if count > 0:
                pct = count / stats["total_chunks"] * 100
                print(f"     {quality}: {count} ({pct:.1f}%)")
        
        print(f"\n✅ 輸出至: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="語言自適應智能分塊工具")
    parser.add_argument("--input", default="datasets", help="輸入資料夾")
    parser.add_argument("--output", default="indices/chunks_language_aware.jsonl", help="輸出檔案")
    parser.add_argument("--base-chunk-size", type=int, default=1200, help="基礎chunk大小")
    parser.add_argument("--base-overlap", type=int, default=150, help="基礎重疊大小")
    parser.add_argument("--base-min-size", type=int, default=100, help="基礎最小chunk大小")
    parser.add_argument("--quality-threshold", type=float, default=0.6, help="品質閾值")
    
    args = parser.parse_args()
    
    # 初始化分塊器
    builder = LanguageAwareChunkBuilder(
        base_chunk_size=args.base_chunk_size,
        base_overlap=args.base_overlap,
        base_min_size=args.base_min_size,
        quality_threshold=args.quality_threshold
    )
    
    input_dir = Path(args.input)
    output_file = Path(args.output)
    
    try:
        print("🚀 開始語言自適應分塊處理...")
        builder.process_directory(input_dir, output_file)
        print("🎉 處理完成!")
        
    except KeyboardInterrupt:
        print("\n🛑 用戶中斷")
    except Exception as e:
        print(f"❌ 處理失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()