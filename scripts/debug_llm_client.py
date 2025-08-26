# -*- coding: utf-8 -*-
"""
LLM客戶端調試和修復版本
解決JSON解析錯誤和API調用問題

主要修復：
1. 增強的JSON解析和清理
2. 更好的錯誤處理和重試機制
3. 詳細的調試信息
4. 多種LLM服務支持
"""

import json
import re
import time
import requests
from typing import List, Dict, Optional, Union
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EnhancedLLMClient:
    """
    增強版LLM客戶端
    支持多種LLM服務，增強錯誤處理
    """
    
    def __init__(self, service="ollama", base_url="http://localhost:11434", 
                 model="llama3.1:latest", debug=True):
        self.service = service
        self.base_url = base_url
        self.model = model
        self.debug = debug
        
        # API配置
        self.config = {
            "timeout": 60,
            "max_retries": 3,
            "retry_delay": 2
        }
        
        print(f"[LLM] 初始化 {service} 客戶端")
        print(f"      服務器: {base_url}")
        print(f"      模型: {model}")
        print(f"      調試模式: {debug}")
    
    def generate_keywords(self, text: str, n: int = 3, lang: str = "en", 
                         content_type: str = "general") -> List[str]:
        """
        生成關鍵字 - 增強版
        """
        try:
            # 構建提示詞
            prompt = self._build_keyword_prompt(text, n, lang, content_type)
            
            # 調用LLM
            raw_response = self._call_llm_with_retries(prompt)
            
            # 解析和清理響應
            keywords = self._parse_keyword_response(raw_response, n, lang)
            
            return keywords
            
        except Exception as e:
            logger.error(f"關鍵字生成失敗: {e}")
            return self._generate_fallback_keywords(lang, n)
    
    def _call_llm_with_retries(self, prompt: str) -> str:
        """
        帶重試機制的LLM調用
        """
        last_error = None
        
        for attempt in range(self.config["max_retries"]):
            try:
                if self.debug:
                    logger.info(f"[嘗試 {attempt + 1}/{self.config['max_retries']}] 調用LLM")
                
                if self.service == "ollama":
                    response = self._call_ollama(prompt)
                elif self.service == "openai":
                    response = self._call_openai(prompt)
                else:
                    raise ValueError(f"不支持的LLM服務: {self.service}")
                
                if self.debug:
                    logger.info(f"[成功] LLM響應長度: {len(response)} 字符")
                    logger.debug(f"[響應預覽] {response[:200]}...")
                
                return response
                
            except Exception as e:
                last_error = e
                logger.warning(f"[嘗試 {attempt + 1}] 失敗: {e}")
                
                if attempt < self.config["max_retries"] - 1:
                    delay = self.config["retry_delay"] * (attempt + 1)
                    logger.info(f"等待 {delay} 秒後重試...")
                    time.sleep(delay)
        
        raise last_error
    
    def _call_ollama(self, prompt: str) -> str:
        """
        調用Ollama API - 修復版本
        """
        url = f"{self.base_url}/api/generate"
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,  # 關鍵：使用非流式模式
            "options": {
                "temperature": 0.3,
                "top_p": 0.9,
                "num_predict": 200,
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if self.debug:
            logger.debug(f"[Ollama] 請求URL: {url}")
            logger.debug(f"[Ollama] 請求載荷: {json.dumps(payload, indent=2)}")
        
        try:
            response = requests.post(
                url, 
                json=payload, 
                headers=headers,
                timeout=self.config["timeout"]
            )
            
            if self.debug:
                logger.debug(f"[Ollama] 響應狀態: {response.status_code}")
                logger.debug(f"[Ollama] 響應頭: {dict(response.headers)}")
                logger.debug(f"[Ollama] 原始響應: {response.text[:500]}...")
            
            if response.status_code != 200:
                raise requests.RequestException(f"HTTP {response.status_code}: {response.text}")
            
            # 解析響應
            try:
                response_data = response.json()
                return response_data.get("response", "").strip()
                
            except json.JSONDecodeError as e:
                logger.error(f"[Ollama] JSON解析失敗: {e}")
                logger.error(f"[Ollama] 原始響應: {response.text}")
                
                # 嘗試從原始文本中提取
                return self._extract_from_raw_response(response.text)
        
        except requests.RequestException as e:
            raise Exception(f"網絡請求失敗: {e}")
    
    def _call_openai(self, prompt: str) -> str:
        """
        調用OpenAI API
        """
        try:
            import openai
        except ImportError:
            raise ImportError("請安裝openai: pip install openai")
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            raise Exception(f"OpenAI API調用失敗: {e}")
    
    def _extract_from_raw_response(self, raw_text: str) -> str:
        """
        從原始響應中提取有用內容
        """
        if self.debug:
            logger.info("[嘗試] 從原始響應提取內容")
        
        # 嘗試找到JSON部分
        json_patterns = [
            r'\[.*?\]',  # 數組格式
            r'\{.*?\}',  # 對象格式
        ]
        
        for pattern in json_patterns:
            matches = re.findall(pattern, raw_text, re.DOTALL)
            if matches:
                if self.debug:
                    logger.info(f"[找到] JSON模式: {matches[0][:100]}...")
                return matches[0]
        
        # 如果找不到JSON，返回原始文本
        return raw_text.strip()
    
    def _parse_keyword_response(self, response: str, n: int, lang: str) -> List[str]:
        """
        解析關鍵字響應 - 增強版
        """
        if not response or not response.strip():
            logger.warning("LLM響應為空")
            return self._generate_fallback_keywords(lang, n)
        
        if self.debug:
            logger.info(f"[解析] 響應內容: {response[:200]}...")
        
        # 方法1: 嘗試直接JSON解析
        try:
            # 清理響應
            cleaned_response = self._clean_json_response(response)
            keywords = json.loads(cleaned_response)
            
            if isinstance(keywords, list) and all(isinstance(kw, str) for kw in keywords):
                filtered_keywords = [kw.strip() for kw in keywords if kw.strip()]
                if self.debug:
                    logger.info(f"[成功] JSON解析: {filtered_keywords}")
                return filtered_keywords[:n]
                
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析失敗: {e}")
        
        # 方法2: 正則表達式提取
        keywords = self._extract_keywords_with_regex(response)
        if keywords:
            if self.debug:
                logger.info(f"[成功] 正則提取: {keywords}")
            return keywords[:n]
        
        # 方法3: 簡單分割
        keywords = self._extract_keywords_simple(response)
        if keywords:
            if self.debug:
                logger.info(f"[成功] 簡單分割: {keywords}")
            return keywords[:n]
        
        # 方法4: 後備方案
        logger.warning("所有解析方法都失敗，使用後備關鍵字")
        return self._generate_fallback_keywords(lang, n)
    
    def _clean_json_response(self, response: str) -> str:
        """
        清理JSON響應
        """
        # 移除markdown代碼塊
        response = re.sub(r'```json\s*', '', response)
        response = re.sub(r'```\s*', '', response)
        
        # 移除多餘的文字
        response = response.strip()
        
        # 尋找JSON部分
        json_match = re.search(r'(\[.*?\]|\{.*?\})', response, re.DOTALL)
        if json_match:
            response = json_match.group(1)
        
        # 修復常見的JSON問題
        response = response.replace('\n', ' ')
        response = response.replace('\t', ' ')
        response = re.sub(r'\s+', ' ', response)
        
        return response.strip()
    
    def _extract_keywords_with_regex(self, text: str) -> List[str]:
        """
        使用正則表達式提取關鍵字
        """
        keywords = []
        
        # 模式1: 引號包圍的詞
        quoted_words = re.findall(r'"([^"]*)"', text)
        keywords.extend([w.strip() for w in quoted_words if w.strip()])
        
        # 模式2: 列表項
        list_items = re.findall(r'[-*•]\s*(.+)', text)
        keywords.extend([item.strip().rstrip(',').strip('"\'') for item in list_items])
        
        # 模式3: 編號列表
        numbered_items = re.findall(r'\d+[.)]\s*(.+)', text)
        keywords.extend([item.strip().rstrip(',').strip('"\'') for item in numbered_items])
        
        # 過濾和清理
        cleaned_keywords = []
        for kw in keywords:
            kw = kw.strip()
            if kw and len(kw) > 1 and len(kw) < 50:
                cleaned_keywords.append(kw)
        
        return cleaned_keywords
    
    def _extract_keywords_simple(self, text: str) -> List[str]:
        """
        簡單分割提取關鍵字
        """
        # 按常見分隔符分割
        separators = [',', '，', ';', '；', '\n', '|']
        
        for sep in separators:
            if sep in text:
                parts = text.split(sep)
                keywords = []
                
                for part in parts:
                    cleaned = part.strip().strip('"\'()[]{}')
                    if cleaned and len(cleaned) > 1 and len(cleaned) < 50:
                        keywords.append(cleaned)
                
                if len(keywords) >= 2:  # 至少要有2個有效關鍵字
                    return keywords
        
        return []
    
    def _generate_fallback_keywords(self, lang: str, n: int = 3) -> List[str]:
        """
        生成後備關鍵字
        """
        if "zh" in lang.lower():
            return [f"關鍵詞{i+1}" for i in range(n)]
        else:
            return [f"keyword{i+1}" for i in range(n)]
    
    def _build_keyword_prompt(self, text: str, n: int, lang: str, content_type: str) -> str:
        """
        構建關鍵字提示詞
        """
        # 根據語言選擇提示詞
        if lang.lower() in ["zh", "chinese"]:
            prompt = f"""請為以下中文內容提取 {n} 個最重要的關鍵字。

要求：
1. 關鍵字必須準確反映內容
2. 使用中文詞彙
3. 輸出格式必須是JSON數組，例如：["關鍵字1", "關鍵字2", "關鍵字3"]
4. 只輸出JSON，不要其他解釋文字

內容：
{text[:800]}

關鍵字："""

        else:
            prompt = f"""Please extract {n} most important keywords from the following English content.

Requirements:
1. Keywords must accurately reflect the content
2. Use English terms
3. Output format must be JSON array, for example: ["keyword1", "keyword2", "keyword3"]
4. Only output JSON, no other explanatory text

Content:
{text[:800]}

Keywords:"""
        
        return prompt
    
    def test_connection(self) -> bool:
        """
        測試LLM連接
        """
        try:
            logger.info(f"[測試] 連接到 {self.service} 服務")
            
            test_prompt = "請輸出JSON格式: [\"test\"]"
            response = self._call_llm_with_retries(test_prompt)
            
            logger.info(f"[測試成功] 響應: {response}")
            return True
            
        except Exception as e:
            logger.error(f"[測試失敗] {e}")
            return False


# ================== 修復版的關鍵字生成函數 ==================

def generate_keywords_fixed(text: str, n: int = 3, lang: str = "en", 
                           content_type: Optional[str] = None, 
                           llm_client: Optional[EnhancedLLMClient] = None) -> List[str]:
    """
    修復版關鍵字生成函數
    """
    if llm_client is None:
        # 使用默認的增強客戶端
        llm_client = EnhancedLLMClient(debug=True)
    
    try:
        return llm_client.generate_keywords(text, n, lang, content_type or "general")
    except Exception as e:
        logger.error(f"關鍵字生成徹底失敗: {e}")
        # 最終後備方案
        if "zh" in lang.lower():
            return [f"後備關鍵字{i+1}" for i in range(n)]
        else:
            return [f"fallback_kw_{i+1}" for i in range(n)]


# ================== 診斷和測試工具 ==================

def diagnose_llm_issue():
    """
    診斷LLM連接問題
    """
    print("🔍 LLM連接診斷工具")
    print("=" * 40)
    
    # 測試不同配置
    configs = [
        {"service": "ollama", "base_url": "http://localhost:11434", "model": "llama3.1:latest"},
        {"service": "ollama", "base_url": "http://localhost:11434", "model": "llama3.2:latest"}, 
        {"service": "ollama", "base_url": "http://127.0.0.1:11434", "model": "llama3.1:latest"},
    ]
    
    for i, config in enumerate(configs, 1):
        print(f"\n📋 測試配置 {i}:")
        print(f"   服務: {config['service']}")
        print(f"   地址: {config['base_url']}")  
        print(f"   模型: {config['model']}")
        
        try:
            client = EnhancedLLMClient(**config, debug=True)
            
            if client.test_connection():
                print("✅ 連接成功！")
                
                # 測試關鍵字生成
                test_text = "This is a test document about artificial intelligence and machine learning."
                keywords = client.generate_keywords(test_text, 3, "en")
                print(f"🔑 測試關鍵字: {keywords}")
                
                print(f"🎉 配置 {i} 可以正常使用！")
                return client
            else:
                print("❌ 連接失敗")
                
        except Exception as e:
            print(f"❌ 配置 {i} 出錯: {e}")
    
    print("\n⚠️  所有配置都失敗了")
    print("建議檢查：")
    print("1. Ollama是否正在運行: ollama serve")
    print("2. 模型是否已下載: ollama pull llama3.1:latest")
    print("3. 防火牆設置")
    print("4. 端口是否被佔用")
    
    return None


def quick_fix_demo():
    """
    快速修復演示
    """
    print("🛠️ 快速修復演示")
    print("=" * 30)
    
    # 診斷問題
    working_client = diagnose_llm_issue()
    
    if working_client:
        print("\n🎯 使用可用的客戶端測試:")
        
        test_cases = [
            ("台積電是全球最大的半導體代工廠", "zh"),
            ("TSMC is the world's largest semiconductor foundry", "en")
        ]
        
        for text, lang in test_cases:
            print(f"\n📝 測試文本 ({lang}): {text[:50]}...")
            try:
                keywords = working_client.generate_keywords(text, 3, lang)
                print(f"✅ 生成關鍵字: {keywords}")
            except Exception as e:
                print(f"❌ 失敗: {e}")
    
    else:
        print("\n❌ 無法建立正常連接")
        print("建議使用模擬模式或檢查Ollama設置")


if __name__ == "__main__":
    quick_fix_demo()