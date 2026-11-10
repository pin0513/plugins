#!/usr/bin/env python3
"""第一階段確定性檢查：找出讀者無法自行解讀的文字。

檢查四件事：
  未定義標籤   代號（P50、BUDGET-1、Q1～Q4、SDD、判準①、⚪）首次出現時沒有定義
  對話殘留     文件引用了只存在於對話中的內容（「本次對話」「as discussed」）
  表格過載     表格單格字數超過門檻，比較功能被細節擠壞
  來源失效     設定檔登錄的術語來源檔不存在

定義來源除了文件本身，也包含 repo 裡的 glossary（名詞表）。找不到 glossary 時略過，
不報錯；只有設定檔明確指定的 glossary 不存在時才回報。

用法：
  prose_check.py FILE [FILE...] [--json]   命令列模式；有發現時 exit 1
  prose_check.py --hook                    PostToolUse：檢查剛寫入的 Markdown，
                                           有發現時寫到 stderr 並 exit 2（回饋給 Claude）
  prose_check.py --session-start           SessionStart：輸出寫作規則與 glossary 詞彙清單，
                                           stdout 會加入 Claude 的 context
  prose_check.py --stop                    Stop：檢查最後一則給人看的回覆，只寫紀錄、不阻擋
  prose_check.py --report [LOG]            彙整 Stop 紀錄，找出高頻問題

只用 Python 標準函式庫。
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import sys
from dataclasses import dataclass, asdict

# ── 預設設定 ─────────────────────────────────────────────
DEFAULT_CONFIG = {
    "mode": "feedback",            # feedback：回饋給 Claude；off：停用 hook
    "include": ["**/*.md"],
    "exclude": ["**/CHANGELOG.md", "**/node_modules/**", "**/.git/**"],
    "max_cell_chars": 40,
    "max_findings": 15,
    "known_terms": {},             # {"BUDGET-1": "docs/rules/budget.md"}：術語 → 定義來源
    "allow_terms": [],             # 讀者一定認得、不需要定義的詞
    "glossary_files": [],          # 明確指定的 glossary；空清單代表自動搜尋
    "glossary_autodiscover": True,
    "console_mode": "log",         # log：Stop 時寫紀錄；off：不檢查
    "console_log": ".prose-check/console-log.jsonl",
}

# glossary 自動搜尋：檔名（不分大小寫、不含副檔名）或目錄名符合即採用
GLOSSARY_NAMES = {"glossary", "terms", "terminology", "ubiquitous-language", "ubiquitous_language",
                  "名詞", "名詞表", "名詞庫", "詞彙", "詞彙表", "術語", "術語表"}
SKIP_DIRS = {".git", "node_modules", "bin", "obj", "dist", "build", "out", ".venv", "venv",
             "packages", ".vs", ".idea", "target", "__pycache__"}
SOURCE_HEADERS = {"來源", "出處", "source", "sources", "ref", "reference"}

# 工程讀者普遍認得的縮寫；專案可用 allow_terms 擴充
COMMON_TERMS = set("""
AI API APIs CI CD CLI CPU CRUD CSS CSV DB DNS GPU HTML HTTP HTTPS ID IDE IO IP JSON JWT
KPI LLM MCP MVP OK ORM OS PDF PM PR QA RAM REST ROI SDK SLA SLO SQL SSH SSO TDD TLS UI URL
UTF UTF-8 UX XML YAML MD JS TS AWS GCP ETL FAQ TODO README README.md OAuth DDD CQRS
""".split())

LEAK_PHRASES = [
    "本次對話", "這次對話", "此次對話", "對話自創", "剛才討論", "剛剛討論", "我們討論過",
    "如我們所討論", "上一輪", "前面的對話", "對話中提到", "見對話",
    "as discussed", "as we discussed", "earlier in this conversation", "per our discussion",
    "in our conversation", "discussed above in chat",
]

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
STATUS_EMOJI = "⚪⚫🔴🟠🟡🟢🔵🟣🟤"

RE_RANGE = re.compile(r"(?<![A-Za-z0-9_\-./])([A-Z]{1,8})(\d+)\s*[～~–—]\s*(?:\1)?(\d+)(?![A-Za-z0-9_])")
RE_ID = re.compile(r"(?<![A-Za-z0-9_\-./])([A-Z]{1,8}-?\d+(?:\.\d+)?)(?![A-Za-z0-9_])")
RE_NO = re.compile(r"(?<![A-Za-z0-9_])(No\.\s?\d+)")
RE_PLACEHOLDER = re.compile(r"(?<![A-Za-z0-9_\-])([A-Z]-x{1,3})(?![A-Za-z0-9_])")
RE_ACRONYM = re.compile(r"(?<![A-Za-z0-9_\-./])([A-Z]{2,6})(?![A-Za-z0-9_\-]|\.[A-Za-z])")  # SKILL.md 是檔名，不是縮寫
RE_CIRCLED = re.compile(r"([\u4e00-\u9fffA-Za-z]{1,6})\s*([" + CIRCLED + r"])")
RE_EMOJI = re.compile("([" + STATUS_EMOJI + "])")
# 「方案 B」「根因 B」：AI 常為選項或段落臨時取的單字母代號
LETTER_PREFIXES = "方案|根因|選項|情境|階段|路線|版本|模式|類型|原因|問題|風險|做法|案例|假設"
RE_PREFIX_LETTER = re.compile(r"(" + LETTER_PREFIXES + r")\s?([A-Z])(?![A-Za-z0-9_])")
# 「依 4.1」「見 2.3 節」：引用章節編號
RE_SECREF = re.compile(r"(?:依|見|參照|參考|如|同|照)\s*(?:第\s*)?(\d+(?:\.\d+)+)")

RE_GLOSS_AFTER = re.compile(r"\s?[（(][^）)\n]{2,}[）)]")
RE_DEF_VERB_AFTER = re.compile(r"\s*(是|指|代表|意指|表示|＝|=|：|:)")


@dataclass
class Finding:
    check: str      # 檢查名稱（白話）
    line: int
    term: str
    message: str


# ── 設定 ────────────────────────────────────────────────
def load_config(start_dir: str) -> tuple[dict, str]:
    """從檔案所在目錄往上找 .prose-check.json；找不到就用預設值。"""
    cfg = dict(DEFAULT_CONFIG)
    d = os.path.abspath(start_dir)
    while True:
        p = os.path.join(d, ".prose-check.json")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                cfg.update(json.load(f))
            return cfg, d
        parent = os.path.dirname(d)
        if parent == d:
            return cfg, os.environ.get("CLAUDE_PROJECT_DIR", os.path.abspath(start_dir))
        d = parent


def in_scope(path: str, root: str, cfg: dict) -> bool:
    rel = "./" + os.path.relpath(os.path.abspath(path), root).replace(os.sep, "/")
    if any(fnmatch.fnmatch(rel, pat) for pat in cfg["exclude"]):
        return False
    return any(fnmatch.fnmatch(rel, pat) for pat in cfg["include"])


# ── 前處理：遮掉不算文字的部分，保留行號 ─────────────────
def _blank(m: re.Match) -> str:
    return re.sub(r"[^\n]", " ", m.group(0))


def mask_non_prose(text: str) -> str:
    text = re.sub(r"```.*?```", _blank, text, flags=re.S)        # fenced code
    text = re.sub(r"~~~.*?~~~", _blank, text, flags=re.S)
    text = re.sub(r"<!--.*?-->", _blank, text, flags=re.S)        # HTML 註解
    text = re.sub(r"`[^`\n]+`", _blank, text)                     # inline code
    text = re.sub(r"\]\([^)\n]*\)", lambda m: "]" + " " * (len(m.group(0)) - 1), text)  # 連結目標
    text = re.sub(r"https?://\S+", _blank, text)
    text = text.replace("**", "  ").replace("__", "  ")            # 粗體標記（保留長度）
    return text


def directives(raw: str) -> tuple[bool, set[str]]:
    # 先遮掉 code：文件裡「示範」指令寫法的 code 不能被當成真的指令
    raw = re.sub(r"```.*?```", _blank, raw, flags=re.S)
    raw = re.sub(r"~~~.*?~~~", _blank, raw, flags=re.S)
    raw = re.sub(r"`[^`\n]+`", _blank, raw)
    off = bool(re.search(r"<!--\s*prose-check:\s*off\s*-->", raw))
    ignored: set[str] = set()
    for m in re.finditer(r"<!--\s*prose-check:\s*ignore\s+(.+?)\s*-->", raw):
        ignored.update(t.strip() for t in m.group(1).split(",") if t.strip())
    return off, ignored


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


# ── 未定義標籤 ───────────────────────────────────────────
def collect_candidates(text: str) -> list[tuple[int, int, str]]:
    """回傳 (start, end, 正規化後的詞)；範圍與長樣式優先，避免重疊重複計算。"""
    spans: list[tuple[int, int, str]] = []

    def free(s: int, e: int) -> bool:
        return all(e <= a or s >= b for a, b, _ in spans)

    for m in RE_RANGE.finditer(text):
        spans.append((m.start(), m.end(), f"{m.group(1)}{m.group(2)}～{m.group(1)}{m.group(3)}"))
    for rx in (RE_NO, RE_PLACEHOLDER, RE_ID):
        for m in rx.finditer(text):
            if free(m.start(1), m.end(1)):
                spans.append((m.start(1), m.end(1), re.sub(r"\s", "", m.group(1))))
    for m in RE_CIRCLED.finditer(text):
        if free(m.start(2), m.end(2)):
            spans.append((m.start(), m.end(), m.group(1) + m.group(2)))
    for m in RE_PREFIX_LETTER.finditer(text):
        if free(m.start(), m.end()):
            spans.append((m.start(), m.end(), m.group(1) + m.group(2)))
    for m in RE_EMOJI.finditer(text):
        spans.append((m.start(), m.end(), m.group(1)))
    for m in RE_ACRONYM.finditer(text):
        if free(m.start(1), m.end(1)):
            spans.append((m.start(1), m.end(1), m.group(1)))
    spans.sort()
    return spans


def is_defining(text: str, start: int, end: int, all_spans) -> bool:
    after = text[end:end + 200]
    if RE_GLOSS_AFTER.match(after):                 # P50（中位數估計）
        return True
    if RE_DEF_VERB_AFTER.match(after):              # G1 是…／⚪：…
        return True
    # 表格的第一欄就是這個詞（glossary 列）
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    line = text[ls: le if le != -1 else len(text)]
    if line.lstrip().startswith("|"):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == text[start:end].strip():
            return True
    term = text[start:end]
    # 圈號代表「某份清單的第 N 項」：讀者需要的是那份清單，前後文的白話不算定義
    if any(ch in CIRCLED for ch in term):
        return False
    # 中位數估計（P50）或（P50，說明…）：詞是括號內的主體，括號前有白話說明
    open_pos = max(text.rfind("（", ls, start), text.rfind("(", ls, start))
    if open_pos != -1:
        close_rel = re.search(r"[）)]", text[open_pos:le if le != -1 else len(text)])
        if close_rel and open_pos + close_rel.start() >= end:
            inner = text[open_pos + 1: open_pos + close_rel.start()].strip()
            term_len = end - start
            others = [s for s in all_spans if open_pos < s[0] < open_pos + close_rel.start() and s[0] != start]
            before = text[ls:open_pos].strip()
            if len(before) >= 2 and len(inner) <= term_len + 8 and not others:
                return True
            # 詞在括號開頭，後面緊接逗號開始解釋：（P50，有一半機會…）
            if len(before) >= 2 and text[open_pos + 1:start].strip() == "" and re.match(r"\s*[，,；;]", text[end:]):
                return True
    return False



# ── glossary ────────────────────────────────────────────
def find_glossaries(root: str, cfg: dict) -> tuple[list[str], list[str]]:
    """回傳 (找到的 glossary 路徑, 明確指定卻不存在的路徑)。都找不到時回傳空清單，不視為錯誤。"""
    if cfg.get("glossary_files"):
        found, missing = [], []
        for g in cfg["glossary_files"]:
            p = os.path.join(root, g)
            (found if os.path.isfile(p) else missing).append(p if os.path.isfile(p) else g)
        return found, missing
    if not cfg.get("glossary_autodiscover", True):
        return [], []
    found = []
    base_depth = root.rstrip(os.sep).count(os.sep)
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
        if d.count(os.sep) - base_depth >= 4:
            dirs[:] = []
        in_glossary_dir = os.path.basename(d).lower() in GLOSSARY_NAMES
        for f in files:
            stem, ext = os.path.splitext(f)
            if ext.lower() in (".md", ".markdown") and (in_glossary_dir or stem.lower() in GLOSSARY_NAMES):
                found.append(os.path.join(d, f))
    return sorted(found), []


def parse_glossary(path: str) -> tuple[dict[str, int], list[tuple[int, str]]]:
    """解析 glossary，回傳 ({詞: 行號}, [(行號, 缺少來源的詞)])。
    支援三種格式：表格第一欄、「- **詞**：定義」、「### 詞」標題。"""
    terms: dict[str, int] = {}
    no_source: list[tuple[int, str]] = []
    try:
        lines = open(path, encoding="utf-8").read().split("\n")
    except OSError:
        return terms, no_source
    header, src_col = None, None
    for i, line in enumerate(lines, start=1):
        st = line.strip()
        if st.startswith("|"):
            cells = [c.strip() for c in st.strip("|").split("|")]
            if re.fullmatch(r"\|[\s:\-|]+\|?", st):
                continue
            if header is None:
                header = [c.lower() for c in cells]
                src_col = next((k for k, h in enumerate(header) if h in SOURCE_HEADERS), None)
                continue
            term = cells[0].replace("**", "").replace("`", "").strip()
            if term:
                terms.setdefault(term, i)
                if src_col is not None and (src_col >= len(cells) or not cells[src_col]):
                    no_source.append((i, term))
            continue
        header, src_col = None, None
        m = re.match(r"^[-*]\s+\*\*(.+?)\*\*\s*[：:]", st) or re.match(r"^#{2,4}\s+(.+?)\s*$", st)
        if m:
            terms.setdefault(m.group(1).replace("`", "").strip(), i)
    return terms, no_source


def glossary_terms(root: str, cfg: dict) -> tuple[dict[str, str], list[str]]:
    """回傳 ({詞: 定義所在的 glossary 路徑}, 明確指定卻不存在的路徑)。"""
    found, missing = find_glossaries(root, cfg)
    out: dict[str, str] = {}
    for g in found:
        for t in parse_glossary(g)[0]:
            out.setdefault(t, os.path.relpath(g, root))
    return out, missing


def is_glossary_file(path: str, root: str, cfg: dict) -> bool:
    return os.path.abspath(path) in {os.path.abspath(g) for g in find_glossaries(root, cfg)[0]}


def check_labels(text: str, cfg: dict, cfg_root: str, ignored: set[str],
                 extra_allowed: set[str] = frozenset(), undefined_label: str = "未定義標籤",
                 undefined_msg: str = "首次出現時沒有定義。") -> list[Finding]:
    gloss, _ = glossary_terms(cfg_root, cfg)
    allow = COMMON_TERMS | set(cfg["allow_terms"]) | ignored | set(gloss) | set(extra_allowed)
    known = cfg["known_terms"]
    spans = collect_candidates(text)
    seen: dict[str, bool] = {}
    out: list[Finding] = []
    for s, e, term in spans:
        if term in seen or term in allow:
            continue
        if term in known:
            seen[term] = True
            src = known[term]
            if not str(src).startswith(("http://", "https://")) and not os.path.exists(os.path.join(cfg_root, src)):
                out.append(Finding("來源失效", line_of(text, s), term,
                                   f"「{term}」登錄的定義來源 {src} 不存在。修正來源路徑，或在首次出現處直接定義。"))
            continue
        seen[term] = True
        if not is_defining(text, s, e, spans):
            out.append(Finding(undefined_label, line_of(text, s), term, f"「{term}」{undefined_msg}"))
    return out


# ── 對話殘留 ─────────────────────────────────────────────
def check_leaks(text: str) -> list[Finding]:
    out = []
    low = text.lower()
    for ph in LEAK_PHRASES:
        for m in re.finditer(re.escape(ph.lower()), low):
            out.append(Finding("對話殘留", line_of(text, m.start()), ph,
                               f"「{ph}」指向讀者看不到的對話。把內容寫進文件，或寫進規則檔後引用。"))
    return out


# ── 表格過載 ─────────────────────────────────────────────
def visible_len(cell: str) -> int:
    cell = re.sub(r"\s+", " ", cell).strip()
    return len(cell)


def check_tables(text: str, cfg: dict) -> list[Finding]:
    out = []
    limit = cfg["max_cell_chars"]
    for i, line in enumerate(text.split("\n"), start=1):
        st = line.strip()
        if not st.startswith("|") or re.fullmatch(r"\|[\s:\-|]+\|?", st):
            continue
        cells = [c for c in st.strip("|").split("|")]
        longest = max((visible_len(c) for c in cells), default=0)
        if longest > limit:
            out.append(Finding("表格過載", i, f"{longest} 字",
                               f"表格單格 {longest} 字，超過 {limit} 字。格子只放可比較的短句，細節移到表格下方。"))
    return out


# ── 主流程 ───────────────────────────────────────────────
def check_file(path: str, cfg: dict, cfg_root: str) -> list[Finding]:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    off, ignored = directives(raw)
    if off:
        return []
    text = mask_non_prose(raw)
    findings = check_labels(text, cfg, cfg_root, ignored) + check_leaks(text) + check_tables(text, cfg)
    for g in glossary_terms(cfg_root, cfg)[1]:
        findings.append(Finding("來源失效", 1, g, f"設定檔指定的 glossary {g} 不存在。修正 glossary_files，或移除該設定改用自動搜尋。"))
    if is_glossary_file(path, cfg_root, cfg):
        for ln, term in parse_glossary(path)[1]:
            findings.append(Finding("來源缺漏", ln, term,
                                    f"glossary 條目「{term}」沒有填來源。條目要能回溯到 ADR、規則檔或 PR，否則不登錄。"))
    findings.sort(key=lambda x: (x.line, x.check))
    return findings


GUIDE = """處理方式（依定義來源決定，不要一律刪除）：
- repo 有 glossary 時：優先改用 glossary 裡既有的詞；glossary 裡的詞視為已定義。
- 業界通用的詞：保留，首次出現時加括號說明。
- 團隊規則檔裡有定義的代號：保留代號當索引，同時寫出內容；或登錄到 .prose-check.json 的 known_terms 並附來源。
- 只存在對話裡的代號：刪掉改寫成白話，或先登錄進 glossary（附來源）再引用。對話不是讀者打得開的來源。
- 不知道代號意思時：標【待補】並問使用者，不要自己猜一個定義。
- 表格過載：表格只放一眼可比較的短句，定義與細節移到表格下方第二層。
- 確定是誤報：在檔案中加 <!-- prose-check: ignore 詞1, 詞2 -->。
文件屬於 skills/ 或 docs/ 時，修完後建議再跑 prose-review skill 做冷讀者理解測試。"""


def render(path: str, findings: list[Finding], cap: int) -> str:
    lines = [f"[reader-based-prose] {path}：發現 {len(findings)} 個讀者無法自行解讀的地方。"]
    for f in findings[:cap]:
        lines.append(f"  第 {f.line} 行［{f.check}］{f.message}")
    if len(findings) > cap:
        lines.append(f"  ……另有 {len(findings) - cap} 項未列出。")
    lines.append(GUIDE)
    return "\n".join(lines)


def run_hook() -> int:
    if os.environ.get("PROSE_CHECK_DISABLE") == "1":
        return 0
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path.lower().endswith((".md", ".markdown")) or not os.path.isfile(path):
        return 0
    cfg, root = load_config(os.path.dirname(os.path.abspath(path)))
    if cfg.get("mode") == "off" or not in_scope(path, root, cfg):
        return 0
    findings = check_file(path, cfg, root)
    if not findings:
        return 0
    sys.stderr.write(render(path, findings, cfg["max_findings"]) + "\n")
    return 2


def run_cli(args: list[str]) -> int:
    as_json = "--json" in args
    files = [a for a in args if not a.startswith("--")]
    if not files:
        sys.stderr.write(__doc__)
        return 2
    report, total = {}, 0
    for p in files:
        cfg, root = load_config(os.path.dirname(os.path.abspath(p)))
        fs = check_file(p, cfg, root)
        total += len(fs)
        report[p] = [asdict(f) for f in fs]
        if not as_json:
            print(render(p, fs, 10**6) if fs else f"[reader-based-prose] {p}：沒有發現。")
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if total else 0


# ── SessionStart：預防 ──────────────────────────────────
CONSOLE_RULES = """[reader-based-prose] 給人看的文字（回覆、摘要、報告、文件）遵守以下規則：
1. 不為選項、原因、段落臨時取代號（方案 B、根因 B、Q1～Q4）。使用者沒用過的代號，不要在後續回覆中引用；需要引用時，寫出內容本身。
2. 不引用前一則回覆的章節編號（依 4.1）；直接寫出被引用的內容。
3. 代號首次出現就定義。業界通用縮寫（API、SQL、PR）除外。
4. 日常詞不賦予私有意思；兩個概念的名稱要能區分。
5. 表格每格一眼讀完，細節放表格下方。
6. 不知道代號意思就標【待補】並詢問，不自己編定義。"""


def run_session_start() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    cfg, root = load_config(root)
    out = [CONSOLE_RULES]
    gloss, missing = glossary_terms(root, cfg)
    if gloss:
        files = sorted(set(gloss.values()))
        terms = sorted(gloss)
        listed = "、".join(terms[:200])
        more = f"（另有 {len(terms) - 200} 個未列出）" if len(terms) > 200 else ""
        out.append(f"\n本 repo 的 glossary：{'、'.join(files)}。已登錄的詞：{listed}{more}。"
                   "寫作時優先使用這些詞，不另取同義的新詞；需要定義時讀 glossary 檔。"
                   "要長期使用的新詞，先登錄進 glossary 並附來源，再引用。")
    for g in missing:
        out.append(f"\n注意：設定檔指定的 glossary {g} 不存在。")
    print("\n".join(out))
    return 0


# ── Stop：檢查給人看的回覆，只寫紀錄 ──────────────────────
def _text_of(content) -> tuple[str, bool]:
    """回傳 (文字, 是否為人類輸入)。tool_result 不算人類輸入。"""
    if isinstance(content, str):
        return content, True
    parts, human = [], False
    for b in content or []:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
            human = True
    return "\n".join(parts), human


def read_transcript(path: str) -> tuple[str, str]:
    """回傳 (所有人類訊息的文字, 最後一輪 assistant 回覆的文字)。"""
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
    human_texts, last_human_idx = [], -1
    for i, e in enumerate(entries):
        if e.get("type") == "user" and not e.get("isMeta"):
            text, human = _text_of((e.get("message") or {}).get("content"))
            if human:
                human_texts.append(text)
                last_human_idx = i
    reply = []
    for e in entries[last_human_idx + 1:]:
        if e.get("type") == "assistant":
            reply.append(_text_of((e.get("message") or {}).get("content"))[0])
    return "\n".join(human_texts), "\n".join(t for t in reply if t)


def check_console(reply: str, human_text: str, cfg: dict, root: str) -> list[Finding]:
    text = mask_non_prose(reply)
    human_masked = human_text
    used_by_human = {t for _, _, t in collect_candidates(human_masked)}
    findings = check_labels(text, cfg, root, set(), extra_allowed=used_by_human,
                            undefined_label="模型自創代號",
                            undefined_msg="不是使用者提出的詞，這則回覆也沒有定義它。")
    headings = set(re.findall(r"^#{1,6}\s*(\d+(?:\.\d+)+)", text, flags=re.M))
    for m in RE_SECREF.finditer(text):
        if m.group(1) not in headings:
            findings.append(Finding("跨回合引用", line_of(text, m.start()), m.group(1),
                                    f"引用了「{m.group(1)}」，但這則回覆沒有這個章節；讀者要往上捲才找得到。"))
    findings += check_tables(text, cfg)
    return sorted(findings, key=lambda x: (x.line, x.check))


def run_stop() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    cfg, root = load_config(root)
    if cfg.get("console_mode") == "off" or os.environ.get("PROSE_CHECK_DISABLE") == "1":
        return 0
    human, reply = "", data.get("last_assistant_message") or ""
    tp = data.get("transcript_path")
    if tp and os.path.isfile(tp):
        human, from_tp = read_transcript(tp)
        reply = from_tp or reply
    if not reply.strip():
        return 0
    findings = check_console(reply, human, cfg, root)
    if findings:
        log = os.path.join(root, cfg["console_log"])
        os.makedirs(os.path.dirname(log), exist_ok=True)
        import datetime
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": datetime.datetime.now().isoformat(timespec="seconds"),
                                "session_id": data.get("session_id"),
                                "findings": [asdict(x) for x in findings]}, ensure_ascii=False) + "\n")
    return 0   # 只寫紀錄：文字已經顯示，阻擋只會讓 Claude 在後面補一段更正


def run_report(args: list[str]) -> int:
    import collections
    cfg, root = load_config(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    path = next((a for a in args if not a.startswith("--")), os.path.join(root, cfg["console_log"]))
    if not os.path.isfile(path):
        print(f"[reader-based-prose] 沒有紀錄檔：{path}")
        return 0
    by_check, by_term, replies = collections.Counter(), collections.Counter(), 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            replies += 1
            for x in rec["findings"]:
                by_check[x["check"]] += 1
                by_term[(x["check"], x["term"])] += 1
    print(f"[reader-based-prose] {replies} 則回覆有發現。")
    print("\n| 問題類型 | 次數 |\n|---|---|")
    for k, v in by_check.most_common():
        print(f"| {k} | {v} |")
    print("\n| 問題類型 | 詞 | 次數 |\n|---|---|---|")
    for (c, t), v in by_term.most_common(15):
        print(f"| {c} | {t} | {v} |")
    print("\n高頻出現的詞：登錄進 glossary（附來源），或補進預防規則。")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--hook" in a:
        sys.exit(run_hook())
    if "--session-start" in a:
        sys.exit(run_session_start())
    if "--stop" in a:
        sys.exit(run_stop())
    if "--report" in a:
        sys.exit(run_report(a))
    sys.exit(run_cli(a))
