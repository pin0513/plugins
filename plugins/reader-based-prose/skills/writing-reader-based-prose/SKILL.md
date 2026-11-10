---
name: writing-reader-based-prose
description: >
  This skill should be used when Claude writes or edits any document a person will read later:
  SKILL.md files, README, architecture decision records, design docs, PR descriptions, handover notes, comparison tables,
  or when the user says "寫文件", "寫 skill", "整理成文件", "write docs", "write a skill".
  It prevents undefined labels, conversation leaks, and overstuffed tables at writing time.
---

# 寫給讀者，不是寫給自己

寫作時的 context 裡有讀者看不到的東西：對話、計畫、子任務回報、先前定義的代號。下筆前先假設讀者只拿到這份文件。

## 寫之前

查看 session 開始時注入的 glossary 詞彙清單。repo 沒有 glossary 時跳過這一步，直接依下列規則寫。

- 要表達的概念在 glossary 裡已有名稱：用那個名稱，不另取同義詞。
- 需要知道定義時：讀 glossary 檔，不要憑名稱猜。
- 要長期使用的新詞：先登錄進 glossary 並附來源（架構決策紀錄、規則檔或 PR），再在文件中引用。沒有來源的詞不登錄。

## 寫作時遵守

1. **每個代號首次出現就定義**：`P50（中位數估計，有一半機會在此時數內完成）`。業界通用、工程師一定認得的縮寫（API、SQL、PR）除外。repo 內的文件，可改用連結指向 glossary 條目；會離開 repo 的文字（PR 描述、給 PM 的報告），仍要寫出一句白話。
2. **不在文件裡發明代號**：在對話中為了方便而取的代號（例如 `方案 B`、`T1～T4`、`Phase-3`），寫進文件時一律改成白話。要長期使用的代號，先登錄進 glossary，再引用。
   - 回覆給人看時也一樣：使用者沒用過的代號，不在後續回覆中引用；也不寫 `依 4.1` 這類指向前一則回覆的編號，直接寫出內容。
3. **不引用對話**：不寫 `本次對話`、`如前所述`（指對話時）、`as discussed` 這類指向對話的說法。需要的內容直接寫進文件。
4. **日常詞不賦予私有意思**：`上限`、`未判定` 這類詞，讀者會照日常意思理解，而且不會察覺自己讀錯。需要特定意思時，換一個不會誤讀的詞。
5. **一個概念一個詞**：兩個狀態意思接近時，名稱要能區分（`可能性未查證` 與 `嚴重性未評估`，不要都叫 `未判定`）。
6. **表格只放可比較的短句**：每格一眼讀完。定義與細節放在表格下方的第二層。
7. **範例必須比被解釋的東西更好懂**：範例本身含代號時，改用白話描述的具體情境。
8. **不知道就標【待補】**：不替使用者編定義。

## 寫完後

文件寫入後，reader-based-prose hook 會自動執行確定性檢查。收到回饋就依回饋修正；屬於 skills/ 或 docs/ 的文件，修完後建議跑 prose-review skill。
