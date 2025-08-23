# 📋 RAG Pipeline 每日工作流程模板

## 🌅 **開始工作前** (5 分鐘)

### 1. 檢查狀態
```powershell
# 切換到專案目錄
cd C:\AI\projects\multilingual_rag_live2d_scaffold

# 檢查 Git 狀態
git status
git pull origin master  # 同步最新變更

# 檢查環境
python --version
ollama list
```

### 2. 建立今日日誌
```powershell
# 建立今日工作日誌
$today = Get-Date -Format "yyyy-MM-dd"
New-Item "docs/daily_logs/$today.md" -ItemType File -Force

# 日誌模板
@"
# 工作日誌 - $today

## 🎯 今日目標
- [ ] 目標1：具體要完成的功能
- [ ] 目標2：要修復的問題
- [ ] 目標3：要測試的模組

## 📝 工作紀錄
### 上午 (9:00-12:00)
- 時間：
- 工作內容：
- 遇到問題：
- 解決方案：

### 下午 (13:00-18:00)  
- 時間：
- 工作內容：
- 遇到問題：
- 解決方案：

## 🔧 技術筆記
- 新學到的東西：
- 有用的指令/程式碼：
- 參考資料連結：

## 📊 今日成果
- 完成功能：
- 修復問題：
- 程式碼行數：+XXX/-XXX
- 測試通過率：

## 🚀 明日計劃
- 優先任務：
- 待解決問題：
- 預期困難：
"@ | Out-File "docs/daily_logs/$today.md" -Encoding UTF8
```

---

## 💼 **開發過程中** (持續更新)

### 每完成一個功能模組
```powershell
# 1. 檢查變更
git status
git diff

# 2. 添加變更
git add packages/rag/generation/3_Answer_llm/core_parallel.py
git add docs/daily_logs/$(Get-Date -Format 'yyyy-MM-dd').md

# 3. 專業提交訊息
git commit -m "feat: 實作並行處理核心模組

## 功能
- 新增 core_parallel.py 支援 32 worker 並行處理
- 優化記憶體使用，支援大批量資料處理
- 加入 GPU 使用率監控和自動調節

## 測試
- 通過 100 chunks 壓力測試  
- 效能提升 40% (12.3 → 17.2 chunks/sec)
- 記憶體使用穩定在 16GB 以下

## 文檔
- 更新今日工作日誌
- 新增效能測試結果

Closes #23"

# 4. 推送變更
git push
```

---

## 🌅 **每日結束前** (10 分鐘)

### 1. 更新專案 README 的「最近更新」區段
```markdown
## 📊 最近更新

### 🗓️ 2025-08-23
- ✅ **完成**: 並行處理核心模組 (core_parallel.py)
- ✅ **優化**: Answer LLM 效能提升 40%
- ✅ **測試**: 大批量資料處理穩定性驗證
- 🚧 **進行中**: Live2D TTS 整合 (60% 完成)
- 📝 **文檔**: 更新效能測試報告

### 🗓️ 2025-08-22  
- ✅ **完成**: Git 版本控制系統建置
- ✅ **完成**: 專業級 README 文檔
- ✅ **優化**: .gitignore 設定和專案結構
```

### 2. 日誌總結提交
```powershell
# 更新 README 和日誌
git add README.md
git add docs/daily_logs/

# 每日總結提交
git commit -m "docs: $(Get-Date -Format 'yyyy-MM-dd') 工作總結

## 今日完成
- 實作並行處理核心模組
- 效能優化和壓力測試
- 文檔更新

## 明日計劃  
- Live2D 角色整合
- TTS 語音合成測試
- API 端點開發

工作時長: 8h | 程式碼: +347/-23 | 測試通過: ✅"

git push
```

---

## 🤖 **讓下個對話的 Claude 快速了解狀況**

### **在專案根目錄建立 STATUS.md**
```markdown
# 🎯 專案現況總覽

## 📅 最後更新：2025-08-23 18:00

### 🚀 目前狀態
- **整體進度**: 65% 完成  
- **當前重點**: Live2D 整合開發
- **下個里程碑**: 完整 Demo 展示 (目標: 9/1)

### ✅ 已完成模組
1. **資料處理 Pipeline** (100%)
   - PDF 抽取和 chunking
   - 向量索引建立 
   - 多語言支援

2. **問答生成系統** (95%)
   - 問題自動生成
   - 並行答案生成 (新增!)
   - 品質審核機制

3. **開發基礎設施** (100%)
   - Git 版本控制
   - Docker 容器化準備
   - 專業文檔

### 🚧 進行中
1. **Live2D 整合** (60%)
   - TTS 語音合成: 測試中
   - 嘴型同步: 待實作
   - 角色模型: 已準備

2. **API 服務** (30%)  
   - FastAPI 框架: 已初始化
   - 端點設計: 規劃中

### ❓ 當前問題
1. Live2D SDK 授權和設定
2. TTS 服務選擇 (Azure vs OpenAI)
3. 部署環境資源需求評估

### 🎯 即將開始
- Live2D 角色載入測試
- TTS 多語音測試  
- 效能瓶頸分析

### 💡 技術債務
- 單元測試覆蓋率待提升
- 錯誤處理機制待完善
- 監控和日誌系統待建立
```

---

## 🎯 **對話開始模板**

**每次開始新對話時，您可以說**：
```
嗨 Claude，我是 RAG Pipeline 專案的開發者。

請先查看我的 STATUS.md 了解目前專案狀況，
然後查看最新的 daily_logs/2025-XX-XX.md 了解今日進度。

我想討論：[具體問題或需求]
```

## 🏆 **這個流程的好處**

### **對您**
- 📈 **清晰追蹤進度**
- 🧠 **不會忘記重要細節**
- 💼 **面試時完美展示**
- 🔍 **問題調試更容易**

### **對未來的 Claude**
- ⚡ **瞬間了解專案狀況**
- 🎯 **精準提供建議**
- 🔄 **延續開發思路**
- 💡 **避免重複說明**

**這樣您就建立了一個專業的開發工作流程！** 🚀

想要立即開始實施這個流程嗎？我可以協助您建立第一天的工作日誌！
