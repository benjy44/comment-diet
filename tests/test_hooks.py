import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests.loader import cd

BAD = ("// This function parses the config.\n"
       "func Parse() {}\n")
GOOD = "// Parse reads the config at path.\nfunc Parse() {}\n"


def _run(entry, payload, stdout):
    with mock.patch.object(cd.sys, "stdin", io.StringIO(json.dumps(payload))), \
         redirect_stdout(stdout):
        return entry()


def _decision(stdout):
    text = stdout.getvalue().strip()
    return json.loads(text) if text else None


class PostToolUse(unittest.TestCase):
    def test_violation_emits_a_block_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.go")
            with open(path, "w", encoding="utf-8") as f:
                f.write(BAD)
            out = io.StringIO()
            with mock.patch.object(cd, "added_linenos", return_value=None):
                code = _run(cd.post_tool_use_hook,
                            {"tool_input": {"file_path": path}}, out)
        self.assertEqual(code, 0)
        decision = _decision(out)
        self.assertEqual(decision["decision"], "block")
        self.assertIn("filler", decision["reason"])
        self.assertIn(cd.FIX, decision["reason"])

    def test_clean_file_emits_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.go")
            with open(path, "w", encoding="utf-8") as f:
                f.write(GOOD)
            out = io.StringIO()
            with mock.patch.object(cd, "added_linenos", return_value=None):
                _run(cd.post_tool_use_hook, {"tool_input": {"file_path": path}}, out)
        self.assertIsNone(_decision(out))

    def test_unsupported_file_is_ignored(self):
        out = io.StringIO()
        code = _run(cd.post_tool_use_hook, {"tool_input": {"file_path": "a.rb"}}, out)
        self.assertEqual((code, _decision(out)), (0, None))

    def test_missing_file_path_is_ignored(self):
        out = io.StringIO()
        self.assertEqual(_run(cd.post_tool_use_hook, {"tool_input": {}}, out), 0)

    def test_malformed_stdin_is_ignored(self):
        with mock.patch.object(cd.sys, "stdin", io.StringIO("not json")):
            self.assertEqual(cd.post_tool_use_hook(), 0)

    def test_warnings_alone_do_not_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write("# ---------- helpers\nx = 1\n")
            out = io.StringIO()
            with mock.patch.object(cd, "added_linenos", return_value=None):
                _run(cd.post_tool_use_hook, {"tool_input": {"file_path": path}}, out)
        self.assertIsNone(_decision(out))


class StopHook(unittest.TestCase):
    def test_reentry_is_short_circuited(self):
        out = io.StringIO()
        with mock.patch.object(cd, "changed_files", side_effect=AssertionError("scanned")):
            code = _run(cd.stop_hook, {"stop_hook_active": True}, out)
        self.assertEqual((code, _decision(out)), (0, None))

    def test_turn_touched_file_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.go")
            with open(path, "w", encoding="utf-8") as f:
                f.write(BAD)
            out = io.StringIO()
            with mock.patch.object(cd, "changed_files", return_value=[path]), \
                 mock.patch.object(cd, "added_linenos", return_value=None):
                _run(cd.stop_hook, {}, out)
        self.assertEqual(_decision(out)["decision"], "block")

    def test_malformed_stdin_still_scans(self):
        with mock.patch.object(cd.sys, "stdin", io.StringIO("not json")), \
             mock.patch.object(cd, "changed_files", return_value=[]), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(cd.stop_hook(), 0)


class Cli(unittest.TestCase):
    def test_no_arguments_is_usage(self):
        self.assertIn("usage", cd.check_argv([]))

    def test_missing_path_is_reported(self):
        self.assertIn("no such path", cd.check_argv(["/nope/x.go"]))

    def test_unsplit_file_list_hints_at_the_pipe(self):
        self.assertIn("usage", cd.check_argv(["a.go\nb.go"]))

    def test_no_supported_types_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.rb")
            open(path, "w").close()
            self.assertIn("supported file type", cd.check_argv([path]))

    def test_clean_scope_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.go")
            with open(path, "w", encoding="utf-8") as f:
                f.write(GOOD)
            self.assertIsNone(cd.check_argv([path]))
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cd.main([path]), 0)

    def test_violation_exits_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.go")
            with open(path, "w", encoding="utf-8") as f:
                f.write(BAD)
            with redirect_stdout(io.StringIO()), io.StringIO() as err:
                from contextlib import redirect_stderr
                with redirect_stderr(err):
                    self.assertEqual(cd.main([path]), 1)

    def test_bad_invocation_exits_two(self):
        from contextlib import redirect_stderr
        with redirect_stderr(io.StringIO()):
            self.assertEqual(cd.main([]), 2)


if __name__ == "__main__":
    unittest.main()
