# pin0513/plugins

Paul 個人通用的 AI 工具市集。給 [Claude Code](https://code.claude.com/docs/en/plugins/create-marketplace) 使用，會陸續在這裡收可公開安裝的 plugin。

## 怎麼加入市集並安裝

在 Claude Code 輸入：

```
/plugin marketplace add pin0513/plugins
```

接著安裝你要的套件，格式是 `套件名稱@pin0513-plugins`。例如：

```
/plugin install reader-based-prose@pin0513-plugins
```

也可以在終端機執行同樣的指令：

```
claude plugin marketplace add pin0513/plugins
claude plugin install reader-based-prose@pin0513-plugins
```

市集識別名稱是 `pin0513-plugins`，與 GitHub 倉庫路徑 `pin0513/plugins` 不同。加入市集時用倉庫路徑，安裝套件時用 `套件名稱@pin0513-plugins`。

## Plugin 一覽

| 名稱 | 版本 | 說明 |
|---|---|---|
| [reader-based-prose](./plugins/reader-based-prose) | 0.5.0 | 檢查 AI 產出的文件是否有未定義代號、對話殘留、表格塞太滿，並以看不到對話的冷讀者確認能否讀懂。 |

詳細說明與原始碼見各套件目錄。目前第一個套件是 [reader-based-prose](https://github.com/pin0513/plugins/tree/main/plugins/reader-based-prose)。

## 這個市集會繼續增加

之後若有新的個人通用 AI 工具，會在上表新增一列，並在 `.claude-plugin/marketplace.json` 的 `plugins` 陣列加一筆。每個套件放在 `plugins/<名稱>/`，並有自己的 README。

## 授權

MIT License。作者 Paul / pin0513，2026。
