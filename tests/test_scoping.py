import os
import tempfile
import unittest
from unittest import mock

from tests.loader import cd

LEGACY = ("// Client talks to the vendor API.\n"
          "//\n"
          "// It handles retries, backoff and connection reuse.\n"
          "type Client struct{}\n")


def _write(tmp, name, text):
    path = os.path.join(tmp, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class ParseAdded(unittest.TestCase):
    def test_single_added_line(self):
        diff = "@@ -0,0 +3 @@\n+new line\n"
        self.assertEqual(cd.parse_added(diff), {3})

    def test_multiple_hunks(self):
        diff = "@@ -1,0 +2,2 @@\n+a\n+b\n@@ -9,0 +20 @@\n+c\n"
        self.assertEqual(cd.parse_added(diff), {2, 3, 20})

    def test_removed_lines_do_not_advance_the_counter(self):
        diff = "@@ -1,2 +1,1 @@\n-gone\n+kept\n"
        self.assertEqual(cd.parse_added(diff), {1})

    def test_file_header_is_not_an_added_line(self):
        diff = "+++ b/x.go\n@@ -0,0 +1 @@\n+a\n"
        self.assertEqual(cd.parse_added(diff), {1})


class DiffScoping(unittest.TestCase):
    def test_untouched_block_does_not_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.go", LEGACY)
            with mock.patch.object(cd, "added_linenos", return_value={4}):
                self.assertEqual(cd.check_file(path, cd.lang_for(path), cd.DEFAULTS), [])

    def test_touching_one_line_trips_the_whole_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.go", LEGACY)
            with mock.patch.object(cd, "added_linenos", return_value={3}):
                findings = cd.check_file(path, cd.lang_for(path), cd.DEFAULTS)
        self.assertTrue(any("second paragraph" in f.message for f in findings))

    def test_no_diff_audits_the_whole_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.go", LEGACY)
            with mock.patch.object(cd, "added_linenos", return_value=None):
                findings = cd.check_file(path, cd.lang_for(path), cd.DEFAULTS)
        self.assertTrue(findings)

    def test_whole_file_mode_ignores_the_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.go", LEGACY)
            with mock.patch.object(cd, "added_linenos", return_value={99}):
                findings = cd.check_file(path, cd.lang_for(path), cd.DEFAULTS, whole_file=True)
        self.assertTrue(findings)


class Collect(unittest.TestCase):
    def test_unreadable_file_raises_for_the_cli(self):
        with self.assertRaises(cd.ReadError):
            cd.collect(["/nope/missing.go"], cd.DEFAULTS, whole_file=True)

    def test_unreadable_file_is_skipped_for_hooks(self):
        viols, warns = cd.collect(["/nope/missing.go"], cd.DEFAULTS,
                                  whole_file=True, skip_unreadable=True)
        self.assertEqual((viols, warns), ([], []))

    def test_unsupported_file_is_skipped(self):
        viols, _ = cd.collect(["a.rb"], cd.DEFAULTS, whole_file=True)
        self.assertEqual(viols, [])

    def test_span_is_rendered_for_multi_line_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "a.go", LEGACY)
            viols, _ = cd.collect([path], cd.DEFAULTS, whole_file=True)
        self.assertTrue(any(":1-3:" in v for v in viols))


class ChangedFiles(unittest.TestCase):
    def test_untracked_files_are_included_and_missing_ones_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            here = os.getcwd()
            os.chdir(tmp)
            try:
                _write(tmp, "new.go", "package main\n")
                outputs = {("diff", "--name-only", "HEAD"): "deleted.go\n",
                           ("ls-files", "--others", "--exclude-standard"): "new.go\n"}
                with mock.patch.object(cd, "_git", side_effect=lambda *a: outputs.get(a, "")):
                    self.assertEqual(cd.changed_files(), ["new.go"])
            finally:
                os.chdir(here)


if __name__ == "__main__":
    unittest.main()
