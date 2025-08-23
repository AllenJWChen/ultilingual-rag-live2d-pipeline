# --- Fix Windows DLL search path for PyTorch ---
import os, sys
from pathlib import Path

# 把 torch 的 lib 目錄加入 DLL 搜尋路徑
torch_lib = Path(sys.executable).parent.parent / "Lib" / "site-packages" / "torch" / "lib"
if torch_lib.exists():
    os.add_dll_directory(str(torch_lib))

import torch
print("[Torch OK]", torch.__version__, "CUDA:", torch.version.cuda)



# build_index.py (debug-friendly)
import os, re, sys
from pathlib import Path
import fitz  # PyMuPDF
from paddleocr import PaddleOCR
from langchain.text_splitter import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer
import faiss, numpy as np

BASE = Path(__file__).parent
PDF_DIR = BASE / "data"          # 專案內 data 資料夾
INDEX_DIR = BASE / "indices"
INDEX_DIR.mkdir(parents=True, exist_ok=True)

# ---- OCR 引擎：先用 CPU 版就好（你已裝 paddlepaddle 2.6.1）
ocr = PaddleOCR(use_angle_cls=True, lang='ch')  # ch 支援中英混排

def extract_page_text(page, page_idx, tmp_dir: Path):
    """優先用文字層；若太短/空則走 OCR。回傳 (text, used_ocr:bool)"""
    t = (page.get_text("text") or "").strip()
    # 如果文字層過短，視為圖像頁，走 OCR
    if len(t) < 50:
        # 轉成圖做 OCR（300 dpi 較穩定）
        pix = page.get_pixmap(dpi=300)
        img_path = tmp_dir / f"page_{page_idx+1}.png"
        pix.save(img_path.as_posix())
        try:
            ocr_result = ocr.ocr(img_path.as_posix(), cls=True)
            t = "\n".join([line[1][0] for line in (ocr_result[0] or [])]) if ocr_result else ""
        finally:
            try:
                img_path.unlink()
            except:
                pass
        return (t.strip(), True)
    return (t, False)

def extract_pdf_text_with_ocr(pdf_path: Path):
    doc = fitz.open(pdf_path.as_posix())
    tmp_dir = INDEX_DIR / "_ocr_tmp"
    tmp_dir.mkdir(exist_ok=True)
    texts = []
    ocr_pages = 0
    for i, page in enumerate(doc):
        t, used_ocr = extract_page_text(page, i, tmp_dir)
        if used_ocr: ocr_pages += 1
        # 簡單清理
        t = re.sub(r"\n{2,}", "\n", t).strip()
        if t:
            header = f"[{pdf_path.name} | page {i+1}]"
            texts.append(f"{header}\n{t}")
    return "\n\n".join(texts), len(doc), ocr_pages

def list_pdfs(root: Path):
    # 支援大小寫與子資料夾
    pdfs = list(root.rglob("*.pdf")) + list(root.rglob("*.PDF"))
    return sorted(set(pdfs))

def main():
    print(f"[INFO] PDF_DIR = {PDF_DIR}")
    pdf_files = list_pdfs(PDF_DIR)
    if not pdf_files:
        print("[WARN] 找不到任何 PDF。請確認檔案是否放在 data/ 內。")
        sys.exit(0)
    print(f"[INFO] 共找到 {len(pdf_files)} 份 PDF：")
    for p in pdf_files:
        print("  -", p)

    total_pages = 0
    total_ocr_pages = 0
    docs_texts = []

    for pdf in pdf_files:
        text, pages, ocr_pages = extract_pdf_text_with_ocr(pdf)
        total_pages += pages
        total_ocr_pages += ocr_pages
        print(f"[INFO] {pdf.name}: pages={pages}, ocr_pages={ocr_pages}, text_len={len(text)}")
        if len(text) > 0:
            docs_texts.append(text)

    if not docs_texts:
        print("[ERROR] 所有 PDF 都沒有抽到文字（包含 OCR）…請檢查 OCR 安裝或 PDF 是否加密。")
        sys.exit(0)

    # chunking（稍微放寬）
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200, chunk_overlap=150, separators=["\n\n", "\n", " ", ""]
    )
    chunks = []
    for doc_text in docs_texts:
        parts = splitter.split_text(doc_text)
        for p in parts:
            if len(p.strip()) < 60:  # 降低過濾門檻
                continue
            chunks.append(p)

    print(f"[INFO] 總頁數={total_pages}, 其中 OCR 頁數={total_ocr_pages}")
    print(f"[INFO] 產生 chunks 數量 = {len(chunks)}")
    if len(chunks) == 0:
        print("[ERROR] 沒有產生任何 chunk，請檢查前處理或過濾門檻設定。")
        sys.exit(0)

    # embedding（多語）
    print("[INFO] 載入多語向量模型（首次會下載較久）…")
    model = SentenceTransformer("intfloat/multilingual-e5-base")
    emb_inputs = [f"passage: {c}" for c in chunks]
    emb = model.encode(emb_inputs, normalize_embeddings=True, batch_size=64, show_progress_bar=True)
    emb = np.asarray(emb, dtype="float32")

    # FAISS
    index = faiss.IndexFlatIP(emb.shape[1])
    index.add(emb)
    faiss.write_index(index, (INDEX_DIR / "index.faiss").as_posix())
    with open(INDEX_DIR / "chunks.txt", "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(c.replace("\n", "\\n") + "\n")

    print(f"[OK] FAISS index saved to: {INDEX_DIR}")

if __name__ == "__main__":
    main()
