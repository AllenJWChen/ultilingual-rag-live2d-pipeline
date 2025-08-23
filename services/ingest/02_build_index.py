import os, glob, json, numpy as np, re
from sentence_transformers import SentenceTransformer
import faiss

INDEX_DIR = os.environ.get("INDEX_DIR","indices")
os.makedirs(INDEX_DIR, exist_ok=True)

def parse_pages(text: str):
    cur=1; lines=[]
    for line in text.splitlines():
        m = re.match(r"\[page=(\d+)\]", line.strip())
        if m: cur=int(m.group(1)); continue
        lines.append((cur, line))
    return lines

def split_chunks(text: str, size=1000, overlap=100):
    step = size - overlap
    i=0; chunks=[]
    while i < len(text):
        ch = text[i:i+size]
        if ch.strip(): chunks.append(ch)
        i += step
    return chunks

def main():
    PROCESSED = "data/processed"
    metas=[]; texts=[]
    for fp in glob.glob(os.path.join(PROCESSED, "*.txt")):
        raw = open(fp, "r", encoding="utf-8").read()
        pairs = parse_pages(raw)
        text = "\n".join([t for _,t in pairs])
        pages = [pg for pg,_ in pairs]
        chs = split_chunks(text, size=1000, overlap=100)
        for idx, ch in enumerate(chs):
            pg = pages[min(len(pages)-1, idx*20)] if pages else None
            metas.append({"text":ch, "page":pg, "source":os.path.basename(fp)})
            texts.append(ch)
    model = SentenceTransformer(os.environ.get("EMBEDDING_MODEL","sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"))
    vecs = model.encode(texts, normalize_embeddings=True).astype("float32")
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)
    faiss.write_index(index, os.path.join(INDEX_DIR, "faiss.index"))
    with open(os.path.join(INDEX_DIR, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump({"chunks": metas, "embedder": model._first_module().__class__.__name__}, f, ensure_ascii=False, indent=2)
    print("Index built at:", INDEX_DIR, "size:", len(metas))

if __name__ == "__main__":
    main()
