# Git RAG Pipeline 專案管理完整手冊

## 📋 目錄
1. [Git 基礎概念](#git-基礎概念)
2. [RAG Pipeline 專案初始化](#rag-pipeline-專案初始化)
3. [.gitignore 設定與原理](#gitignore-設定與原理)
4. [.gitkeep 目錄結構保持](#gitkeep-目錄結構保持)
5. [Git 基本工作流程](#git-基本工作流程)
6. [分支管理策略](#分支管理策略)
7. [遠端儲存庫管理](#遠端儲存庫管理)
8. [常用 Git 指令參考](#常用-git-指令參考)
9. [專案維護最佳實踐](#專案維護最佳實踐)

---

## 🎯 Git 基礎概念

### 什麼是 Git？
Git 是一個**分散式版本控制系統**，用於追蹤檔案變更、協調多人開發、備份專案歷史。

### 為什麼 RAG Pipeline 需要 Git？
1. **版本追蹤**：記錄模型調整、參數變更的歷史
2. **實驗管理**：不同分支測試不同的 pipeline 配置
3. **團隊協作**：多人同時開發不同模組
4. **備份安全**：防止重要程式碼遺失
5. **部署管理**：區分開發、測試、正式環境

### Git 核心概念
- **Repository (儲存庫)**：專案的完整歷史記錄
- **Working Directory (工作目錄)**：您正在編輯的檔案
- **Staging Area (暫存區)**：準備提交的變更
- **Commit (提交)**：一次變更的快照
- **Branch (分支)**：平行開發線
- **Remote (遠端)**：雲端或伺服器上的儲存庫

---

## 🚀 RAG Pipeline 專案初始化

### 完整初始化流程

```powershell
# 1. 切換到專案目錄
cd C:\AI\projects\multilingual_rag_live2d_scaffold

# 2. 初始化 Git 儲存庫
git init
# 輸出：Initialized empty Git repository in C:/AI/projects/multilingual_rag_live2d_scaffold/.git/

# 3. 設定使用者資訊（全域設定，只需做一次）
git config --global user.name "您的姓名"
git config --global user.email "your.email@example.com"

# 4. 建立 .gitignore 檔案
New-Item -ItemType File .gitignore
# 然後將後面提供的 .gitignore 內容貼入

# 5. 建立 .gitkeep 檔案保持目錄結構
New-Item -ItemType File datasets/.gitkeep
New-Item -ItemType File outputs/data/.gitkeep
New-Item -ItemType File outputs/tests/.gitkeep
New-Item -ItemType File packages/rag/generation/1_Keyword_llm/tests/results/.gitkeep
New-Item -ItemType File packages/rag/generation/3_Answer_llm/tests/results/.gitkeep

# 6. 檢查狀態
git status

# 7. 添加所有檔案到暫存區
git add .

# 8. 第一次提交
git commit -m "Initial commit: Professional RAG pipeline structure

- 建立完整的模組化 RAG pipeline 架構
- 包含 5 個處理階段：Keyword → Question → Answer → Critique → Eval
- 設定完整的測試環境與正式環境分離
- 加入 .gitkeep 保持目錄結構
- 配置 .gitignore 過濾大型檔案與緩存"
```

### 驗證初始化結果
```powershell
# 查看提交歷史
git log --oneline

# 查看分支狀態
git branch

# 查看遠端設定
git remote -v
```

---

## 🔒 .gitignore 設定與原理

### .gitignore 的作用
`.gitignore` 告訴 Git **哪些檔案或目錄不要追蹤**，避免：
- 大型資料檔案拖慢儲存庫
- 機敏資訊被意外提交
- 自動生成的檔案造成混亂
- Python 快取檔案污染專案

### RAG Pipeline 專用 .gitignore

```gitignore
# ===========================================
# RAG Pipeline .gitignore
# ===========================================

# ===========================================
# 大型資料檔案 (不追蹤，節省 repo 空間)
# ===========================================
datasets/*.pdf
datasets/*.docx
datasets/*.txt
datasets/*.zip
outputs/data/*.jsonl
outputs/data/*.csv
indices/chunks.*
indices/index.faiss
indices/metadata.json

# ===========================================
# Python 相關
# ===========================================
# 位元組碼檔案
**/__pycache__/
*.py[cod]
*$py.class

# 分發 / 打包
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# 虛擬環境
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Jupyter Notebook
.ipynb_checkpoints

# ===========================================
# 測試結果 (可重新生成，不需追蹤)
# ===========================================
**/tests/results/*.jsonl
**/tests/results/*.csv
**/tests/results/*.log
**/tests/results/bench_*.log
**/tests/results/chunk_k_*.jsonl

# 效能測試結果
outputs/tests/*.jsonl
outputs/tests/*.csv

# ===========================================
# AI 模型相關
# ===========================================
# 大型模型檔案
*.bin
*.safetensors
*.h5
*.onnx
*.pt
*.pth

# 向量資料庫
*.faiss
*.index

# ===========================================
# 臨時檔案與快取
# ===========================================
*.tmp
*.temp
*.swp
*.swo
*~
.DS_Store
Thumbs.db

# IDE 相關
.vscode/
.idea/
*.sublime-*
.spyderproject
.spyproject

# ===========================================
# 機敏資訊
# ===========================================
.env
.env.local
.env.prod
.env.development
config/*.key
config/*.secret
*.pem

# OpenAI API Keys
openai_api_key.txt
api_keys.json

# ===========================================
# 日誌檔案
# ===========================================
*.log
logs/
log/

# ===========================================
# 系統生成的檔案
# ===========================================
.coverage
htmlcov/
.pytest_cache/
.mypy_cache/
.dmypy.json
dmypy.json
.tox/
.nox/
coverage.xml
*.cover
*.py,cover
.hypothesis/

# ===========================================
# Docker 相關
# ===========================================
.dockerignore
docker-compose.override.yml

# ===========================================
# 保留目錄結構 (重要！)
# ===========================================
# 這些 .gitkeep 檔案確保空資料夾被 Git 追蹤
!**/.gitkeep
!datasets/.gitkeep
!outputs/data/.gitkeep
!outputs/tests/.gitkeep
!**/tests/results/.gitkeep

# ===========================================
# 特殊保留檔案
# ===========================================
# 保留重要的設定範例
!configs/.env.example
!README*.md
!requirements.txt
!Makefile
!docker-compose.yml
```

### .gitignore 語法規則

| 語法 | 說明 | 範例 |
|------|------|------|
| `file.txt` | 忽略特定檔案 | `config.json` |
| `*.py` | 忽略所有 .py 檔案 | `*.log` |
| `folder/` | 忽略整個資料夾 | `datasets/` |
| `**/logs` | 忽略任意深度的 logs 資料夾 | `**/tests/results` |
| `!important.txt` | 不要忽略（例外） | `!.env.example` |
| `# comment` | 註解 | `# 這是註解` |

---

## 📁 .gitkeep 目錄結構保持

### 問題：Git 不追蹤空資料夾
Git 只追蹤檔案，不追蹤空的資料夾。當其他開發者 clone 專案時，空資料夾會消失，可能導致程式執行錯誤。

### 解決方案：.gitkeep 檔案
`.gitkeep` 是約定俗成的檔名，用於保持資料夾結構：

```powershell
# 建立 .gitkeep 檔案
New-Item -ItemType File datasets/.gitkeep
New-Item -ItemType File outputs/data/.gitkeep
New-Item -ItemType File outputs/tests/.gitkeep
New-Item -ItemType File indices/.gitkeep

# 可選：添加說明文字
"# 此資料夾用於存放原始資料檔案" | Out-File datasets/.gitkeep -Encoding UTF8
"# 此資料夾用於存放正式流程輸出結果" | Out-File outputs/data/.gitkeep -Encoding UTF8
"# 此資料夾用於存放測試結果" | Out-File outputs/tests/.gitkeep -Encoding UTF8
```

### 驗證效果
```powershell
# 檢查 Git 狀態，應該能看到 .gitkeep 檔案
git status

# 其他開發者 clone 後，目錄結構完整保留
git clone your-repo.git
tree    # 目錄結構完整
```

---

## 🔄 Git 基本工作流程

### 日常開發流程

```powershell
# 1. 檢查當前狀態
git status

# 2. 查看變更內容
git diff

# 3. 添加變更到暫存區
git add .                    # 添加所有變更
git add specific_file.py     # 添加特定檔案
git add packages/           # 添加特定目錄

# 4. 提交變更
git commit -m "功能：添加新的問題生成模組"

# 5. 查看提交歷史
git log --oneline
git log --graph --oneline --all
```

### 撤銷操作

```powershell
# 撤銷工作目錄的變更
git checkout -- filename.py

# 撤銷暫存區的變更
git reset HEAD filename.py

# 修改最後一次提交訊息
git commit --amend -m "修正後的提交訊息"

# 回到上一個提交（保留變更）
git reset --soft HEAD~1

# 回到上一個提交（丟棄變更）
git reset --hard HEAD~1
```

---

## 🌿 分支管理策略

### RAG Pipeline 分支結構

```
main (主分支)
├── develop (開發分支)
├── feature/keyword-enhancement (功能分支)
├── feature/answer-optimization (功能分支)
├── hotfix/critical-bug (修復分支)
└── release/v1.0 (發佈分支)
```

### 分支操作

```powershell
# 查看所有分支
git branch -a

# 建立並切換到新分支
git checkout -b feature/new-evaluation-module

# 切換分支
git checkout develop

# 合併分支
git checkout main
git merge feature/new-evaluation-module

# 删除分支
git branch -d feature/old-feature

# 推送分支到遠端
git push origin feature/new-evaluation-module
```

### 功能開發流程
```powershell
# 1. 從 main 建立功能分支
git checkout main
git pull origin main
git checkout -b feature/improve-chunk-processing

# 2. 開發功能
# ... 編輯檔案 ...

# 3. 提交變更
git add .
git commit -m "功能：改善 chunk 處理效能"

# 4. 推送到遠端
git push origin feature/improve-chunk-processing

# 5. 建立 Pull Request (在 GitHub/GitLab 上)

# 6. 合併後清理
git checkout main
git pull origin main
git branch -d feature/improve-chunk-processing
```

---

## 🌐 遠端儲存庫管理

### 連接 GitHub

```powershell
# 1. 在 GitHub 建立新儲存庫 (不要初始化 README)

# 2. 添加遠端儲存庫
git remote add origin https://github.com/your-username/multilingual-rag-pipeline.git

# 3. 第一次推送
git push -u origin main

# 4. 後續推送
git push
```

### 常用遠端操作

```powershell
# 查看遠端設定
git remote -v

# 從遠端抓取最新變更
git fetch origin

# 從遠端拉取並合併
git pull origin main

# 推送到遠端
git push origin main

# 克隆儲存庫
git clone https://github.com/username/repo.git
```

### 協作流程

```powershell
# 1. 同步最新變更
git checkout main
git pull origin main

# 2. 建立功能分支
git checkout -b feature/your-feature

# 3. 開發並提交
git add .
git commit -m "您的變更"

# 4. 推送分支
git push origin feature/your-feature

# 5. 在 GitHub 建立 Pull Request

# 6. 合併後清理
git checkout main
git pull origin main
git branch -d feature/your-feature
```

---

## 📚 常用 Git 指令參考

### 設定與初始化
```powershell
git init                                    # 初始化儲存庫
git config --global user.name "姓名"        # 設定使用者名稱
git config --global user.email "email"     # 設定使用者信箱
git config --list                          # 查看設定
```

### 基本操作
```powershell
git status                                 # 查看狀態
git add .                                  # 添加所有變更
git add filename                           # 添加特定檔案
git commit -m "訊息"                        # 提交變更
git log                                    # 查看歷史
git log --oneline                          # 簡潔歷史
git diff                                   # 查看變更
```

### 分支操作
```powershell
git branch                                 # 查看本地分支
git branch -a                              # 查看所有分支
git checkout branch-name                   # 切換分支
git checkout -b new-branch                 # 建立並切換分支
git merge branch-name                      # 合併分支
git branch -d branch-name                  # 刪除分支
```

### 遠端操作
```powershell
git remote -v                              # 查看遠端設定
git remote add origin url                  # 添加遠端
git push origin main                       # 推送到遠端
git pull origin main                       # 從遠端拉取
git fetch origin                           # 抓取遠端變更
git clone url                              # 克隆儲存庫
```

### 撤銷與修復
```powershell
git checkout -- filename                  # 撤銷工作目錄變更
git reset HEAD filename                    # 撤銷暫存變更
git reset --soft HEAD~1                   # 軟重置到上一個提交
git reset --hard HEAD~1                   # 硬重置到上一個提交
git commit --amend                         # 修改最後一次提交
```

---

## 🏆 專案維護最佳實踐

### 提交訊息規範

使用 **Conventional Commits** 格式：
```
<類型>[可選範圍]: <描述>

[可選正文]

[可選頁尾]
```

**類型**：
- `feat`: 新功能
- `fix`: 錯誤修復
- `docs`: 文檔變更
- `style`: 程式碼格式調整
- `refactor`: 重構
- `test`: 測試相關
- `chore`: 建構工具或輔助工具變更

**範例**：
```powershell
git commit -m "feat(answer): 添加多語言答案生成支援"
git commit -m "fix(keyword): 修復關鍵字提取的記憶體洩漏問題"  
git commit -m "docs: 更新 README 安裝說明"
git commit -m "refactor(pipeline): 重構問題生成模組以提高效能"
```

### 版本標籤管理

```powershell
# 建立標籤
git tag v1.0.0
git tag -a v1.0.0 -m "第一個正式版本"

# 查看標籤
git tag

# 推送標籤
git push origin v1.0.0
git push origin --tags

# 刪除標籤
git tag -d v1.0.0
git push origin --delete v1.0.0
```

### 定期維護任務

```powershell
# 1. 清理無用分支
git branch -d feature/old-feature
git push origin --delete feature/old-feature

# 2. 壓縮提交歷史 (小心使用)
git rebase -i HEAD~5

# 3. 清理 .git 資料夾 (釋放空間)
git gc --prune=now

# 4. 檢查檔案大小
git ls-files | xargs ls -l | sort -nrk5 | head -10
```

### 專案結構檢查清單

**每次提交前檢查**：
- [ ] `.gitignore` 是否過濾了大型檔案
- [ ] 敏感資訊是否被意外提交
- [ ] 測試結果是否被正確忽略
- [ ] `.gitkeep` 是否保持目錄結構

**定期檢查**：
- [ ] 儲存庫大小是否合理 (< 100MB)
- [ ] 分支是否及時清理
- [ ] 提交歷史是否清晰
- [ ] 文檔是否與程式碼同步

---

## 🚨 常見問題與解決方案

### 問題 1：檔案太大無法推送
```powershell
# 錯誤：file size exceeds GitHub's file size limit of 100.00 MB

# 解決方案：
# 1. 將大檔案移到 .gitignore
echo "large-file.pdf" >> .gitignore

# 2. 從 Git 歷史中移除 (保留本地檔案)
git rm --cached large-file.pdf

# 3. 提交變更
git commit -m "移除大型檔案並加入 .gitignore"
```

### 問題 2：意外提交敏感資訊
```powershell
# 1. 立即從 .gitignore 中添加
echo "config/secret.key" >> .gitignore

# 2. 從 Git 中移除 (保留本地檔案)
git rm --cached config/secret.key

# 3. 提交修正
git commit -m "移除敏感檔案"

# 4. 如果已推送，需要聯繫管理員或重寫歷史
```

### 問題 3：合併衝突
```powershell
# 1. 拉取最新變更時出現衝突
git pull origin main
# Auto-merging conflicts in filename.py
# CONFLICT (content): Merge conflict in filename.py

# 2. 手動解決衝突 (編輯檔案，移除 <<<<<<< ======= >>>>>>> 標記)

# 3. 標記為已解決
git add filename.py

# 4. 完成合併
git commit -m "解決合併衝突"
```

### 問題 4：回復到之前版本
```powershell
# 1. 查看提交歷史
git log --oneline

# 2. 回到特定提交 (保留變更)
git reset --soft commit-hash

# 3. 回到特定提交 (丟棄變更) - 危險操作！
git reset --hard commit-hash

# 4. 建立新分支從特定提交開始
git checkout -b recovery-branch commit-hash
```

---

## 🎯 總結

這份手冊涵蓋了 RAG Pipeline 專案使用 Git 的完整流程，從初始化到日常維護的所有重要知識點。

### 關鍵要點：
1. **正確的 .gitignore 設定**防止大型檔案和敏感資訊被追蹤
2. **使用 .gitkeep**保持重要的目錄結構
3. **規範的提交訊息**讓專案歷史清晰可讀
4. **適當的分支策略**支援團隊協作
5. **定期維護**保持儲存庫健康

遵循這些最佳實踐，您的 RAG Pipeline 專案將具備專業級的版本控制管理，無論是個人開發還是團隊協作都能順暢運行。