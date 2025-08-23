# PowerShell RAG Pipeline 常用指令手冊

## 📁 目錄管理與查詢指令

### 基本目錄查詢
```powershell
# 查看當前目錄內容
Get-ChildItem
dir
ls

# 查看特定資料夾內容
Get-ChildItem data/
dir data\

# 查看檔案詳細資訊（包含大小、修改時間）
Get-ChildItem -Force | Format-Table Name, Length, LastWriteTime

# 遞歸查看所有子目錄檔案
Get-ChildItem -Recurse

# 查看特定副檔名的檔案
Get-ChildItem *.jsonl
Get-ChildItem *.pdf

# 查看檔案內容前幾行
Get-Content data\questions.jsonl | Select-Object -First 5
Get-Content packages\rag\generation\Answer_llm\tests\results\test_answers.jsonl | Select-Object -First 3

# 統計檔案行數
Get-Content data\questions.jsonl | Measure-Object -Line
```

### 進階查詢與篩選
```powershell
# 查找包含特定文字的檔案
Get-ChildItem -Recurse | Select-String "llama3.1"

# 查看檔案大小並排序
Get-ChildItem | Sort-Object Length -Descending | Format-Table Name, @{Name="Size(KB)";Expression={[math]::Round($_.Length/1KB,2)}}

# 查看最近修改的檔案
Get-ChildItem | Sort-Object LastWriteTime -Descending | Select-Object -First 10

# 查看特定時間範圍的檔案
Get-ChildItem | Where-Object {$_.LastWriteTime -gt (Get-Date).AddDays(-1)}
```

## 🗂️ 檔案與資料夾操作

### 建立標準目錄結構
```powershell
# 建立推薦的資料夾結構
New-Item -ItemType Directory -Force data/input
New-Item -ItemType Directory -Force data/samples  
New-Item -ItemType Directory -Force outputs
New-Item -ItemType Directory -Force tests/data
New-Item -ItemType Directory -Force tests/results
New-Item -ItemType Directory -Force tests/benchmarks

# 建立 .gitkeep 檔案保持資料夾結構
New-Item -ItemType File -Force data/input/.gitkeep
New-Item -ItemType File -Force outputs/.gitkeep
New-Item -ItemType File -Force tests/results/.gitkeep
```

### 檔案移動與整理
```powershell
# 移動 PDF 到 input 資料夾
Move-Item data/*.pdf data/input/

# 移動測試檔案到對應資料夾
Move-Item data/sample_questions_20.jsonl data/samples/
Move-Item data/bench tests/benchmarks/
Move-Item data/chunk_k*.jsonl tests/results/
Move-Item data/keywords.jsonl tests/results/

# 複製檔案（保留原檔）
Copy-Item source_file.jsonl destination/

# 重新命名檔案
Rename-Item old_name.jsonl new_name.jsonl
```

## 🔧 環境變數設定

### Ollama + OpenAI 相容模式
```powershell
# 基本設定
$env:LLM_MODE="OPENAI_COMPAT"
$env:OPENAI_BASE_URL="http://localhost:11434/v1"
$env:OPENAI_API_KEY="ollama"

# 模型設定
$env:MODEL_QUESTION="llama3.1:latest"
$env:MODEL_KEYWORDS="llama3.1:latest" 
$env:MODEL_ANSWER="llama3.1:8b"

# 查看當前環境變數
Get-ChildItem Env: | Where-Object {$_.Name -like "*LLM*" -or $_.Name -like "*MODEL*" -or $_.Name -like "*OPENAI*"}

# 清除環境變數
Remove-Item Env:MODEL_ANSWER -ErrorAction SilentlyContinue
```

### MOCK 測試模式
```powershell
$env:LLM_MODE="MOCK"
# MOCK 模式不需要其他設定
```

## 🚀 RAG Pipeline 執行指令

### 1. Chunk 切分與索引
```powershell
# 基本 chunk 切分
python scripts/build_chunks_jsonl.py

# 包含 OCR 功能
python scripts/build_chunks_jsonl.py --ocr

# 完整功能（JSONL + TXT + OCR + FAISS）
python scripts/build_chunks_jsonl.py --preset full

# 自訂設定
python scripts/build_chunks_jsonl.py --input data/input --out indices/chunks.jsonl --chunk-size 1200 --overlap 150
```

### 2. 問題生成
```powershell
# 生成問題（測試）
python -m packages.rag.generation.Question_llm.make_questions `
  --index indices `
  --out tests/results/questions.jsonl `
  --langs zh,en `
  --max-chunks 50

# 生成問題（正式）
python -m packages.rag.generation.Question_llm.make_questions `
  --index indices `
  --out outputs/questions.jsonl `
  --langs zh,en `
  --max-chunks 1000
```

### 3. 問題檢查與抽樣
```powershell
# 檢查問題格式
python scripts/check_questions.py outputs/questions.jsonl

# 隨機抽樣檢查
python scripts/sample_questions.py

# 查看問題統計
Get-Content outputs/questions.jsonl | Measure-Object -Line
```

### 4. 答案生成
```powershell
# 測試模式（少量資料）
python -m packages.rag.generation.Answer_llm.core `
  --questions tests/results/questions.jsonl `
  --index indices `
  --out tests/results/test_answers.jsonl `
  --max 10

# 正式模式（大量資料）
python -m packages.rag.generation.Answer_llm.core `
  --questions outputs/questions.jsonl `
  --index indices `
  --out outputs/answers.jsonl `
  --max 1000
```

### 5. 答案審核
```powershell
python -m packages.rag.generation.Critique_llm.run `
  --answers outputs/answers.jsonl `
  --out outputs/answers_pass.jsonl
```

### 6. 最終資料輸出
```powershell
python scripts/export_rag_corpus.py outputs/answers_pass.jsonl
```

## 📊 效能測試與監控

### 關鍵字生成效能測試
```powershell
# 快速測試（200 chunks）
python scripts/bench_keywords.py --max-chunks 200

# 自訂測試參數
python scripts/bench_keywords.py --workers 1,4,8,16 --max-chunks 400 --langs zh,en

# 查看測試結果
Get-Content tests/benchmarks/bench/bench_keywords.csv
```

### 系統監控
```powershell
# 查看 GPU 狀態（需要 NVIDIA GPU）
nvidia-smi

# 查看系統資源使用
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10

# 查看磁碟空間
Get-PSDrive
```

## 🔍 API 測試指令

### Ollama API 測試
```powershell
# 檢查 Ollama 服務狀態
ollama list
ollama --version

# 測試模型是否存在
ollama show llama3.1:8b

# 測試 API 端點（使用 Invoke-WebRequest）
$headers = @{"Content-Type"="application/json"}
$body = @{
    model = "llama3.1:latest"
    messages = @(@{role="user"; content="Hello"})
    max_tokens = 50
} | ConvertTo-Json -Depth 3

Invoke-WebRequest -Uri "http://localhost:11434/v1/chat/completions" -Method POST -Headers $headers -Body $body

# 簡單測試 API 可用性
curl http://localhost:11434/v1/models
curl http://localhost:11434/api/tags
```

## 📝 資料檢查與驗證

### JSONL 檔案檢查
```powershell
# 檢查 JSONL 格式是否正確
Get-Content outputs/questions.jsonl | ForEach-Object {
    try {
        $_ | ConvertFrom-Json | Out-Null
        "✓"
    } catch {
        "✗ 錯誤行: $_"
    }
} | Group-Object | Select-Object Name, Count

# 查看 JSON 結構
Get-Content outputs/questions.jsonl | Select-Object -First 1 | ConvertFrom-Json | ConvertTo-Json -Depth 10

# 統計關鍵資訊
$questions = Get-Content outputs/questions.jsonl | ConvertFrom-Json
$questions | Group-Object source | Select-Object Name, Count
$questions | ForEach-Object { $_.questions.Count } | Measure-Object -Sum -Average
```

### 檔案完整性檢查
```powershell
# 檢查必要檔案是否存在
$required_files = @(
    "indices/chunks.txt",
    "outputs/questions.jsonl",
    "outputs/answers.jsonl"
)

foreach ($file in $required_files) {
    if (Test-Path $file) {
        "✓ $file 存在"
    } else {
        "✗ $file 缺失"
    }
}

# 檢查檔案大小合理性
Get-ChildItem outputs/ | Where-Object {$_.Length -eq 0} | Select-Object Name
```

## 🧹 清理與維護

### 清理暫存檔案
```powershell
# 清理測試結果
Remove-Item tests/results/*.jsonl -Force

# 清理 benchmark 資料
Remove-Item tests/benchmarks/bench/* -Force

# 清理 Python 快取
Get-ChildItem -Recurse __pycache__ | Remove-Item -Recurse -Force
Get-ChildItem -Recurse *.pyc | Remove-Item -Force
```

### 備份重要資料
```powershell
# 建立備份資料夾
$backup_date = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force backups/$backup_date

# 備份重要檔案
Copy-Item outputs/ backups/$backup_date/ -Recurse
Copy-Item indices/chunks.txt backups/$backup_date/
Copy-Item data/input/ backups/$backup_date/ -Recurse
```

## 🚨 故障排除指令

### 常見問題檢查
```powershell
# 檢查 Python 環境
python --version
pip list | findstr "openai\|httpx\|requests"

# 檢查網路連接
Test-NetConnection localhost -Port 11434

# 檢查程序是否執行
Get-Process | Where-Object {$_.ProcessName -like "*ollama*"}

# 檢查環境變數設定
$env:LLM_MODE
$env:MODEL_ANSWER
$env:OPENAI_BASE_URL

# 重新啟動 Ollama 服務
taskkill /f /im ollama.exe
ollama serve
```

### 日誌查看
```powershell
# 查看最近的錯誤日誌
Get-EventLog -LogName Application -Source "Python*" -Newest 10

# 查看特定程序日誌
python -m packages.rag.generation.Answer_llm.core --help
```

## 💡 實用技巧

### 批次操作
```powershell
# 批次檢查多個 JSONL 檔案
Get-ChildItem *.jsonl | ForEach-Object {
    Write-Host "檢查: $($_.Name)"
    Get-Content $_.FullName | Measure-Object -Line | Select-Object -ExpandProperty Lines
}

# 批次轉換編碼
Get-ChildItem *.jsonl | ForEach-Object {
    $content = Get-Content $_.FullName -Encoding UTF8
    $content | Out-File $_.FullName -Encoding UTF8
}
```

### 快速統計
```powershell
# 統計 pipeline 處理進度
Write-Host "Chunks: $(if (Test-Path indices/chunks.txt) {(Get-Content indices/chunks.txt | Measure-Object -Line).Lines} else {'未生成'})"
Write-Host "Questions: $(if (Test-Path outputs/questions.jsonl) {(Get-Content outputs/questions.jsonl | Measure-Object -Line).Lines} else {'未生成'})"
Write-Host "Answers: $(if (Test-Path outputs/answers.jsonl) {(Get-Content outputs/answers.jsonl | Measure-Object -Line).Lines} else {'未生成'})"
```

---

## 📞 快速參考

**模型檢查**: `ollama list`  
**API 測試**: `curl http://localhost:11434/v1/models`  
**檔案統計**: `Get-Content file.jsonl | Measure-Object -Line`  
**環境變數**: `Get-ChildItem Env: | Where-Object {$_.Name -like "*MODEL*"}`  
**清理快取**: `Get-ChildItem -Recurse __pycache__ | Remove-Item -Recurse -Force`

---

*此手冊涵蓋了 RAG Pipeline 開發與維護的常用 PowerShell 指令，建議收藏備用。*