# 文獻依據

| 檢查項目 | 文獻 |
|---|---|
| 未定義標籤、對話殘留 | Flower 1979 |
| 私有定義、冷讀者測試 | Pinker 2014 |
| 段落銜接、層級 | Gopen 與 Swan 1990 |
| 首次使用即定義 | Vale、Microsoft 與 Google 風格指南 |
| 術語一致 | Anthropic skill 撰寫指南 |

## 各文獻的核心主張

**Flower, L. (1979). Writer-Based Prose: A Cognitive Basis for Problems in Writing. *College English*, 41(1), 19–37.**
作者本位文字（writer-based prose）把作者的思考過程原樣交出，使用對作者有意義、對讀者沒有意義的代號詞。好的寫作要把它轉換成讀者本位文字（reader-based prose）。

**Pinker, S. (2014). *The Sense of Style*, Ch. 3 "The Curse of Knowledge".**
知識的詛咒：作者難以想像別人不知道自己知道的事。成因是 chunking（把概念打包成縮寫）與 functional fixity（以用途而非本質描述事物）。解方是從真實讀者取得回饋訊號；本 plugin 的冷讀者測試即依此設計。

**Gopen, G. D., & Swan, J. A. (1990). The Science of Scientific Writing. *American Scientist*, 78(6), 550–558.**
句首（topic position）放連回前文的舊資訊，句尾（stress position）放要強調的新資訊。句中完全沒有舊資訊時，讀者必須自己建構邏輯連結。

**Vale 的 conditional 規則；Microsoft 與 Google 風格指南的 Acronyms 規則。**
縮寫在首次出現時必須定義。本 plugin 更嚴格：要求首次出現的位置就是定義，表格後方的 glossary 不算。

**Anthropic, Skill authoring best practices.**
同一概念全文使用同一個詞。

## 為什麼 AI 產出特別容易出現這些問題

這一段是推論，不是文獻結論：模型的 context 裡有對話、計畫與 subagent 回報，文件讀者看不到這些內容。標籤的定義留在對話中，文件只帶走代號。實例：某份 AI 產出的 glossary 直接註明代號是在對話中自創的。

## 為什麼第三階段不是每次都跑

版本比較只回答「有代號」和「沒代號」哪個好懂，看不到表格過載這類層級問題；而它能回答的問題，大部分已經被決策表回答。因此只用在規則判不出的情況，以及離線校準決策表。
