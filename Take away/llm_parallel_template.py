# -*- coding: utf-8 -*-
"""
通用並行 LLM 派工模板 (預設 32 工人)
- 目的：一個檔搞定「關鍵字/回答/裁判」等任務，只要改 build_messages() 與 parse_response()
- 相容：OpenAI 相容 API (含 Ollama 的 /v1)
- 特點：ThreadPool 併發、指數回退重試、進度條、JSONL 輸入輸出

用法（PowerShell 範例）：
  $env:OPENAI_BASE_URL="http://localhost:11434/v1"     # Ollama OpenAI 相容模式
  $env:OPENAI_API_KEY="ollama"                         # 任意字串即可
  python scripts/llm_parallel_template.py `
    --in indices/chunks.jsonl `
    --out data/out_answer.jsonl `
    --task answer `
    --model llama3.1:latest `
    --workers 32

常見任務（--task）：
  keywords : 針對 item["text"] 產 3 個關鍵字
  answer   : 針對 item["text"] 回答 item["question"]
  judge    : 針對 item["text"] 評審 item["answer"] 與 item["question"]

資料格式（JSONL）：
  - 任務 keywords  需要欄位：text
  - 任務 answer    需要欄位：text, question
  - 任務 judge     需要欄位：text, question, answer
"""

from __future__ import annotations

import os, sys, json, time, math, traceback, argparse
from typing import Dict, Any, List, Iterable, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

import requests
from tqdm import tqdm

# =========================
# 可調參數（預設值）
# =========================
DEFAULT_WORKERS = 32
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 512
DEFAULT_MODEL = os.getenv("MODEL_KEYWORDS", "llama3.1:latest")  # 沿用你的變數命名
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "ollama")  # Ollama 隨意字串

# =========================
# 1) 任務專屬：訊息構造
#    依需求改這裡就能換任務
# =========================
def build_messages(item: Dict[str, Any], task: str) -> List[Dict[str, str]]:
    """
    回傳 OpenAI ChatCompletions messages 格式。
    你只需針對不同 task 改 system / user 提示。
    """
    if task == "keywords":
        text = (item.get("text") or "").strip()
        sys_prompt = "你是資料標註助理。請從輸入內容中萃取 3 個精準、不重複的關鍵字，回傳 JSON：{\"keywords\": [..]}。"
        user_prompt = f"內容：\n{text}\n\n產出語言：依內容語言。禁止贅詞與說明。"

    elif task == "answer":
        text = (item.get("text") or "").strip()
        question = (item.get("question") or "").strip()
        sys_prompt = "你是專業回答助理。請根據提供的知識回答問題。若無資訊，明確說明無法回答。回傳 JSON：{\"answer\": \"...\"}。"
        user_prompt = f"[知識]\n{text}\n\n[問題]\n{question}\n\n限制：嚴禁杜撰，必要時引用原文片段精簡回答。"

    elif task == "judge":
        text = (item.get("text") or "").strip()
        question = (item.get("question") or "").strip()
        answer = (item.get("answer") or "").strip()
        sys_prompt = (
            "你是嚴謹的評審，根據知識判定回答是否正確、是否有幻覺。"
            "回傳 JSON：{\"verdict\": \"correct|partial|wrong|insufficient\", \"reason\": \"...\"}。"
        )
        user_prompt = f"[知識]\n{text}\n\n[問題]\n{question}\n\n[回答]\n{answer}\n\n請嚴格對照知識。"

    else:
        raise ValueError(f"Unknown task: {task}")

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user",   "content": user_prompt},
    ]


# =========================
# 2) 任務專屬：模型輸出解析
#    依需求改這裡把 LLM 的文字轉成結構
# =========================
def parse_response(task: str, content: str) -> Dict[str, Any]:
    """
    嘗試從模型輸出中擷取 JSON（容錯）。
    """
    def _safe_json(s: str) -> Optional[Dict[str, Any]]:
        try:
            i = s.find("{"); j = s.rfind("}")
            if i != -1 and j != -1 and j > i:
                return json.loads(s[i:j+1])
        except Exception:
            return None
        return None

    data = _safe_json(content) or {}

    if task == "keywords":
        kws = data.get("keywords") or []
        if not isinstance(kws, list): kws = []
        kws = [str(x).strip() for x in kws if str(x).strip()]
        return {"keywords": kws[:3]}

    if task == "answer":
        ans = data.get("answer")
        if isinstance(ans, str) and ans.strip():
            return {"answer": ans.strip()}
        return {"answer": content.strip()[:1000]}  # 後備：整段截斷

    if task == "judge":
        verdict = str(data.get("verdict", "")).strip().lower()
        reason  = str(data.get("reason", "")).strip()
        if verdict not in {"correct", "partial", "wrong", "insufficient"}:
            verdict = "insufficient"
        return {"verdict": verdict, "reason": reason or content.strip()[:800]}

    return {"raw": content}


# =========================
# 3) OpenAI 相容：ChatCompletions 呼叫 + 重試
# =========================
def call_chat_completions(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: float = 120.0,
    max_retries: int = 4,
    backoff_base: float = 1.8,
) -> str:
    url = f"{OPENAI_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENAI_API_KEY}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
    }

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if r.status_code == 200:
                data = r.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                return content or ""
            else:
                last_err = RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        except Exception as e:
            last_err = e

        # backoff
        if attempt < max_retries:
            delay = backoff_base ** attempt + (0.1 * attempt)
            time.sleep(delay)

    raise last_err or RuntimeError("Unknown error during chat completions")


# =========================
# 4) 單筆任務執行
# =========================
def run_one(item: Dict[str, Any], task: str, model: str, temperature: float, max_tokens: int) -> Dict[str, Any]:
    msgs = build_messages(item, task)
    content = call_chat_completions(model=model, messages=msgs, temperature=temperature, max_tokens=max_tokens)
    parsed = parse_response(task, content)
    out = dict(item)  # 保留原欄位
    out.update(parsed)
    return out


# =========================
# 5) JSONL I/O
# =========================
def read_jsonl(path: str, limit: int = 0) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            s = line.strip()
            if not s:
                continue
            try:
                items.append(json.loads(s))
            except Exception:
                # 忽略壞行
                pass
            if limit and len(items) >= limit:
                break
    return items

def write_jsonl(path: str, rows: Iterable[Dict[str, Any]]):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# =========================
# 6) 主程式：並行派工
# =========================
def main():
    ap = argparse.ArgumentParser(description="通用並行 LLM 派工模板（預設 32 工人）")
    ap.add_argument("--in",   dest="inp", required=True, help="輸入 JSONL 檔（每行一筆任務資料）")
    ap.add_argument("--out",  dest="out", required=True, help="輸出 JSONL 檔")
    ap.add_argument("--task", choices=["keywords","answer","judge"], required=True, help="任務類型")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="模型名稱（OpenAI 相容）")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="並行工人數（預設 32）")
    ap.add_argument("--limit", type=int, default=0, help="僅處理前 N 筆（0 表示全部）")
    ap.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    args = ap.parse_args()

    items = read_jsonl(args.inp, limit=args.limit)
    if not items:
        print("[WARN] 無資料可處理。")
        return

    print(f"[info] items={len(items)}, task={args.task}, model={args.model}, workers={args.workers}")
    results: List[Dict[str, Any]] = []

    worker = partial(run_one, task=args.task, model=args.model,
                     temperature=args.temperature, max_tokens=args.max_tokens)

    # I/O bound（HTTP）→ ThreadPoolExecutor 最合適
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(worker, it) for it in items]
        for fut in tqdm(as_completed(futures), total=len(futures), desc=args.task, unit="item"):
            try:
                results.append(fut.result())
            except Exception as e:
                # 失敗也寫出錯誤，避免整體中斷
                results.append({"error": str(e), "trace": traceback.format_exc()[:2000]})

    write_jsonl(args.out, results)
    print(f"[OK] wrote {len(results)} lines → {args.out}")


if __name__ == "__main__":
    main()
