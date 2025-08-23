# -*- coding: utf-8 -*-
"""
逐頁抽取 + 切 chunk，輸出 indices/chunks.jsonl（每行一個 JSON：source/page/text）

使用場景（Examples）：
  基本使用（推薦新手）：
    python scripts/build_chunks_jsonl.py

  包含 OCR 功能（缺文字層時會自動圖像辨識）：
    python scripts/build_chunks_jsonl.py --ocr

  相容舊系統（需要 TXT）：
    python scripts/build_chunks_jsonl.py --write-txt

  一次到位（JSONL + TXT + OCR + FAISS）：
    python scripts/build_chunks_jsonl.py --preset full

  自訂輸出位置與切片大小：
    python scripts/build_chunks_jsonl.py --input data --out indices/chunks.jsonl --chunk-size 1200 --overlap 150

預設組合（--preset）：
  basic = 預設行為（只寫 JSONL）
  full  = 同時啟用 --write-txt --ocr --faiss
"""

from __future__ import annotations
import os, re, sys, json, argparse
from pathlib import Path

# ---- (修復) Windows 上 torch DLL 搜尋路徑，必須在所有導入之前 ----
if os.name == 'nt':  # Windows
    try:
        # 設置環境變量
        os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
        os.environ["OMP_NUM_THREADS"] = "1"
        
        # 添加 torch lib 目錄到 DLL 搜索路徑
        torch_lib = Path(sys.executable).parent.parent / "Lib" / "site-packages" / "torch" / "lib"
        if torch_lib.exists():
            os.add_dll_directory(str(torch_lib))
            
        # 立即測試 torch 導入
        import torch
        print(f"[DEBUG] Torch 預載成功: {torch.__version__}")
    except Exception as e:
        print(f"[WARN] Torch 預載失敗，但繼續執行: {e}")

import fitz  # PyMuPDF
from paddleocr import PaddleOCR
from langchain.text_splitter import RecursiveCharacterTextSplitter

# ---- 預先導入可能有問題的庫 ----
def _preload_faiss_deps():
    """預先載入 FAISS 相關依賴，避免延遲導入問題"""
    try:
        import numpy as np
        import faiss
        from sentence_transformers import SentenceTransformer
        print("[DEBUG] FAISS 相關庫預載成功")
        return np, faiss, SentenceTransformer
    except Exception as e:
        print(f"[DEBUG] FAISS 相關庫預載失敗: {e}")
        return None, None, None

# 全局變量存儲預載的庫
_NUMPY = None
_FAISS = None 
_SENTENCE_TRANSFORMER = None


# -------------------------- 依賴檢查 --------------------------
def check_dependencies(need_ocr: bool, need_faiss: bool):
    missing: list[str] = []
    if need_ocr:
        try:
            import paddleocr  # noqa: F401
        except Exception:
            missing.append("paddleocr")
    if need_faiss:
        try:
            import faiss  # noqa: F401
            import sentence_transformers  # noqa: F401
        except Exception:
            # 這兩個通常要一起：faiss-cpu + sentence-transformers
            missing.append("faiss-cpu sentence-transformers")
    if missing:
        print(f"[ERROR] 缺少套件，請先安裝：\n  pip install {' '.join(missing)}")
        sys.exit(1)


# -------------------------- 修復後的 FAISS 導入 --------------------------
def _maybe_import_faiss():
    """使用預載的庫或重新導入"""
    global _NUMPY, _FAISS, _SENTENCE_TRANSFORMER
    
    if _NUMPY is None or _FAISS is None or _SENTENCE_TRANSFORMER is None:
        # 如果預載失敗，嘗試重新載入
        _NUMPY, _FAISS, _SENTENCE_TRANSFORMER = _preload_faiss_deps()
    
    if _NUMPY is None or _FAISS is None or _SENTENCE_TRANSFORMER is None:
        raise ImportError("無法載入 FAISS 相關依賴")
        
    return _NUMPY, _FAISS, _SENTENCE_TRANSFORMER


# -------------------------- 小工具 --------------------------
def list_pdfs(root: Path) -> list[Path]:
    pdfs = list(root.rglob("*.pdf")) + list(root.rglob("*.PDF"))
    return sorted(set(pdfs), key=lambda p: p.as_posix())


def extract_page_text(page, page_idx: int, tmp_dir: Path, ocr: PaddleOCR | None) -> tuple[str, bool]:
    """
    優先用文字層；若文字層太短則走 OCR。回傳 (text, used_ocr)
    """
    t = (page.get_text("text") or "").strip()
    if len(t) >= 50 or ocr is None:
        return t, False

    # 文字層不足 → 以 300dpi 轉圖做 OCR
    tmp_dir.mkdir(parents=True, exist_ok=True)
    img_path = tmp_dir / f"page_{page_idx+1}.png"
    page.get_pixmap(dpi=300).save(img_path.as_posix())
    try:
        result = ocr.ocr(img_path.as_posix(), cls=True)
        t = "\n".join([line[1][0] for line in (result[0] or [])]) if result else ""
    finally:
        try:
            img_path.unlink()
        except Exception:
            pass
    return t.strip(), True


def chunk_page_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", " ", ""],
    )
    pieces = [s.strip() for s in splitter.split_text(text)]
    return [p for p in pieces if len(p) >= 60]  # 過短片段丟棄


# -------------------------- 主程式 --------------------------
def main():
    parser = argparse.ArgumentParser(
        description="逐頁抽取 + 切 chunk，輸出 indices/chunks.jsonl（每行 JSON：source/page/text）"
    )
    parser.add_argument("--input", default="datasets", help="資料來源根目錄（預設 data）")
    parser.add_argument("--out", default="indices/chunks.jsonl", help="輸出 JSONL（預設 indices/chunks.jsonl）")
    parser.add_argument("--write-txt", action="store_true", help="同時輸出 indices/chunks.txt（相容舊流程）")
    parser.add_argument("--chunk-size", type=int, default=1200, help="每個 chunk 大小（字元）")
    parser.add_argument("--overlap", type=int, default=150, help="chunk 重疊字元數")
    parser.add_argument("--ocr", action="store_true", help="缺文字層時啟用 OCR（paddleocr）")
    parser.add_argument("--faiss", action="store_true", help="一併建立 indices/index.faiss（多語 embedding）")
    parser.add_argument(
        "--preset",
        choices=["basic", "full"],
        help="預設組合：basic（基本行為，僅 JSONL）、full（= --write-txt --ocr --faiss）",
    )
    args = parser.parse_args()

    # 套用 preset
    if args.preset == "full":
        args.write_txt = True
        args.ocr = True
        args.faiss = True

    # 依賴檢查
    check_dependencies(need_ocr=args.ocr, need_faiss=args.faiss)
    
    # 預載 FAISS 相關庫（如果需要的話）
    global _NUMPY, _FAISS, _SENTENCE_TRANSFORMER
    if args.faiss:
        print("[INFO] 預載 FAISS 相關庫...")
        _NUMPY, _FAISS, _SENTENCE_TRANSFORMER = _preload_faiss_deps()
        if _NUMPY is None:
            print("[ERROR] FAISS 庫預載失敗，無法建立向量索引")
            args.faiss = False

    input_dir = Path(args.input)
    out_path = Path(args.out)
    index_dir = out_path.parent
    index_dir.mkdir(parents=True, exist_ok=True)

    pdfs = list_pdfs(input_dir)
    if not pdfs:
        print(f"[WARN] 找不到 PDF（搜尋：{input_dir}）。")
        sys.exit(0)

    print(f"[INFO] 找到 {len(pdfs)} 份 PDF：")
    for p in pdfs:
        print("  -", p.relative_to(Path.cwd()) if p.is_absolute() else p)

    ocr_engine = PaddleOCR(use_angle_cls=True, lang="ch") if args.ocr else None
    tmp_dir = index_dir / "_ocr_tmp"

    total_pages = 0
    total_ocr = 0
    total_chunks = 0

    txt_lines: list[str] = []
    all_chunk_texts: list[str] = []

    with out_path.open("w", encoding="utf-8") as fout:
        for pdf in pdfs:
            doc = fitz.open(pdf.as_posix())
            for i, page in enumerate(doc):
                total_pages += 1
                text, used_ocr = extract_page_text(page, i, tmp_dir, ocr_engine)
                if used_ocr:
                    total_ocr += 1
                text = re.sub(r"\n{2,}", "\n", text).strip()
                if not text:
                    continue

                # 逐頁切片
                for piece in chunk_page_text(text, args.chunk_size, args.overlap):
                    rec = {"source": pdf.name, "page": i + 1, "text": piece}
                    fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    total_chunks += 1

                    if args.write_txt:
                        header = f"[{pdf.name} | page {i+1}]"
                        txt_lines.append((header + "\n" + piece).replace("\n", "\\n"))

                    if args.faiss:
                        all_chunk_texts.append(piece)

    # 補寫 chunks.txt（選擇性）
    if args.write_txt:
        with (index_dir / "chunks.txt").open("w", encoding="utf-8") as ftxt:
            for line in txt_lines:
                ftxt.write(line + "\n")

    # 建 FAISS（選擇性）
    if args.faiss and all_chunk_texts and _SENTENCE_TRANSFORMER is not None:
        print("[INFO] 建立多語向量索引（intfloat/multilingual-e5-base）…")
        np, faiss, SentenceTransformer = _maybe_import_faiss()
        model = SentenceTransformer("intfloat/multilingual-e5-base")
        emb_inputs = [f"passage: {c}" for c in all_chunk_texts]
        emb = model.encode(emb_inputs, normalize_embeddings=True, batch_size=64, show_progress_bar=True)
        emb = np.asarray(emb, dtype="float32")
        index = faiss.IndexFlatIP(emb.shape[1])
        index.add(emb)
        faiss.write_index(index, (index_dir / "index.faiss").as_posix())

    # 清理暫存
    if tmp_dir.exists():
        try:
            for p in tmp_dir.glob("page_*.png"):
                p.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except Exception:
            pass

    print(f"[OK] 總頁數={total_pages}，OCR頁數={total_ocr}，chunks={total_chunks}")
    print(f"[OK] JSONL 寫到：{out_path}")
    if args.write_txt:
        print(f"[OK] TXT  也寫到：{index_dir/'chunks.txt'}")
    if args.faiss and _SENTENCE_TRANSFORMER is not None:
        print(f"[OK] FAISS index：{index_dir/'index.faiss'}")


if __name__ == "__main__":
    main()