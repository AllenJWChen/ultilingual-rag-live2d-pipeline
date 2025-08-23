#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
bench.py - Answer LLM 統一性能測試腳本
支援基礎版本和高性能並行版本測試

用法：
# 基礎版本測試
python bench.py --mode basic --max-questions 50

# 並行版本測試 (預設)
python bench.py --workers 1,8,16,32 --max-questions 200

# 完整壓力測試
python bench.py --workers 8,16,24,32 --max-questions 1000
"""

import os
import sys
import csv
import json
import time
import threading
import subprocess as sp
import argparse
from pathlib import Path
from typing import List, Dict, Optional

# 測試結果輸出位置
TESTS_DIR = Path(__file__).parent
RESULTS_DIR = TESTS_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# 專案根目錄
PROJECT_ROOT = TESTS_DIR.parents[4]

def has_nvidia_smi() -> bool:
    return shutil.which("nvidia-smi") is not None

def gpu_monitor_thread(stop_event: threading.Event, samples: list):
    """GPU 監控線程"""
    if not has_nvidia_smi(): 
        return
    
    query = "timestamp,index,name,utilization.gpu,memory.used,memory.total"
    args = ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader,nounits"]
    
    while not stop_event.is_set():
        try:
            out = sp.check_output(args, stderr=sp.DEVNULL, text=True, timeout=2)
            
            util_max = 0.0
            mem_used_max = 0.0
            mem_total_max = 0.0
            
            for line in out.strip().splitlines():
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 6:
                    try:
                        util = float(parts[3])
                        mem_used = float(parts[4]) 
                        mem_total = float(parts[5])
                        
                        util_max = max(util_max, util)
                        mem_used_max = max(mem_used_max, mem_used)
                        mem_total_max = max(mem_total_max, mem_total)
                    except ValueError:
                        continue
            
            if util_max > 0:
                samples.append({
                    'timestamp': time.time(),
                    'gpu_util': util_max,
                    'vram_used': mem_used_max,
                    'vram_total': mem_total_max
                })
                
        except (sp.TimeoutExpired, sp.CalledProcessError):
            pass
        except KeyboardInterrupt:
            break
            
        time.sleep(1)

def run_benchmark(mode: str, workers: int, max_questions: int, 
                 questions_file: str, index_dir: str) -> Dict:
    """執行單次基準測試
    
    Args:
        mode: 'basic' 或 'parallel'
        workers: 並行工作數 (basic 模式忽略)
        max_questions: 最大問題數
        questions_file: 問題檔案路徑
        index_dir: 索引目錄路徑
    """
    
    if mode == 'basic':
        print(f"\n🚀 Testing Answer LLM (Basic Mode) - {max_questions} questions")
        module_name = "packages.rag.generation.Answer_llm.core"
        output_file = RESULTS_DIR / f"answers_basic_{max_questions}.jsonl"
        log_file = RESULTS_DIR / f"bench_basic_{max_questions}.log"
        workers_display = 1
    else:
        print(f"\n🚀 Testing Answer LLM (Parallel Mode) - {workers} workers, {max_questions} questions")
        module_name = "packages.rag.generation.Answer_llm.core_parallel"
        output_file = RESULTS_DIR / f"answers_w{workers}.jsonl"
        log_file = RESULTS_DIR / f"bench_w{workers}.log"
        workers_display = workers
    
    # 環境變數設定
    env = os.environ.copy()
    if mode == 'parallel':
        env["OLLAMA_NUM_PARALLEL"] = str(workers)
    
    # 建構命令
    cmd = [
        sys.executable, "-m", module_name,
        "--questions", str(questions_file),
        "--index", str(index_dir),
        "--out", str(output_file),
        "--max", str(max_questions)
    ]
    
    if mode == 'parallel':
        cmd.extend(["--workers", str(workers)])
    
    print(f"📝 Command: {' '.join(cmd)}")
    print(f"📁 Output: {output_file}")
    print(f"📋 Log: {log_file}")
    
    # GPU 監控
    gpu_samples = []
    gpu_stop = threading.Event()
    gpu_thread = threading.Thread(target=gpu_monitor_thread, args=(gpu_stop, gpu_samples))
    gpu_thread.start()
    
    start_time = time.time()
    
    try:
        # 執行命令
        with open(log_file, 'w', encoding='utf-8') as log_f:
            proc = sp.Popen(cmd, stdout=log_f, stderr=sp.STDOUT,
                          text=True, env=env, cwd=PROJECT_ROOT)
            proc.wait()
            returncode = proc.returncode
            
    except KeyboardInterrupt:
        print("\n⏹️  Benchmark interrupted by user")
        proc.terminate()
        returncode = -1
    finally:
        gpu_stop.set()
        gpu_thread.join()
    
    end_time = time.time()
    total_seconds = end_time - start_time
    
    # 分析結果
    success_count = 0
    fail_count = 0
    
    if output_file.exists():
        try:
            with open(output_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if data.get('status') == 'failed':
                                fail_count += 1
                            else:
                                success_count += 1
                        except:
                            pass
        except Exception as e:
            print(f"❌ Error reading output file: {e}")
    
    total_processed = success_count + fail_count
    throughput = total_processed / total_seconds if total_seconds > 0 else 0
    
    # GPU 統計
    gpu_util_avg = 0.0
    gpu_util_max = 0
    vram_max_mb = 0
    
    if gpu_samples:
        gpu_utils = [s['gpu_util'] for s in gpu_samples]
        vram_usages = [s['vram_used'] for s in gpu_samples]
        
        gpu_util_avg = sum(gpu_utils) / len(gpu_utils)
        gpu_util_max = int(max(gpu_utils))
        vram_max_mb = int(max(vram_usages)) if vram_usages else 0
    
    result = {
        'mode': mode,
        'workers': workers_display,
        'seconds': round(total_seconds, 2),
        'questions': total_processed,
        'success': success_count,
        'failed': fail_count,
        'throughput': round(throughput, 2),
        'gpu_util_avg': round(gpu_util_avg, 1),
        'gpu_util_max': gpu_util_max,
        'vram_max_mb': vram_max_mb,
        'returncode': returncode
    }
    
    print(f"⏱️  Time: {total_seconds:.2f}s")
    print(f"📊 Processed: {total_processed} questions ({success_count} success, {fail_count} failed)")
    print(f"🚀 Throughput: {throughput:.2f} Q/s")
    if gpu_samples:
        print(f"🎮 GPU Util: {gpu_util_avg:.1f}% avg, {gpu_util_max}% max")
        print(f"💾 VRAM: {vram_max_mb} MB max")
    
    return result

def main():
    parser = argparse.ArgumentParser(description="Answer LLM Performance Benchmark")
    
    # 模式選擇
    parser.add_argument("--mode", choices=['basic', 'parallel'], default='parallel',
                       help="Test mode: basic (single-threaded) or parallel (multi-threaded)")
    
    # 並行設定
    parser.add_argument("--workers", default="1,8,16,32",
                       help="Comma-separated worker counts for parallel mode")
    
    # 測試參數
    parser.add_argument("--max-questions", type=int, default=200,
                       help="Maximum questions per test")
    parser.add_argument("--questions", 
                       default=str(PROJECT_ROOT / "outputs" / "data" / "questions.jsonl"),
                       help="Questions file path")
    parser.add_argument("--index",
                       default=str(PROJECT_ROOT / "indices"),
                       help="Index directory path")
    
    args = parser.parse_args()
    
    print(f"🎯 Answer LLM Performance Benchmark")
    print(f"🔧 Mode: {args.mode.upper()}")
    print(f"❓ Max questions: {args.max_questions}")
    print(f"📄 Questions file: {args.questions}")
    print(f"📁 Index directory: {args.index}")
    print(f"💾 Results will be saved in: {RESULTS_DIR}")
    
    # 檢查檔案存在
    questions_file = Path(args.questions)
    index_dir = Path(args.index)
    
    if not questions_file.exists():
        print(f"❌ Questions file not found: {questions_file}")
        sys.exit(1)
        
    if not index_dir.exists():
        print(f"❌ Index directory not found: {index_dir}")
        sys.exit(1)
    
    results = []
    
    if args.mode == 'basic':
        # 基礎版本測試
        try:
            result = run_benchmark(
                mode='basic',
                workers=1,  # basic 模式固定為 1
                max_questions=args.max_questions,
                questions_file=str(questions_file),
                index_dir=str(index_dir)
            )
            results.append(result)
            
        except Exception as e:
            print(f"❌ Error in basic mode test: {e}")
    
    else:
        # 並行版本測試
        try:
            worker_counts = [int(w.strip()) for w in args.workers.split(',')]
        except ValueError:
            print("❌ Invalid workers format. Use comma-separated integers")
            sys.exit(1)
        
        print(f"📊 Testing with workers: {worker_counts}")
        
        for workers in worker_counts:
            try:
                result = run_benchmark(
                    mode='parallel',
                    workers=workers,
                    max_questions=args.max_questions,
                    questions_file=str(questions_file),
                    index_dir=str(index_dir)
                )
                results.append(result)
                
            except KeyboardInterrupt:
                print("\n⏹️  Benchmark stopped by user")
                break
            except Exception as e:
                print(f"❌ Error with {workers} workers: {e}")
                continue
    
    # 儲存結果
    if results:
        timestamp = int(time.time())
        csv_file = RESULTS_DIR / f"benchmark_{args.mode}_{timestamp}.csv"
        
        with open(csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
        
        print(f"\n📊 Results saved to: {csv_file}")
        
        # 顯示彙總表格
        print(f"\n📈 Performance Summary ({args.mode.upper()} mode):")
        print(f"{'Workers':<8} {'Time(s)':<8} {'Questions':<10} {'Q/s':<8} {'GPU%':<6} {'VRAM(MB)':<10}")
        print("-" * 60)
        
        for r in results:
            print(f"{r['workers']:<8} {r['seconds']:<8} {r['questions']:<10} "
                  f"{r['throughput']:<8} {r['gpu_util_max']:<6} {r['vram_max_mb']:<10}")
        
        # 找出最佳配置
        if len(results) > 1:
            best_throughput = max(results, key=lambda x: x['throughput'])
            print(f"\n🏆 Best performance: {best_throughput['workers']} workers "
                  f"({best_throughput['throughput']:.2f} Q/s)")
    
    print(f"\n✅ All results saved in: {RESULTS_DIR}")

if __name__ == "__main__":
    import shutil  # 加上這個 import
    main()