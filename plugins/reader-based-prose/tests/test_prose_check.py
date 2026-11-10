"""以 evals/fixtures 驗證第一階段檢查：負面樣本必須被抓到，正面樣本必須零發現。"""
import json, os, subprocess, sys, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import prose_check as pc  # noqa: E402

FIX = os.path.join(ROOT, "evals", "fixtures")


def run(name):
    p = os.path.join(FIX, name)
    cfg, root = pc.load_config(FIX)
    return pc.check_file(p, cfg, root)


class LabelTable(unittest.TestCase):
    def setUp(self):
        self.f = run("bad-label-table.md")
        self.terms = {x.term for x in self.f if x.check == "未定義標籤"}

    def test_catches_codes(self):
        for t in ["SDD", "P50", "BUDGET-1", "G1", "G2", "Q1～Q4", "判準①", "⚪", "No.17", "F-xx", "No.21"]:
            self.assertIn(t, self.terms, t)

    def test_range_not_split(self):
        self.assertNotIn("Q1", self.terms)
        self.assertNotIn("Q4", self.terms)

    def test_glossary_after_use_does_not_count(self):
        # Q1～Q4 在 glossary 才定義，但首次出現在表格裡，仍應被抓
        self.assertIn("Q1～Q4", self.terms)

    def test_catches_conversation_leak(self):
        self.assertTrue(any(x.check == "對話殘留" for x in self.f))

    def test_common_terms_allowed(self):
        self.assertNotIn("PM", self.terms)
        self.assertNotIn("AI", self.terms)


class Overstuffed(unittest.TestCase):
    def test_cell_overload(self):
        f = run("bad-overstuffed-table.md")
        self.assertTrue(any(x.check == "表格過載" for x in f))
        # 這份的代號都有定義，所以不應有未定義標籤
        self.assertEqual([x.term for x in f if x.check == "未定義標籤"], [])


class Good(unittest.TestCase):
    def test_zero_findings(self):
        f = run("good-two-layer.md")
        self.assertEqual([(x.line, x.check, x.term) for x in f], [])


class Directives(unittest.TestCase):
    def test_ignore_and_off(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("<!-- prose-check: ignore XYZ -->\n依 XYZ 處理。\n")
            cfg, root = pc.load_config(d)
            self.assertEqual(pc.check_file(p, cfg, root), [])
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("<!-- prose-check: off -->\n依 XYZ 與 ABC-3 處理。\n")
            self.assertEqual(pc.check_file(p, cfg, root), [])

    def test_known_terms_source_must_exist(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, ".prose-check.json"), "w") as fh:
                json.dump({"known_terms": {"ABC-3": "rules/abc.md", "XYZ": "rules/xyz.md"}}, fh)
            os.makedirs(os.path.join(d, "rules"))
            open(os.path.join(d, "rules", "xyz.md"), "w").close()
            p = os.path.join(d, "a.md")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("依 XYZ 與 ABC-3 處理。\n")
            cfg, root = pc.load_config(d)
            f = pc.check_file(p, cfg, root)
            self.assertEqual([(x.check, x.term) for x in f], [("來源失效", "ABC-3")])

    def test_directive_inside_code_is_not_a_directive(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("寫法：`<!-- prose-check: off -->`\n依 XYZ 處理。\n")
            cfg, root = pc.load_config(d)
            self.assertEqual([x.term for x in pc.check_file(p, cfg, root)], ["XYZ"])

    def test_filename_is_not_acronym(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.md")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("修改 SKILL.md 與 README.md。\n")
            cfg, root = pc.load_config(d)
            self.assertEqual(pc.check_file(p, cfg, root), [])


class HookMode(unittest.TestCase):
    def _hook(self, path):
        return subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "prose_check.py"), "--hook"],
                              input=json.dumps({"tool_input": {"file_path": path}}),
                              capture_output=True, text=True)

    def test_bad_exits_2_with_feedback(self):
        r = self._hook(os.path.join(FIX, "bad-label-table.md"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("未定義標籤", r.stderr)

    def test_good_exits_0(self):
        r = self._hook(os.path.join(FIX, "good-two-layer.md"))
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_non_markdown_ignored(self):
        r = self._hook(os.path.join(ROOT, "scripts", "prose_check.py"))
        self.assertEqual(r.returncode, 0)


# ── glossary、SessionStart、Stop ─────────────────────────
import tempfile  # noqa: E402

SCRIPT = os.path.join(ROOT, "scripts", "prose_check.py")


def write(d, rel, content):
    p = os.path.join(d, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(content)
    return p


GLOSSARY = """# 名詞表

| 詞 | 定義 | 來源 |
|---|---|---|
| BUDGET-1 | 開工前和 PM 對齊預算的三個問題 | docs/rules/budget.md |
| G1 | 人逐項看過估工明細並同意 | |
"""


class Glossary(unittest.TestCase):
    def test_absent_glossary_is_optional(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "docs/a.md", "依 BUDGET-1 處理。\n")
            cfg, root = pc.load_config(d)
            f = pc.check_file(p, cfg, root)
            self.assertEqual([(x.check, x.term) for x in f], [("未定義標籤", "BUDGET-1")])

    def test_autodiscovered_glossary_defines_terms(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "docs/glossary.md", GLOSSARY)
            p = write(d, "docs/a.md", "依 BUDGET-1 與 G1 處理，再看 Z9。\n")
            cfg, root = pc.load_config(d)
            self.assertEqual([x.term for x in pc.check_file(p, cfg, root)], ["Z9"])

    def test_chinese_glossary_name(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "docs/名詞表.md", GLOSSARY)
            p = write(d, "a.md", "依 BUDGET-1 處理。\n")
            cfg, root = pc.load_config(d)
            self.assertEqual(pc.check_file(p, cfg, root), [])

    def test_glossary_in_skipped_dir_is_ignored(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "node_modules/x/glossary.md", GLOSSARY)
            p = write(d, "a.md", "依 BUDGET-1 處理。\n")
            cfg, root = pc.load_config(d)
            self.assertEqual([x.term for x in pc.check_file(p, cfg, root)], ["BUDGET-1"])

    def test_configured_but_missing_glossary_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, ".prose-check.json", json.dumps({"glossary_files": ["docs/terms.md"]}))
            p = write(d, "a.md", "一般文字。\n")
            cfg, root = pc.load_config(d)
            self.assertEqual([(x.check, x.term) for x in pc.check_file(p, cfg, root)],
                             [("來源失效", "docs/terms.md")])

    def test_glossary_entry_without_source(self):
        with tempfile.TemporaryDirectory() as d:
            g = write(d, "docs/glossary.md", GLOSSARY)
            cfg, root = pc.load_config(d)
            f = pc.check_file(g, cfg, root)
            self.assertEqual([(x.check, x.term) for x in f], [("來源缺漏", "G1")])

    def test_definition_list_and_heading_formats(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "glossary.md", "- **P50**：中位數估計\n\n### ADR-7\n說明。\n")
            p = write(d, "a.md", "看 P50 與 ADR-7。\n")
            cfg, root = pc.load_config(d)
            self.assertEqual(pc.check_file(p, cfg, root), [])


class NewPatterns(unittest.TestCase):
    def test_prefix_letter_label(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, "a.md", "採用方案 B。根因 C（快取失效）已處理。\n")
            cfg, root = pc.load_config(d)
            self.assertEqual([x.term for x in pc.check_file(p, cfg, root)], ["方案B"])


class SessionStart(unittest.TestCase):
    def _run(self, d):
        return subprocess.run([sys.executable, SCRIPT, "--session-start"], input=json.dumps({"cwd": d}),
                              capture_output=True, text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": d})

    def test_rules_without_glossary(self):
        with tempfile.TemporaryDirectory() as d:
            r = self._run(d)
            self.assertEqual(r.returncode, 0)
            self.assertIn("不為選項", r.stdout)
            self.assertNotIn("glossary：", r.stdout)

    def test_rules_with_glossary_terms(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, "docs/glossary.md", GLOSSARY)
            r = self._run(d)
            self.assertIn("BUDGET-1", r.stdout)
            self.assertIn("docs/glossary.md", r.stdout)


def transcript(d, turns):
    lines = []
    for role, text in turns:
        if role == "tool":
            lines.append({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "content": text}]}})
        else:
            lines.append({"type": role, "message": {"role": role, "content":
                          text if role == "user" else [{"type": "text", "text": text}]}})
    return write(d, "t.jsonl", "\n".join(json.dumps(x, ensure_ascii=False) for x in lines))


class Stop(unittest.TestCase):
    def _run(self, d, tp):
        return subprocess.run([sys.executable, SCRIPT, "--stop"],
                              input=json.dumps({"transcript_path": tp, "cwd": d, "session_id": "s1"}),
                              capture_output=True, text=True, env={**os.environ, "CLAUDE_PROJECT_DIR": d})

    def _log(self, d):
        p = os.path.join(d, ".prose-check", "console-log.jsonl")
        if not os.path.isfile(p):
            return []
        return [x for line in open(p, encoding="utf-8") for x in json.loads(line)["findings"]]

    def test_model_invented_labels_logged_user_terms_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            tp = transcript(d, [
                ("user", "請把 L1 的節點整理一下"),
                ("assistant", "根因 B 已處理（舊回合）。"),
                ("user", "繼續"),
                ("tool", "No.99 tool output 不算人類輸入"),
                ("assistant", "L1 已更新。直接證實了根因 B，依 4.1 裁決；No.99 待查。"),
            ])
            r = self._run(d, tp)
            self.assertEqual(r.returncode, 0)   # 不阻擋
            got = {(x["check"], x["term"]) for x in self._log(d)}
            self.assertEqual(got, {("模型自創代號", "根因B"), ("模型自創代號", "No.99"), ("跨回合引用", "4.1")})

    def test_clean_reply_writes_no_log(self):
        with tempfile.TemporaryDirectory() as d:
            tp = transcript(d, [("user", "好"), ("assistant", "## 4.1 範圍\n依 4.1 處理，P50（中位數估計）為 8 小時。")])
            self._run(d, tp)
            self.assertEqual(self._log(d), [])

    def test_report(self):
        with tempfile.TemporaryDirectory() as d:
            tp = transcript(d, [("user", "好"), ("assistant", "採用方案 B。")])
            self._run(d, tp)
            self._run(d, tp)
            r = subprocess.run([sys.executable, SCRIPT, "--report"], capture_output=True, text=True,
                               env={**os.environ, "CLAUDE_PROJECT_DIR": d})
            self.assertIn("| 模型自創代號 | 方案B | 2 |", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
