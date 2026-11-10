---
name: prose-review
description: >
  This skill should be used when the user asks to "review this doc", "審這份文件",
  "檢查易讀性", "檢查 skill 寫得好不好", "冷讀測試", "prose review", or wants to check
  whether an AI-written document or SKILL.md has undefined labels, conversation leaks,
  private meanings of common words, terminology collisions, or overstuffed tables.
  Also use after the reader-based-prose hook reports findings on files under skills/ or docs/.
---

# prose-review：三階段文件審查

目標：讓讀者不用查詢、不用看對話紀錄就能讀懂文件，同時不遺失細節。要降低的是讀者必須自行重建的推論量，不是資訊量。

## 流程

### 第一階段：確定性檢查

執行本 skill 目錄往上兩層的 `scripts/prose_check.py`：

```bash
python3 <plugin 根目錄>/scripts/prose_check.py <檔案> --json
```

輸出列出未定義標籤、對話殘留、表格過載、來源失效。記下每一項，不要在這一步修改檔案。

### 第二階段：冷讀者理解測試

用 Task 工具呼叫 `cold-reader` agent，**只傳檔案路徑，以及 repo 的 glossary 路徑（有的話）**。glossary 是讀者打得開的資源，可以給；對話摘要、背景、「這份文件是在講什麼」不能給。附了背景，冷讀者就和作者一樣知道太多，測試失效。

拿到回報後，以作者身分逐項比對冷讀者的理解：

| 比對結果 | 判定 |
|---|---|
| 冷讀者理解與原意一致 | 通過 |
| 冷讀者標「推測」且猜對 | 可讀但脆弱，補一句定義 |
| 冷讀者理解與原意不同 | **私有定義**：日常詞被賦予特定意思，最危險，必須換詞或定義 |
| 冷讀者標「不懂」 | 參照斷裂，依決策表處理 |
| 冷讀者回報兩詞重疊 | **術語碰撞**：合併，或改成能區分的名稱 |

### 第三階段：版本比較（只在規則判不出時使用）

決策表（`references/decision-table.md`）能判定的情況直接判定，不要跑這一步。只有在「代號有持久來源、只出現一次、展開後可能遺失資訊」這類規則無法裁決的情況，才把兩個版本（保留代號加註 vs. 改寫成白話）交給 `cold-reader` 做比較任務。

## 修改原則

讀 `references/decision-table.md` 決定每個詞的處理方式；讀 `references/layering.md` 處理表格與段落層級。

- 動手改之前，先估「改錯了要還原的成本」：還原成本高（例如 Jira 描述與留言，送出就有人讀）時，只評估並給修改預覽，使用者同意才寫入；還原成本低（例如有版控、沒有未提交修改的本機檔案）時，可以直接改並附上差異。
- 不知道代號原意時，標【待補】並問使用者。不准自己編一個定義。
- 定義只存在對話裡的代號，不准用加註的方式保留；對話不是讀者打得開的來源。
- 修改後重跑第一階段，確認歸零。

## 回報格式

| 詞或位置 | 問題類型 | 裁決 | 依據的規則 | 修改內容 |
|---|---|---|---|---|

「依據的規則」寫決策表的條目名稱，讓使用者可以覆核並反駁。最後列出所有【待補】項目，請使用者補充。
