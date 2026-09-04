import unittest

from tests.loader import blocked, warned


class OneLineRule(unittest.TestCase):
    def test_single_line_comment_passes(self):
        self.assertEqual(blocked("# the vendor 500s over 50\nx = 1\n", ".py"), [])

    def test_two_line_block_is_blocked(self):
        source = "# the vendor 500s over 50\n# so batches are capped\nx = 1\n"
        self.assertIn("longer than 1 line", blocked(source, ".py")[0])

    def test_blank_line_separates_two_allowed_comments(self):
        source = "# first reason\n\n# second reason\nx = 1\n"
        self.assertEqual(blocked(source, ".py"), [])

    def test_terraform_accepts_both_prefixes(self):
        source = '// one\n// two\nresource "aws_s3_bucket" "x" {}\n'
        self.assertIn("longer than 1 line", blocked(source, ".tf")[0])

    def test_go_comment_inside_function_gets_one_line(self):
        source = "func f() {\n\t// one\n\t// two\n}\n"
        self.assertIn("longer than 1 line", blocked(source, ".go")[0])


class Directives(unittest.TestCase):
    def test_shebang_is_not_a_comment(self):
        self.assertEqual(blocked("#!/usr/bin/env bash\necho hi\n", ".sh"), [])

    def test_checkov_skip_is_not_counted(self):
        source = 'resource "x" "y" {\n  # checkov:skip=CKV_1\n  # checkov:skip=CKV_2\n}\n'
        self.assertEqual(blocked(source, ".tf"), [])

    def test_go_build_directive_is_not_counted(self):
        source = "//go:build linux\n//go:generate stringer -type=X\n\npackage main\n"
        self.assertEqual(blocked(source, ".go"), [])

    def test_eslint_disable_is_not_counted(self):
        source = "// eslint-disable-next-line no-console\n// @ts-expect-error\nfoo();\n"
        self.assertEqual(blocked(source, ".ts"), [])

    def test_directive_breaks_a_run(self):
        source = "// one reason\n//go:generate stringer\n// another reason\nvar x int\n"
        self.assertEqual([m for m in blocked(source, ".go") if "longer than" in m], [])


class StringBodies(unittest.TestCase):
    def test_heredoc_hash_lines_are_skipped(self):
        source = 'x = <<EOT\n# not a comment\n# nor this\nEOT\n'
        self.assertEqual(blocked(source, ".tf"), [])

    def test_yaml_block_scalar_is_skipped(self):
        source = "script: |\n  # not a comment\n  # nor this\nnext: 1\n"
        self.assertEqual(blocked(source, ".yml"), [])

    def test_python_hash_inside_string_is_skipped(self):
        source = 's = """\n# not a comment\n# nor this\n"""\n'
        self.assertEqual([m for m in blocked(source, ".py") if "longer than" in m], [])

    def test_go_raw_string_is_skipped(self):
        source = "func f() {\n\ts := `\n// not a comment\n// nor this\n`\n}\n"
        self.assertEqual(blocked(source, ".go"), [])

    def test_template_literal_is_skipped(self):
        source = "const s = `\n// not a comment\n// nor this\n`;\n"
        self.assertEqual(blocked(source, ".ts"), [])


class Contrastive(unittest.TestCase):
    def test_road_not_taken_is_blocked(self):
        source = "# point at the file, not the dir\nx = 1\n"
        self.assertIn("road not taken", blocked(source, ".py")[0])

    def test_instead_of_is_blocked(self):
        source = "# use the pool instead of a fresh connection\nx = 1\n"
        self.assertIn("road not taken", blocked(source, ".py")[0])

    def test_contrastive_can_be_disabled(self):
        from tests.loader import cd
        conf = cd.replace(cd.DEFAULTS, contrastive=False)
        source = "# point at the file, not the dir\nx = 1\n"
        self.assertEqual(blocked(source, ".py", conf), [])


class Warnings(unittest.TestCase):
    def test_banner_warns(self):
        self.assertIn("banner", warned("# ---------- helpers\nx = 1\n", ".py")[0])

    def test_narration_warns(self):
        source = "# creates the bucket\nx = 1\n"
        self.assertIn("narrates", warned(source, ".py")[0])

    def test_over_long_one_liner_warns(self):
        source = "# " + ("z" * 130) + "\nx = 1\n"
        self.assertTrue(any("over 120 chars" in m for m in warned(source, ".py")))

    def test_warnings_do_not_block(self):
        self.assertEqual(blocked("# ---------- helpers\nx = 1\n", ".py"), [])


if __name__ == "__main__":
    unittest.main()
