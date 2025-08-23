import os, glob, fitz, json, re
from dotenv import load_dotenv
load_dotenv()

RAW = "data/raw"
PROCESSED = "data/processed"
os.makedirs(PROCESSED, exist_ok=True)

def extract_pdf(path: str) -> str:
    doc = fitz.open(path)
    parts = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text()
        parts.append(f"[page={i}]\n{text}")
    return "\n".join(parts)

def main():
    for p in glob.glob(os.path.join(RAW, "*.pdf")):
        out = extract_pdf(p)
        dst = os.path.join(PROCESSED, os.path.basename(p).replace(".pdf", ".txt"))
        with open(dst, "w", encoding="utf-8") as f:
            f.write(out)
        print("wrote:", dst)
    for p in glob.glob(os.path.join(RAW, "*.txt")):
        dst = os.path.join(PROCESSED, os.path.basename(p))
        with open(dst, "w", encoding="utf-8") as f:
            f.write(open(p, "r", encoding="utf-8").read())
        print("copied:", dst)

if __name__ == "__main__":
    main()
