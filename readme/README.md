# Multilingual RAG + LoRA + Live2D Assistant (Demo-Ready)

目標：依照 8/15~8/31 計畫，交付可現場操作的 **雙語 RAG + LoRA + 多模態（圖片/表格）+ Live2D** Demo。

## 架構總覽
- services/api：FastAPI 對外 API（/ask, /ingest, /health）
- services/ingest：資料抽取、OCR、chunking、embedding、建索引
- services/live2d：TTS 產檔；預留與 VTube Studio / Cubism SDK 串接點
- packages/rag_core：檢索與生成核心（retriever, reranker hook, rag_chain, multilingual embeddings）
- data/：raw / processed 原始資料與抽取後文本
- indices/：向量索引與metadata
- configs/：環境設定（.env.example, settings.yaml）
- web/（可選）：簡易前端（後續可加）

> 預設優先使用 **SentenceTransformers + FAISS**（可離線），需要時可切換 **Milvus/Weaviate**。

## 快速開始（本機）
```bash
# 0) Python 3.10+ 建議
pip install -r requirements.txt

# 1) 把 PDF/TXT 放到 data/raw
# 2) 抽取與清理 → 切分 → 建索引
python services/ingest/01_extract.py
python services/ingest/02_build_index.py

# 3) 啟動 API
uvicorn services.api.server:app --reload --port 8000

# 4) 測試
curl -X POST http://127.0.0.1:8000/ask -H "Content-Type: application/json" -d '{"q":"中文查英文：What is silicon photonics 的材料組成？"}'
```

## 切換多語 Embedding
- 預設：`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`（輕量）
- 推薦：`intfloat/multilingual-e5-base`（更強，記得在 `packages/rag_core/embeddings.py` 改名）
- OpenAI：`text-embedding-3-large`（需設定 OPENAI_API_KEY）

## LoRA / QLoRA
- 此模板預留 `services/ingest/03_lora_train.py`，可在完成資料集後啟動 LoRA 訓練（使用 HuggingFace PEFT）。

## Live2D & 多語 TTS
- `services/live2d/tts_stub.py` 產生 wav → 餵給 VTube Studio API 做嘴型同步。
- 未包含商用 TTS SDK，請依 `.env.example` 配置 Azure/ElevenLabs/OpenAI TTS 後接入 `services/live2d/tts_router.py`。

## 評估（Evaluation）
- `services/ingest/04_build_evalset.py`：建立 golden Q&A + keywords
- `services/ingest/05_eval.py`：Precision / Recall / F1 / Cosine Similarity（可針對數字題重點檢測）

## 注意
- 此專案偏向 **可展示的最小可行產品（MVP）**，方便面試現場 demo。上雲/高可用可再補 docker-compose / Helm。
```
