import unittest

from tests.loader import blocked, warned

LONG = ("Client talks to the vendor billing API, retrying on 500 responses because "
        "the vendor documents batches of two hundred items but in practice fails "
        "on anything above fifty items per request, which we discovered the hard way.")


class GoDocComments(unittest.TestCase):
    def test_one_line_doc_comment_passes(self):
        source = "// Client talks to the vendor API.\ntype Client struct{}\n"
        self.assertEqual(blocked(source, ".go"), [])

    def test_doc_comment_survives_where_ordinary_two_liner_would_not(self):
        source = ("// Client talks to the vendor API and caps batches at fifty,\n"
                  "// which is the largest size the vendor actually accepts.\n"
                  "type Client struct{}\n")
        self.assertEqual(blocked(source, ".go"), [])

    def test_second_paragraph_is_blocked(self):
        source = ("// Client talks to the vendor API.\n"
                  "//\n"
                  "// It handles retries and backoff.\n"
                  "type Client struct{}\n")
        self.assertIn("second paragraph", blocked(source, ".go")[0])

    def test_over_budget_doc_comment_is_blocked(self):
        source = f"// {LONG}\ntype Client struct{{}}\n"
        self.assertTrue(any("budget 200" in m for m in blocked(source, ".go")))

    def test_wordy_doc_comment_warns_before_it_blocks(self):
        body = "Client talks to the vendor billing API and caps outbound batches at fifty items."
        source = (f"// {body}\n// The vendor documents two hundred but fails above fifty.\n"
                  "type Client struct{}\n")
        self.assertEqual(blocked(source, ".go"), [])
        self.assertTrue(any("getting wordy" in m for m in warned(source, ".go")))

    def test_list_in_doc_comment_is_blocked(self):
        source = ("// Client talks to the vendor API.\n"
                  "//   - retries on 500\n"
                  "type Client struct{}\n")
        self.assertTrue(any("list" in m for m in blocked(source, ".go")))

    def test_section_header_is_blocked(self):
        source = ("// Parse reads the config.\n"
                  "// Returns: the parsed config.\n"
                  "func Parse() {}\n")
        self.assertTrue(any("section header" in m for m in blocked(source, ".go")))

    def test_this_function_preamble_is_blocked(self):
        source = "// This function parses the config.\nfunc Parse() {}\n"
        self.assertTrue(any("filler" in m for m in blocked(source, ".go")))

    def test_signature_restatement_warns(self):
        source = "// Parse takes a path and returns a Config.\nfunc Parse() {}\n"
        self.assertTrue(any("restates the signature" in m for m in warned(source, ".go")))

    def test_indented_comment_is_not_a_doc_comment(self):
        source = ("type Client struct {\n"
                  "\t// Endpoint is the vendor base URL and it is\n"
                  "\t// resolved once at construction time.\n"
                  "\tEndpoint string\n"
                  "}\n")
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".go")))

    def test_blank_line_before_declaration_is_not_a_doc_comment(self):
        source = ("// Client talks to the vendor API and caps batches at fifty,\n"
                  "// which is the largest size the vendor actually accepts.\n"
                  "\n"
                  "type Client struct{}\n")
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".go")))

    def test_package_doc_is_a_doc_comment(self):
        source = "// Package billing talks to the vendor API.\npackage billing\n"
        self.assertEqual(blocked(source, ".go"), [])


class FileHeaders(unittest.TestCase):
    def test_licence_header_is_free(self):
        source = ("// Copyright 2026 Example Ltd.\n"
                  "// SPDX-License-Identifier: MIT\n"
                  "\n"
                  "package main\n")
        self.assertEqual(blocked(source, ".go"), [])

    def test_apache_boilerplate_is_free(self):
        source = ("// Copyright 2026 Example Ltd.\n"
                  "//\n"
                  "// Licensed under the Apache License, Version 2.0 (the \"License\");\n"
                  "// you may not use this file except in compliance with the License.\n"
                  "// You may obtain a copy of the License at the address below.\n"
                  "\n"
                  "package main\n")
        self.assertEqual(blocked(source, ".go"), [])

    def test_prose_beside_a_licence_line_is_not_free(self):
        source = ("// Copyright 2026 Example Ltd.\n"
                  "// This file contains the HTTP handlers for the billing service.\n"
                  "\n"
                  "package main\n")
        self.assertTrue(any("filler" in m for m in blocked(source, ".go")))


class JsDoc(unittest.TestCase):
    def test_one_line_jsdoc_passes(self):
        source = "/** Talks to the vendor API. */\nexport class Client {}\n"
        self.assertEqual(blocked(source, ".ts"), [])

    def test_multi_line_jsdoc_within_budget_passes(self):
        source = ("/**\n"
                  " * Talks to the vendor API and caps batches at fifty items.\n"
                  " */\n"
                  "export class Client {}\n")
        self.assertEqual(blocked(source, ".ts"), [])

    def test_jsdoc_second_paragraph_is_blocked(self):
        source = ("/**\n"
                  " * Talks to the vendor API.\n"
                  " *\n"
                  " * Handles retries and backoff.\n"
                  " */\n"
                  "export class Client {}\n")
        self.assertIn("second paragraph", blocked(source, ".ts")[0])

    def test_param_tag_blocked_in_typescript(self):
        source = ("/**\n"
                  " * Parses the config.\n"
                  " * @param path the config path\n"
                  " */\n"
                  "export function parse(path: string) {}\n")
        self.assertTrue(any("typed signature" in m for m in blocked(source, ".ts")))

    def test_param_tag_allowed_in_javascript(self):
        source = ("/**\n"
                  " * Parses the config.\n"
                  " * @param path the config path\n"
                  " */\n"
                  "export function parse(path) {}\n")
        self.assertEqual(blocked(source, ".js"), [])

    def test_jsdoc_bullet_is_blocked(self):
        source = ("/**\n"
                  " * Talks to the vendor API.\n"
                  " * - retries on 500\n"
                  " */\n"
                  "export class Client {}\n")
        self.assertTrue(any("list" in m for m in blocked(source, ".ts")))

    def test_plain_block_comment_gets_the_ordinary_rule(self):
        source = "/* one reason\n   two reasons */\nexport const x = 1;\n"
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".ts")))

    def test_double_slash_above_export_is_not_a_doc_comment(self):
        source = ("// Talks to the vendor API and caps batches at fifty,\n"
                  "// which is the largest size the vendor accepts.\n"
                  "export class Client {}\n")
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".ts")))


class PythonDocstrings(unittest.TestCase):
    def test_one_line_docstring_passes(self):
        source = 'def parse(path):\n    """Read the config at path."""\n    return 1\n'
        self.assertEqual(blocked(source, ".py"), [])

    def test_google_style_sections_are_blocked(self):
        source = ('def parse(path):\n'
                  '    """Read the config.\n'
                  '\n'
                  '    Args:\n'
                  '        path: the config path.\n'
                  '    """\n'
                  '    return 1\n')
        messages = blocked(source, ".py")
        self.assertTrue(any("second paragraph" in m for m in messages))
        self.assertTrue(any("section header" in m for m in messages))

    def test_over_budget_docstring_is_blocked(self):
        source = f'def parse(path):\n    """{LONG}"""\n    return 1\n'
        self.assertTrue(any("budget 200" in m for m in blocked(source, ".py")))

    def test_numpy_underline_is_blocked(self):
        source = ('def parse(path):\n'
                  '    """Read the config.\n'
                  '    Parameters\n'
                  '    ----------\n'
                  '    path : str\n'
                  '    """\n'
                  '    return 1\n')
        self.assertTrue(any("underline" in m for m in blocked(source, ".py")))

    def test_module_and_class_docstrings_are_checked(self):
        source = f'"""{LONG}"""\n\n\nclass A:\n    """{LONG}"""\n'
        self.assertEqual(len([m for m in blocked(source, ".py") if "budget 200" in m]), 2)

    def test_docstrings_can_be_disabled(self):
        from tests.loader import cd
        conf = cd.replace(cd.DEFAULTS, docstrings=False)
        source = f'def parse(path):\n    """{LONG}"""\n    return 1\n'
        self.assertEqual(blocked(source, ".py", conf), [])

    def test_unparseable_python_still_checks_hash_comments(self):
        source = "# one reason\n# two reasons\ndef broken(\n"
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".py")))


if __name__ == "__main__":
    unittest.main()
