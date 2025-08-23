# -*- coding: utf-8 -*-
"""
Chunks 品質檢查工具

檢查項目：
1. 基本統計：總數、平均長度、長度分布
2. 文字品質：語言混雜、特殊字符、截斷問題
3. 語意完整性：句子完整度、段落連貫性
4. 內容重複：相似度檢查、重複內容偵測
5. 領域特性：技術文件特徵、專業術語分析

使用方式：
python -m scripts.check_chunks_quality --input indices/chunks.jsonl
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Any, Tuple
import argparse

# 可選依賴：如果有的話會提供更詳細分析
try:
    import jieba
    import jieba.analyse
    JIEBA_AVAILABLE = True
except ImportError:
    JIEBA_AVAILABLE = False

try:
    from difflib import SequenceMatcher
    DIFFLIB_AVAILABLE = True
except ImportError:
    DIFFLIB_AVAILABLE = False


class ChunksQualityChecker:
    """Chunks品質檢查器"""
    
    def __init__(self, chunks_file: str):
        self.chunks_file = Path(chunks_file)
        self.chunks: List[Dict[str, Any]] = []
        self.stats = defaultdict(int)
        self.quality_issues = defaultdict(list)
        
        # 載入chunks
        self._load_chunks()
    
    def _load_chunks(self):
        """載入chunks檔案"""
        print(f"📁 載入檔案: {self.chunks_file}")
        
        if not self.chunks_file.exists():
            raise FileNotFoundError(f"找不到檔案: {self.chunks_file}")
        
        try:
            with open(self.chunks_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                        if 'text' in chunk:
                            self.chunks.append(chunk)
                        else:
                            self.quality_issues['malformed_json'].append(f"Line {line_num}: 缺少text欄位")
                    except json.JSONDecodeError as e:
                        self.quality_issues['json_errors'].append(f"Line {line_num}: {e}")
        except Exception as e:
            print(f"❌ 載入失敗: {e}")
            sys.exit(1)
        
        print(f"✅ 成功載入 {len(self.chunks)} 個 chunks")
    
    def analyze_basic_stats(self) -> Dict[str, Any]:
        """基本統計分析"""
        print("\n📊 === 基本統計分析 ===")
        
        lengths = [len(chunk['text']) for chunk in self.chunks]
        sources = [chunk.get('source', 'unknown') for chunk in self.chunks]
        pages = [(chunk.get('source', 'unknown'), chunk.get('page', 0)) for chunk in self.chunks]
        
        stats = {
            'total_chunks': len(self.chunks),
            'unique_sources': len(set(sources)),
            'total_pages': len(set(pages)),
            'avg_length': sum(lengths) / len(lengths) if lengths else 0,
            'min_length': min(lengths) if lengths else 0,
            'max_length': max(lengths) if lengths else 0,
            'length_std': self._calculate_std(lengths),
        }
        
        # 長度分布
        length_ranges = {
            'very_short': sum(1 for l in lengths if l < 100),
            'short': sum(1 for l in lengths if 100 <= l < 500),
            'medium': sum(1 for l in lengths if 500 <= l < 1000),
            'long': sum(1 for l in lengths if 1000 <= l < 2000),
            'very_long': sum(1 for l in lengths if l >= 2000),
        }
        
        print(f"📈 總chunks數: {stats['total_chunks']}")
        print(f"📚 來源文件: {stats['unique_sources']} 個")
        print(f"📄 總頁面數: {stats['total_pages']}")
        print(f"📏 平均長度: {stats['avg_length']:.1f} 字元")
        print(f"📐 長度範圍: {stats['min_length']} ~ {stats['max_length']} 字元")
        print(f"📊 標準差: {stats['length_std']:.1f}")
        
        print("\n📏 長度分布:")
        total = stats['total_chunks']
        for range_name, count in length_ranges.items():
            percentage = (count / total * 100) if total > 0 else 0
            print(f"  {range_name:12}: {count:4d} ({percentage:5.1f}%)")
        
        return {**stats, 'length_distribution': length_ranges}
    
    def analyze_text_quality(self) -> Dict[str, Any]:
        """文字品質分析"""
        print("\n🔍 === 文字品質分析 ===")
        
        language_stats = {'chinese': 0, 'english': 0, 'mixed': 0, 'other': 0}
        encoding_issues = []
        truncation_issues = []
        special_char_stats = Counter()
        
        for i, chunk in enumerate(self.chunks):
            text = chunk['text']
            
            # 語言檢測
            chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
            english_chars = len(re.findall(r'[a-zA-Z]', text))
            total_chars = len(text)
            
            if chinese_chars > total_chars * 0.5:
                language_stats['chinese'] += 1
            elif english_chars > total_chars * 0.3:
                if chinese_chars > total_chars * 0.1:
                    language_stats['mixed'] += 1
                else:
                    language_stats['english'] += 1
            else:
                language_stats['other'] += 1
            
            # 特殊字符統計
            special_chars = re.findall(r'[^\w\s\u4e00-\u9fff，。！？；：""''（）【】\-\.\,\!\?\;\:]', text)
            special_char_stats.update(special_chars)
            
            # 編碼問題檢測
            if ' ' in text or text.count('\\') > text.count('\\n') + text.count('\\"'):
                encoding_issues.append(i)
            
            # 截斷問題檢測
            if text.endswith('...') or (not text.endswith(('。', '.', '!', '?', '！', '？')) and len(text) > 100):
                truncation_issues.append(i)
        
        print(f"🌐 語言分布:")
        total = len(self.chunks)
        for lang, count in language_stats.items():
            percentage = (count / total * 100) if total > 0 else 0
            print(f"  {lang:10}: {count:4d} ({percentage:5.1f}%)")
        
        print(f"\n⚠️  品質問題:")
        print(f"  編碼問題: {len(encoding_issues)} 個")
        print(f"  截斷問題: {len(truncation_issues)} 個")
        
        if special_char_stats:
            print(f"\n🔣 特殊字符 TOP 5:")
            for char, count in special_char_stats.most_common(5):
                print(f"  '{char}': {count} 次")
        
        return {
            'language_distribution': language_stats,
            'encoding_issues': encoding_issues,
            'truncation_issues': truncation_issues,
            'special_characters': dict(special_char_stats.most_common(10))
        }
    
    def analyze_semantic_integrity(self) -> Dict[str, Any]:
        """語意完整性分析"""
        print("\n🧠 === 語意完整性分析 ===")
        
        sentence_patterns = {
            'complete_sentences': 0,
            'incomplete_sentences': 0,
            'bullet_points': 0,
            'tables': 0,
            'code_blocks': 0
        }
        
        paragraph_issues = []
        context_breaks = []
        
        for i, chunk in enumerate(self.chunks):
            text = chunk['text'].strip()
            
            # 句子完整性檢查
            sentences = re.split(r'[。！？\.\!\?]\s*', text)
            complete_count = 0
            for sentence in sentences:
                if len(sentence.strip()) > 5:  # 忽略太短的片段
                    if sentence.strip().endswith(('。', '.', '!', '?', '！', '？')):
                        complete_count += 1
                    else:
                        # 檢查是否是列表項或表格
                        if re.match(r'^\s*[\d\-\*\•]\s*', sentence) or '\t' in sentence:
                            sentence_patterns['bullet_points'] += 1
                        elif '|' in sentence and sentence.count('|') > 2:
                            sentence_patterns['tables'] += 1
                        elif any(keyword in sentence for keyword in ['def ', 'class ', 'import ', '```']):
                            sentence_patterns['code_blocks'] += 1
                        else:
                            sentence_patterns['incomplete_sentences'] += 1
            
            if complete_count > 0:
                sentence_patterns['complete_sentences'] += complete_count
            
            # 段落連貫性檢查
            paragraphs = text.split('\n\n')
            if len(paragraphs) > 1:
                for j in range(len(paragraphs) - 1):
                    # 簡單的上下文連貫性檢查
                    current = paragraphs[j].strip()
                    next_para = paragraphs[j + 1].strip()
                    if current and next_para and not self._has_topic_continuity(current, next_para):
                        context_breaks.append((i, j))
        
        print(f"📝 句子模式分析:")
        for pattern, count in sentence_patterns.items():
            print(f"  {pattern:20}: {count}")
        
        print(f"\n🔗 連貫性問題: {len(context_breaks)} 處")
        
        return {
            'sentence_patterns': sentence_patterns,
            'context_breaks': context_breaks
        }
    
    def analyze_content_overlap(self, similarity_threshold: float = 0.8) -> Dict[str, Any]:
        """內容重複分析"""
        print("\n🔄 === 內容重複分析 ===")
        
        if not DIFFLIB_AVAILABLE:
            print("⚠️  未安裝difflib，跳過相似度分析")
            return {}
        
        duplicates = []
        high_similarity_pairs = []
        
        print(f"🔍 檢查 {len(self.chunks)} chunks 的相似度...")
        
        # 只檢查前100個chunks的相似度（避免計算量過大）
        sample_size = min(100, len(self.chunks))
        for i in range(sample_size):
            for j in range(i + 1, sample_size):
                text1 = self.chunks[i]['text']
                text2 = self.chunks[j]['text']
                
                similarity = SequenceMatcher(None, text1, text2).ratio()
                
                if similarity >= similarity_threshold:
                    if similarity > 0.95:
                        duplicates.append((i, j, similarity))
                    else:
                        high_similarity_pairs.append((i, j, similarity))
        
        print(f"🔴 完全重複: {len(duplicates)} 對")
        print(f"🟡 高相似度: {len(high_similarity_pairs)} 對")
        
        return {
            'duplicates': duplicates,
            'high_similarity_pairs': high_similarity_pairs
        }
    
    def analyze_domain_characteristics(self) -> Dict[str, Any]:
        """領域特性分析"""
        print("\n🎓 === 領域特性分析 ===")
        
        technical_terms = Counter()
        citation_patterns = []
        figure_references = []
        table_references = []
        
        # 常見的技術/學術詞彙模式
        tech_patterns = [
            r'\b[A-Z]{2,}\b',  # 縮寫
            r'\b\d+\.\d+\b',   # 版本號或數值
            r'\([^)]*\d{4}[^)]*\)',  # 包含年份的引用
            r'Figure\s+\d+|圖\s*\d+',  # 圖表引用
            r'Table\s+\d+|表\s*\d+',   # 表格引用
            r'Section\s+\d+|第.*章|第.*節',  # 章節引用
        ]
        
        for i, chunk in enumerate(self.chunks):
            text = chunk['text']
            
            # 技術術語統計
            for pattern in tech_patterns:
                matches = re.findall(pattern, text)
                technical_terms.update(matches)
            
            # 引用模式
            citations = re.findall(r'\[[^\]]*\d+[^\]]*\]|\([^)]*\d{4}[^)]*\)', text)
            citation_patterns.extend(citations)
            
            # 圖表引用
            figures = re.findall(r'Figure\s+\d+[\.\d]*|圖\s*\d+[\.\d]*', text, re.IGNORECASE)
            figure_references.extend(figures)
            
            tables = re.findall(r'Table\s+\d+[\.\d]*|表\s*\d+[\.\d]*', text, re.IGNORECASE)
            table_references.extend(tables)
        
        print(f"🔬 技術特徵:")
        print(f"  技術術語: {len(technical_terms)} 種")
        print(f"  引用模式: {len(citation_patterns)} 個")
        print(f"  圖表引用: {len(figure_references)} 個")
        print(f"  表格引用: {len(table_references)} 個")
        
        if technical_terms:
            print(f"\n🏷️  常見技術術語 TOP 10:")
            for term, count in technical_terms.most_common(10):
                print(f"  {term}: {count}")
        
        return {
            'technical_terms': dict(technical_terms.most_common(20)),
            'citation_count': len(citation_patterns),
            'figure_references': len(figure_references),
            'table_references': len(table_references)
        }
    
    def generate_recommendations(self, analysis_results: Dict[str, Any]) -> List[str]:
        """產生改善建議"""
        recommendations = []
        
        # 基於統計結果給建議
        basic_stats = analysis_results.get('basic_stats', {})
        text_quality = analysis_results.get('text_quality', {})
        semantic = analysis_results.get('semantic_integrity', {})
        
        if basic_stats.get('avg_length', 0) < 300:
            recommendations.append("⚠️  平均chunk長度偏短，建議增加chunk_size參數")
        
        if basic_stats.get('avg_length', 0) > 2000:
            recommendations.append("⚠️  平均chunk長度過長，建議減少chunk_size參數")
        
        length_dist = basic_stats.get('length_distribution', {})
        if length_dist.get('very_short', 0) > len(self.chunks) * 0.1:
            recommendations.append("⚠️  過多極短chunks，建議調整最小長度過濾")
        
        if text_quality.get('encoding_issues'):
            recommendations.append("❌ 發現編碼問題，請檢查原始文件編碼")
        
        if text_quality.get('truncation_issues'):
            recommendations.append("❌ 發現截斷問題，建議調整overlap參數或分隔符設定")
        
        lang_dist = text_quality.get('language_distribution', {})
        if lang_dist.get('mixed', 0) > len(self.chunks) * 0.3:
            recommendations.append("ℹ️  中英混雜內容較多，適合多語言embedding模型")
        
        if semantic.get('context_breaks'):
            recommendations.append("⚠️  發現上下文斷裂，建議增加overlap或調整分割策略")
        
        return recommendations
    
    def run_full_analysis(self) -> Dict[str, Any]:
        """執行完整分析"""
        print("🚀 開始全面chunks品質分析...\n")
        
        results = {}
        
        try:
            results['basic_stats'] = self.analyze_basic_stats()
            results['text_quality'] = self.analyze_text_quality()
            results['semantic_integrity'] = self.analyze_semantic_integrity()
            results['content_overlap'] = self.analyze_content_overlap()
            results['domain_characteristics'] = self.analyze_domain_characteristics()
            
            # 產生建議
            recommendations = self.generate_recommendations(results)
            
            print("\n" + "="*60)
            print("📋 === 改善建議 ===")
            if recommendations:
                for i, rec in enumerate(recommendations, 1):
                    print(f"{i:2d}. {rec}")
            else:
                print("✅ Chunks品質良好，無明顯問題")
            
            print("\n" + "="*60)
            print("✅ 分析完成！")
            
        except Exception as e:
            print(f"❌ 分析過程出錯: {e}")
            import traceback
            traceback.print_exc()
        
        return results
    
    def _calculate_std(self, values: List[float]) -> float:
        """計算標準差"""
        if not values:
            return 0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5
    
    def _has_topic_continuity(self, text1: str, text2: str) -> bool:
        """簡單的主題連貫性檢查"""
        # 簡化版本：檢查是否有共同關鍵詞
        if JIEBA_AVAILABLE:
            words1 = set(jieba.lcut(text1))
            words2 = set(jieba.lcut(text2))
            common_words = words1 & words2
            return len(common_words) >= 2
        else:
            # 基礎版本：檢查英文單詞重疊
            words1 = set(re.findall(r'\b[a-zA-Z]{3,}\b', text1.lower()))
            words2 = set(re.findall(r'\b[a-zA-Z]{3,}\b', text2.lower()))
            common_words = words1 & words2
            return len(common_words) >= 1


def main():
    parser = argparse.ArgumentParser(description="Chunks品質檢查工具")
    parser.add_argument("--input", default="indices/chunks.jsonl", help="chunks.jsonl檔案路徑")
    parser.add_argument("--output", help="結果輸出檔案（可選）")
    
    args = parser.parse_args()
    
    try:
        checker = ChunksQualityChecker(args.input)
        results = checker.run_full_analysis()
        
        if args.output:
            output_path = Path(args.output)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n📁 結果已保存到: {output_path}")
            
    except KeyboardInterrupt:
        print("\n🛑 用戶中斷")
    except Exception as e:
        print(f"❌ 執行失敗: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()