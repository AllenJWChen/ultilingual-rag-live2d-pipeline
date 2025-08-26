# -*- coding: utf-8 -*-
"""
build_chunks_optimized.py - 優化版本的chunks切分工具

修正版本，解決語法錯誤並簡化部分功能
"""

from __future__ import annotations
import os, re, sys, json, argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import fitz  # PyMuPDF
from langchain.text_splitter import RecursiveCharacterTextSplitter

# 可選依賴檢查
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    print("[INFO] PaddleOCR not available. OCR功能將被禁用")

try:
    import jieba
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False
    print("[INFO] jieba not available. 中文分詞功能將被禁用")


class OptimizedChunkBuilder:
    """優化版chunks建構器"""
    
    def __init__(self, 
                 chunk_size: int = 1200,
                 chunk_overlap: int = 150,
                 min_chunk_size: int = 100,
                 quality_threshold: float = 0.6):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.quality_threshold = quality_threshold
        
        # 優化的分隔符順序 - 針對中英混雜技術文件
        self.separators = [
            "\n\n\n",           # 多個換行
            "\n\n",             # 段落分隔
            "\n",               # 單換行
            "。",               # 中文句號
            "！",               # 中文驚嘆號
            "？",               # 中文問號
            "；",               # 中文分號
            ".",                # 英文句號
            "!",                # 英文驚嘆號  
            "?",                # 英文問號
            ";",                # 英文分號
            "：",               # 中文冒號
            ":",                # 英文冒號
            "，",               # 中文逗號
            ",",                # 英文逗號
            "）",               # 中文右括號
            ")",                # 英文右括號
            "】",               # 中文右方括號
            "]",                # 英文右方括號
            "、",               # 中文頓號
            " ",                # 空格
            "",                 # 字符級分割
        ]
        
        # 初始化文字分割器
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
            separators=self.separators,
            keep_separator=True
        )
        
        # OCR引擎初始化（如果可用）
        self.ocr = None
        if PADDLEOCR_AVAILABLE:
            try:
                self.ocr = PaddleOCR(use_angle_cls=True, lang="ch")
                print("[INFO] OCR引擎初始化成功")
            except Exception as e:
                print(f"[WARN] OCR初始化失敗: {e}")
    
    def clean_ocr_text(self, text: str) -> str:
        """清理OCR識別出的文字"""
        if not text:
            return ""
        
        # 移除多餘空白
        text = re.sub(r'\s+', ' ', text)
        
        # 修復常見OCR錯誤
        corrections = {
            # 中文標點修復
            ' ， ': '，',
            ' 。 ': '。',
            ' ！ ': '！', 
            ' ？ ': '？',
            ' ； ': '；',
            ' ： ': '：',
            
            # 英文標點修復
            ' , ': ', ',
            ' . ': '. ',
            ' ! ': '! ',
            ' ? ': '? ',
            ' ; ': '; ',
            ' : ': ': ',
            
            # 括號修復
            '( ': '（',
            ' )': '）',
            '[ ': '【',
            ' ]': '】',
        }
        
        for wrong, correct in corrections.items():
            text = text.replace(wrong, correct)
        
        # 移除行首行尾空白
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(line for line in lines if line)
        
        return text.strip()
    
    def extract_page_text_enhanced(self, page, page_idx: int, tmp_dir: Path) -> Tuple[str, bool]:
        """增強版頁面文字抽取"""
        # 先嘗試文字層
        text = (page.get_text("text") or "").strip()
        used_ocr = False
        
        # 如果文字層品質不佳且有OCR，則使用OCR
        if (len(text) < 50 or self._is_low_quality_text(text)) and self.ocr:
            print(f"[OCR] 頁面 {page_idx+1} 文字層品質不佳，使用OCR...")
            tmp_dir.mkdir(parents=True, exist_ok=True)
            img_path = tmp_dir / f"page_{page_idx+1}.png"
            
            try:
                # 高解析度轉圖
                pix = page.get_pixmap(dpi=300)
                pix.save(img_path.as_posix())
                
                # OCR識別
                result = self.ocr.ocr(img_path.as_posix(), cls=True)
                if result and result[0]:
                    ocr_text = "\n".join([line[1][0] for line in result[0]])
                    ocr_text = self.clean_ocr_text(ocr_text)
                    if len(ocr_text) > len(text):
                        text = ocr_text
                        used_ocr = True
                        
            except Exception as e:
                print(f"[WARN] OCR失敗: {e}")
            finally:
                # 清理暫存檔
                try:
                    img_path.unlink(missing_ok=True)
                except:
                    pass
        
        # 清理文字
        text = self._clean_extracted_text(text)
        return text, used_ocr
    
    def _is_low_quality_text(self, text: str) -> bool:
        """判斷文字品質是否過低"""
        if not text or len(text) < 20:
            return True
        
        # 檢查是否包含過多特殊字符
        special_chars = len(re.findall(r'[^\w\s\u4e00-\u9fff，。！？；：""''（）【】\-\.]', text))
        if special_chars / len(text) > 0.3:
            return True
        
        # 檢查是否有意義的文字內容
        meaningful_chars = len(re.findall(r'[\w\u4e00-\u9fff]', text))
        if meaningful_chars / len(text) < 0.3:
            return True
        
        return False
    
    def _clean_extracted_text(self, text: str) -> str:
        """清理抽取的文字"""
        if not text:
            return ""
        
        # 統一換行符
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        
        # 移除過多連續換行（保留段落結構）
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # 清理頁首頁尾常見雜訊 - 修正後的版本
        noise_patterns = [
            r'^\d+$',                    # 單獨的頁碼
            r'^Page \d+$',               # "Page X"
            r'^第\s*\d+\s*頁$',          # "第X頁"
            r'^\d+\s*/\s*\d+$',         # "1/10"
            r'^Copyright.*$',            # 版權信息
            r'^©.*$',                   # 版權符號
        ]
        
        lines = text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                cleaned_lines.append('')
                continue
            
            # 檢查是否為雜訊
            is_noise = False
            for pattern in noise_patterns:
                if re.match(pattern, line, re.IGNORECASE):
                    is_noise = True
                    break
            
            if not is_noise:
                cleaned_lines.append(line)
        
        # 重組文字並清理多餘空行
        text = '\n'.join(cleaned_lines)
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)
        
        return text.strip()
    
    def smart_chunk_with_boundaries(self, text: str) -> List[str]:
        """智能分塊 - 考慮句子邊界"""
        if not text or len(text) < self.min_chunk_size:
            return []
        
        # 使用langchain的分割器進行初步分割
        initial_chunks = self.text_splitter.split_text(text)
        
        # 對每個chunk進行邊界優化和品質檢查
        optimized_chunks = []
        for chunk in initial_chunks:
            chunk = chunk.strip()
            if len(chunk) < self.min_chunk_size:
                continue
            
            # 調整chunk邊界到合適的句子結束位置
            adjusted_chunk = self._adjust_chunk_boundary(chunk)
            if adjusted_chunk and len(adjusted_chunk) >= self.min_chunk_size:
                optimized_chunks.append(adjusted_chunk)
        
        return optimized_chunks
    
    def _adjust_chunk_boundary(self, chunk: str) -> str:
        """調整chunk邊界到適當的句子結束位置"""
        if len(chunk) <= self.chunk_size * 0.8:  # 如果chunk不太長，直接返回
            return chunk
        
        # 尋找最佳截斷點
        max_length = int(self.chunk_size * 0.95)  # 允許稍微超過目標長度
        
        if len(chunk) <= max_length:
            return chunk
        
        # 在最大長度附近尋找合適的句子邊界
        search_start = max(max_length - 200, max_length // 2)
        search_end = min(max_length + 100, len(chunk))
        
        best_cut = max_length
        search_text = chunk[search_start:search_end]
        
        # 按優先級尋找分割點
        sentence_enders = ['。', '！', '？', '.', '!', '?']
        clause_enders = ['；', ';', '：', ':']
        phrase_enders = ['，', ',', '、']
        
        for enders in [sentence_enders, clause_enders, phrase_enders]:
            for ender in enders:
                pos = search_text.rfind(ender)
                if pos > 0:
                    actual_pos = search_start + pos + 1
                    if actual_pos > len(chunk) * 0.5:  # 確保不會切得太短
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
    
    def calculate_chunk_quality(self, chunk: str) -> float:
        """計算chunk品質評分 (0-1)"""
        if not chunk:
            return 0.0
        
        score = 1.0
        
        # 長度評分
        length = len(chunk)
        if length < self.min_chunk_size:
            score *= 0.3
        elif length < self.min_chunk_size * 2:
            score *= 0.7
        
        # 內容完整性評分
        # 檢查是否以句子邊界結束
        if not chunk.rstrip().endswith(('。', '！', '？', '.', '!', '?', '；', ';', '：', ':')):
            score *= 0.8
        
        # 檢查中英文比例平衡
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', chunk))
        english_chars = len(re.findall(r'[a-zA-Z]', chunk))
        total_meaningful = chinese_chars + english_chars
        
        if total_meaningful > 0:
            meaningful_ratio = total_meaningful / length
            if meaningful_ratio < 0.3:  # 太多特殊字符或空白
                score *= 0.5
        
        # 檢查是否包含表格或列表結構（這些通常品質較好）
        if '|' in chunk and chunk.count('|') > 2:  # 可能是表格
            score *= 1.2
        elif re.search(r'^\s*[\d\-\*\•]\s*', chunk, re.MULTILINE):  # 可能是列表
            score *= 1.1
        
        # 檢查技術內容密度
        tech_indicators = len(re.findall(r'\b[A-Z]{2,}\b|\d+\.\d+|\([^)]*\d{4}[^)]*\)', chunk))
        if tech_indicators > 0:
            score *= min(1.3, 1 + tech_indicators * 0.05)  # 技術內容加分
        
        return min(1.0, score)
    
    def build_chunks_from_pdf(self, pdf_path: Path, tmp_dir: Path) -> List[Dict]:
        """從PDF建立chunks"""
        chunks = []
        
        print(f"[INFO] 處理PDF: {pdf_path.name}")
        
        try:
            doc = fitz.open(str(pdf_path))
            total_pages = len(doc)
            ocr_pages = 0
            
            for page_idx, page in enumerate(doc):
                print(f"[INFO] 處理第 {page_idx + 1}/{total_pages} 頁", end="")
                
                # 抽取頁面文字
                text, used_ocr = self.extract_page_text_enhanced(page, page_idx, tmp_dir)
                if used_ocr:
                    ocr_pages += 1
                    print(" (OCR)", end="")
                
                print()
                
                if not text:
                    continue
                
                # 智能分塊
                page_chunks = self.smart_chunk_with_boundaries(text)
                
                # 評估品質並過濾
                for chunk_text in page_chunks:
                    quality = self.calculate_chunk_quality(chunk_text)
                    
                    if quality >= self.quality_threshold:
                        chunk_data = {
                            "source": pdf_path.name,
                            "page": page_idx + 1,
                            "text": chunk_text,
                            "quality_score": round(quality, 3),
                            "length": len(chunk_text)
                        }
                        chunks.append(chunk_data)
                    else:
                        print(f"[WARN] 低品質chunk已過濾 (品質: {quality:.3f})")
            
            print(f"[INFO] PDF處理完成: {len(chunks)} chunks, {ocr_pages}/{total_pages} 頁使用OCR")
            
        except Exception as e:
            print(f"[ERROR] 處理PDF失敗: {e}")
            import traceback
            traceback.print_exc()
            
        return chunks
    
    def process_directory(self, input_dir: Path, output_file: Path, tmp_dir: Path):
        """處理目錄中的所有PDF"""
        pdf_files = list(input_dir.rglob("*.pdf")) + list(input_dir.rglob("*.PDF"))
        pdf_files = sorted(set(pdf_files))
        
        if not pdf_files:
            print(f"[WARN] 在 {input_dir} 中找不到PDF檔案")
            return
        
        print(f"[INFO] 找到 {len(pdf_files)} 個PDF檔案")
        
        all_chunks = []
        stats = {
            'total_files': len(pdf_files),
            'total_chunks': 0,
            'total_pages': 0,
            'ocr_pages': 0,
            'avg_quality': 0,
            'quality_distribution': {'high': 0, 'medium': 0, 'low': 0}
        }
        
        # 確保輸出目錄存在
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 處理每個PDF
        for pdf_path in pdf_files:
            print(f"\n{'='*60}")
            chunks = self.build_chunks_from_pdf(pdf_path, tmp_dir)
            all_chunks.extend(chunks)
            
            # 統計更新
            stats['total_chunks'] += len(chunks)
            if chunks:
                qualities = [c['quality_score'] for c in chunks]
                
                for q in qualities:
                    if q >= 0.8:
                        stats['quality_distribution']['high'] += 1
                    elif q >= 0.6:
                        stats['quality_distribution']['medium'] += 1
                    else:
                        stats['quality_distribution']['low'] += 1
        
        # 計算平均品質
        if all_chunks:
            all_qualities = [c['quality_score'] for c in all_chunks]
            stats['avg_quality'] = sum(all_qualities) / len(all_qualities)
        
        # 輸出結果
        with open(output_file, 'w', encoding='utf-8') as f:
            for chunk in all_chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')
        
        # 顯示統計
        print(f"\n{'='*60}")
        print("📊 處理統計:")
        print(f"  PDF檔案: {stats['total_files']}")
        print(f"  總chunks: {stats['total_chunks']}")
        print(f"  平均品質: {stats['avg_quality']:.3f}")
        print(f"  品質分布:")
        print(f"    高品質(≥0.8): {stats['quality_distribution']['high']}")
        print(f"    中品質(≥0.6): {stats['quality_distribution']['medium']}")  
        print(f"    低品質(<0.6): {stats['quality_distribution']['low']}")
        print(f"\n✅ 輸出至: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="優化版chunks建構工具")
    parser.add_argument("--input", default="datasets", help="輸入資料夾")
    parser.add_argument("--output", default="indices/chunks_optimized.jsonl", help="輸出檔案")
    parser.add_argument("--chunk-size", type=int, default=1200, help="chunk大小")
    parser.add_argument("--overlap", type=int, default=150, help="重疊大小")
    parser.add_argument("--min-size", type=int, default=100, help="最小chunk大小")
    parser.add_argument("--quality-threshold", type=float, default=0.6, help="品質閾值")
    parser.add_argument("--enable-ocr", action="store_true", help="啟用OCR")
    
    args = parser.parse_args()
    
    # 檢查依賴
    if args.enable_ocr and not PADDLEOCR_AVAILABLE:
        print("[ERROR] 要使用OCR請先安裝: pip install paddleocr")
        sys.exit(1)
    
    # 初始化建構器
    builder = OptimizedChunkBuilder(
        chunk_size=args.chunk_size,
        chunk_overlap=args.overlap,
        min_chunk_size=args.min_size,
        quality_threshold=args.quality_threshold
    )
    
    # 如果沒啟用OCR，移除OCR引擎
    if not args.enable_ocr:
        builder.ocr = None
    
    input_dir = Path(args.input)
    output_file = Path(args.output)
    tmp_dir = output_file.parent / "_tmp_ocr"
    
    try:
        print("🚀 開始優化版chunks建構...")
        builder.process_directory(input_dir, output_file, tmp_dir)
        print("🎉 處理完成!")
        
    except KeyboardInterrupt:
        print("\n🛑 用戶中斷")
    except Exception as e:
        print(f"❌ 處理失敗: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # 清理暫存目錄
        if tmp_dir.exists():
            import shutil
            try:
                shutil.rmtree(tmp_dir)
            except:
                pass


if __name__ == "__main__":
    main()