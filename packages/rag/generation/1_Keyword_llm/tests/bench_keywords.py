# -*- coding: utf-8 -*-
"""
bench_keywords.py
跑不同 workers 併發度，壓測 make_keywords 的速度 & GPU 用量
輸出：
  - data/bench/bench_keywords.csv（彙整結果）
  - data/bench/bench_w{N}.log（各次 stdout）
  - data/bench/chunk_k_w{N}.jsonl（各次輸出）

用法（PowerShell）：
  # 確保已啟動 ollama serve，且設定 OPENAI_COMPAT
  # 最快入門（跑 200 個 chunk，workers 1/2/4/8/16 各一次）：
  python scripts/bench_keywords.py --max-chunks 200

  # 自訂 workers、檔位：
  python scripts/bench_keywords.py --workers 1,4,8,16 --max-chunks 400 --langs zh,en

備註：
- 會自動讀取目前環境變數（LLM_MODE, OPENAI_BASE_URL, OPENAI_API_KEY, MODEL_KEYWORDS）
- 會把 OLLAMA_NUM_PARALLEL 設成與 workers 相同（如果你用 Ollama）
"""
import os
import sys
import csv
import time
import shlex
import signal
import shutil
import threading
import subprocess as sp
from pathlib import Path
from typing import List, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]  # 專案根目錄 (…/multilingual_rag_live2d_scaffold)
BENCH_DIR = ROOT / "data" / "bench"
BENCH_DIR.mkdir(parents=True, exist_ok=True)

def has_nvidia_smi() -> bool:
    return shutil.which("nvidia-smi") is not None

def gpu_sampler(stop_evt: threading.Event, samples: list):
    """每秒取一次 GPU 利用率/VRAM 使用量（若有 nvidia-smi）"""
    if not has_nvidia_smi(): 
        return
    q = "timestamp,index,name,utilization.gpu,memory.used,memory.total"
    args = ["nvidia-smi", f"--query-gpu={q}", "--format=csv,noheader,nounits"]
    while not stop_evt.is_set():
        try:
            out = sp.check_output(args, stderr=sp.DEVNULL, text=True, timeout=2)
            # 可能多張卡，取加總/最大：我們取「最大利用率」以及「最大記憶體使用」作為代表
            util_max = 0.0
            mem_used_max = 0.0
            mem_total_max = 0.0
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 6:
                    util = float(parts[3])  # %
                    used = float(parts[4])  # MiB
                    total = float(parts[5]) # MiB
                    if util > util_max: util_max = util
                    if used > mem_used_max: mem_used_max = used
                    if total > mem_total_max: mem_total_max = total
            samples.append((time.time(), util_max, mem_used_max, mem_total_max))
        except Exception:
            pass
        stop_evt.wait(1.0)

def agg_gpu(samples: list) -> Dict[str, float]:
    if not samples:
        return {"gpu_util_avg": 0.0, "gpu_util_max": 0.0, "vram_max_mb": 0.0}
    utils = [s[1] for s in samples]
    vrams = [s[2] for s in samples]
    return {
        "gpu_util_avg": sum(utils) / len(utils),
        "gpu_util_max": max(utils),
        "vram_max_mb": max(vrams),
    }

def run_once(workers: int, max_chunks: int, langs: str, index_dir: str) -> Dict[str, float]:
    """跑一次 make_keywords，回傳統計（秒數、行數、吞吐量、GPU 指標）"""
    out_path = BENCH_DIR / f"chunk_k_w{workers}.jsonl"
    log_path = BENCH_DIR / f"bench_w{workers}.log"
    if out_path.exists():
        out_path.unlink()

    # 以目前環境為基礎，覆蓋 OLLAMA_NUM_PARALLEL
    env = os.environ.copy()
    env.setdefault("LLM_MODE", "OPENAI_COMPAT")
    env.setdefault("OPENAI_BASE_URL", "http://localhost:11434/v1")
    env.setdefault("OPENAI_API_KEY", "ollama")
    env.setdefault("MODEL_KEYWORDS", "llama3.1:latest")
    env["OLLAMA_NUM_PARALLEL"] = str(workers)

    cmd = [
        sys.executable, "-m", "packages.rag.generation.Keyword_llm.make_keywords",
        "--index", index_dir,
        "--out", str(out_path),
        "--langs", langs,
        "--max-chunks", str(max_chunks),
        "--workers", str(workers),
        "--max-chars", "1600",
    ]

    # GPU 取樣
    stop_evt = threading.Event()
    samples: list = []
    sampler = threading.Thread(target=gpu_sampler, args=(stop_evt, samples), daemon=True)
    if has_nvidia_smi():
        sampler.start()

    t0 = time.perf_counter()
    with open(log_path, "w", encoding="utf-8") as lf:
        proc = sp.Popen(cmd, cwd=str(ROOT), env=env, stdout=lf, stderr=sp.STDOUT)
        try:
            proc.wait()
        except KeyboardInterrupt:
            proc.send_signal(signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT)
            proc.wait()

    t1 = time.perf_counter()
    stop_evt.set()
    if sampler.is_alive():
        sampler.join(timeout=2)

    elapsed = t1 - t0
    # 估算輸出行數
    lines = 0
    if out_path.exists():
        try:
            with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
                for _ in f:
                    lines += 1
        except Exception:
            pass
    thru = (lines / elapsed) if elapsed > 0 else 0.0

    gpu = agg_gpu(samples)
    return {
        "workers": workers,
        "seconds": round(elapsed, 2),
        "lines": lines,
        "chunks_per_sec": round(thru, 2),
        "gpu_util_avg": round(gpu["gpu_util_avg"], 1),
        "gpu_util_max": round(gpu["gpu_util_max"], 1),
        "vram_max_mb": round(gpu["vram_max_mb"], 0),
    }

def parse_workers(s: str) -> List[int]:
    out = []
    for p in s.split(","):
        p = p.strip()
        if not p: continue
        out.append(int(p))
    return out

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Benchmark make_keywords with various workers.")
    ap.add_argument("--workers", default="1,2,4,8,16,24,32,48,64", help="逗號分隔，例如: 1,4,8,16")
    ap.add_argument("--max-chunks", type=int, default=200, help="每次跑多少 chunk（建議 100~500）")
    ap.add_argument("--langs", default="zh,en", help="語系，預設 zh,en")
    ap.add_argument("--index", default="indices", help="chunks.jsonl 所在資料夾")
    args = ap.parse_args(argv)

    workers_list = parse_workers(args.workers)
    print(f"[BENCH] workers = {workers_list}, max_chunks = {args.max_chunks}, langs = {args.langs}")
    print(f"[BENCH] index dir = {args.index}")
    results: List[Dict] = []

    for w in workers_list:
        print(f"\n[RUN] workers = {w} ...")
        stats = run_once(w, args.max_chunks, args.langs, args.index)
        print(f"   seconds={stats['seconds']}, lines={stats['lines']}, "
              f"chunks/s={stats['chunks_per_sec']}, "
              f"gpu(avg/max)={stats['gpu_util_avg']}/{stats['gpu_util_max']}%, "
              f"vram_max={stats['vram_max_mb']} MiB")
        results.append(stats)

    csv_path = BENCH_DIR / "bench_keywords.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        wtr = csv.DictWriter(f, fieldnames=[
            "workers", "seconds", "lines", "chunks_per_sec",
            "gpu_util_avg", "gpu_util_max", "vram_max_mb"
        ])
        wtr.writeheader()
        for r in results:
            wtr.writerow(r)

    print(f"\n[OK] CSV written → {csv_path}")
    print("\n[SUMMARY]")
    for r in results:
        print(f"  workers={r['workers']:>2} | {r['seconds']:>7}s | "
              f"{r['lines']:>4} lines | {r['chunks_per_sec']:>6} chunk/s | "
              f"GPU {r['gpu_util_avg']:>5.1f}% avg / {r['gpu_util_max']:>5.1f}% max | "
              f"VRAM {r['vram_max_mb']:>6.0f} MiB")

if __name__ == "__main__":
    main()
