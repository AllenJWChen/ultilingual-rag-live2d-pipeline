最小可用 LLM Router（支援 OpenAI / Azure OpenAI / 本地 OpenAI 相容端點（如 Ollama / OpenWebUI）/ Mock）
- 介面：get_llm(role) -> callable(prompt: str) -> str
- 角色 role："question" | "answer" | "judge" | "final"

環境變數（可寫入 .env）：
  LLM_PROVIDER=openai | azure | mock
  OPENAI_API_KEY=...                # openai 與本地相容端點都用這一個變數
  OPENAI_BASE_URL=http://localhost:11434/v1   # 若連 Ollama / OpenWebUI（OpenAI 相容）
  OPENAI_ORG=...                    # 選填
  AZURE_OPENAI_ENDPOINT=...         # 只有 azure 需要
  AZURE_OPENAI_API_KEY=...          # 只有 azure 需要
  AZURE_OPENAI_API_VERSION=2024-06-01

  MODEL_QUESTION=...  # 各角色模型；若未填，會用 MODEL_DEFAULT
  MODEL_ANSWER=...
  MODEL_JUDGE=...
  MODEL_FINAL=...
  MODEL_DEFAULT=gpt-4o-mini  # 或者是你本地模型的名稱（例如 llama3.1:8b-instruct）
"""
from __future__ import annotations
import os
from typing import Callable

# 溫度預設（可依需求調整）
ROLE_TEMPS = {
    "question": float(os.getenv("TEMP_QUESTION", 0.2)),
    "answer": float(os.getenv("TEMP_ANSWER", 0.6)),
    "judge": float(os.getenv("TEMP_JUDGE", 0.1)),
    "final": float(os.getenv("TEMP_FINAL", 0.3)),
}


def _resolve_model(role: str) -> str:
    return os.getenv(f"MODEL_{role.upper()}") or os.getenv("MODEL_DEFAULT", "gpt-4o-mini")


# ---- Provider: OpenAI / 本地相容端點（含 Ollama, OpenWebUI） ----

def _openai_client():
    try:
        from openai import OpenAI
    except Exception as e:
        raise RuntimeError("Please `pip install openai>=1.0.0`. Error: %s" % e)

    base_url = os.getenv("OPENAI_BASE_URL")  # 例如 http://localhost:11434/v1
    api_key = os.getenv("OPENAI_API_KEY", "sk-xxxx")
    org = os.getenv("OPENAI_ORG")

    return OpenAI(api_key=api_key, base_url=base_url, organization=org)


def _mk_openai_callable(role: str) -> Callable[[str], str]:
    client = _openai_client()
    model = _resolve_model(role)
    temperature = ROLE_TEMPS[role]

    def _call(prompt: str) -> str:
        # 此處我們讓 prompt 包含 [SYSTEM]/[USER] 標頭；若沒有，就合併成 user content 即可。
        msgs = [{"role": "user", "content": prompt}]
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()

    return _call


# ---- Provider: Azure OpenAI ----

def _azure_client():
    try:
        from openai import AzureOpenAI
    except Exception as e:
        raise RuntimeError("Please `pip install openai>=1.0.0`. Error: %s" % e)

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
    if not endpoint or not api_key:
        raise RuntimeError("Missing AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY")
    return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)


def _mk_azure_callable(role: str) -> Callable[[str], str]:
    client = _azure_client()
    # Azure 的 model 名稱通常是部署名，請在 MODEL_* 指定部署名
    model = _resolve_model(role)
    temperature = ROLE_TEMPS[role]

    def _call(prompt: str) -> str:
        msgs = [{"role": "user", "content": prompt}]
        resp = client.chat.completions.create(
            model=model,
            messages=msgs,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()

    return _call


# ---- Provider: Mock（方便在沒有 API Key 的情況下跑通流程） ----
import json as _json

def _mk_mock_callable(role: str) -> Callable[[str], str]:
    def _call(prompt: str) -> str:
        if role == "question":
            return _json.dumps({
                "normalized_zh": "請以矽光子主要市場為主題進行查詢",
                "normalized_en": "Search for the main markets of silicon photonics",
                "keywords_zh": ["矽光子", "市場", "數據通訊", "資料中心"],
                "keywords_en": ["silicon photonics", "market", "datacom", "transceiver"],
                "queries": [
                    "矽光子 主要 市場", 
                    "silicon photonics market datacom transceivers",
                    "silicon photonics other markets lidar"],
            }, ensure_ascii=False)
        if role == "judge":
            return _json.dumps({
                "outline": "(mock) 保守結論：以數據中心/光通訊為主，其次 LiDAR/感測與超算互連。",
                "issues": [],
                "todo_keywords": [],
                "verdict": "PASS",
            }, ensure_ascii=False)
        # answer/final 就回個占位字串
        return "(mock) This is a placeholder response for role=%s." % role
    return _call


# ---- Factory ----

def get_llm(role: str) -> Callable[[str], str]:
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    if provider == "openai" or (provider == "ollama"):
        return _mk_openai_callable(role)
    if provider == "azure":
        return _mk_azure_callable(role)
    # fallback
    return _mk_mock_callable(role)
