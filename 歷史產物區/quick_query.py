# quick_query.py  (reads index.faiss + chunks.txt)
import re, json
from pathlib import Path
import faiss, numpy as np
from sentence_transformers import SentenceTransformer

BASE = Path(__file__).parent
INDEX_DIR = BASE / "indices"
EMB_MODEL = "intfloat/multilingual-e5-base"  # 與 build_index.py 相同

IDX_PATH = INDEX_DIR / "index.faiss"
CHUNK_PATH = INDEX_DIR / "chunks.txt"

def load_index_and_chunks():
    if not IDX_PATH.exists():
        raise FileNotFoundError(f"找不到 {IDX_PATH}")
    if not CHUNK_PATH.exists():
        raise FileNotFoundError(f"找不到 {CHUNK_PATH}")

    index = faiss.read_index(str(IDX_PATH))
    chunks = []
    with open(CHUNK_PATH, "r", encoding="utf-8") as f:
        for line in f:
            # 還原換行
            chunks.append(line.rstrip("\n").replace("\\n", "\n"))
    return index, chunks

def parse_header(text):
    """
    解析 chunk 開頭像: [檔名.pdf | page 12]
    回傳 (source_name, page)
    """
    m = re.match(r"^\[(.+?)\s*\|\s*page\s*(\d+)\]\s*", text)
    if m:
        return m.group(1), int(m.group(2))
    return "unknown", -1

def embed_query(model, q):
    q = "query: " + q.strip()  # e5 規範
    v = model.encode([q], normalize_embeddings=True)
    return v.astype("float32")

def main():
    print("[INFO] 載入索引與 chunks …")
    index, chunks = load_index_and_chunks()
    print(f"[INFO] chunks = {len(chunks)}  (index ntotal = {index.ntotal})")

    model = SentenceTransformer(EMB_MODEL)

    while True:
        try:
            q = input("\n輸入問題（Enter 離開）：").strip()
        except EOFError:
            break
        if not q:
            break

        qvec = embed_query(model, q)
        D, I = index.search(qvec, 5)

        print(f"\n[QUERY] {q}")
        for rank, (dist, idx) in enumerate(zip(D[0], I[0]), 1):
            text = chunks[int(idx)]
            source, page = parse_header(text)
            preview = re.sub(r"\s+", " ", text)[:200] + "…"
            # 這裡 score 用 inner product，越大越好
            print(f"{rank:>2}. score={dist:.4f}  file={source}  p{page}")
            print(f"    {preview}")
        print()

if __name__ == "__main__":
    main()
