import unittest

from tests.loader import blocked, warned

LONG = ("Client talks to the vendor billing API, retrying on 500 responses because "
        "the vendor documents batches of two hundred items but in practice fails "
        "on anything above fifty items per request, which we discovered the hard way.")


class OrdinaryComments(unittest.TestCase):
    def test_single_line_comment_passes(self):
        self.assertEqual(blocked("// the vendor 500s over 50\nlet x = 1;\n", ".rs"), [])

    def test_two_line_block_is_blocked(self):
        source = "// the vendor 500s over 50\n// so batches are capped\nlet x = 1;\n"
        self.assertIn("longer than 1 line", blocked(source, ".rs")[0])

    def test_double_slash_above_a_declaration_is_not_a_doc_comment(self):
        source = ("// Client talks to the vendor API and caps batches at fifty,\n"
                  "// which is the largest size the vendor accepts.\n"
                  "pub struct Client;\n")
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".rs")))

    def test_quadruple_slash_is_an_ordinary_comment(self):
        source = ("//// Talks to the vendor API and caps batches at fifty,\n"
                  "//// which is the largest size the vendor accepts.\n"
                  "pub struct Client;\n")
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".rs")))

    def test_plain_block_comment_gets_the_ordinary_rule(self):
        source = "/* one reason\n   two reasons */\nlet x = 1;\n"
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".rs")))

    def test_safety_comment_is_not_a_section_header(self):
        source = "// SAFETY: ptr comes from Box::into_raw and is never aliased.\nunsafe { }\n"
        self.assertEqual(blocked(source, ".rs"), [])


class DocComments(unittest.TestCase):
    def test_one_line_doc_comment_passes(self):
        self.assertEqual(blocked("/// Talks to the vendor API.\npub struct Client;\n", ".rs"), [])

    def test_doc_comment_survives_where_ordinary_two_liner_would_not(self):
        source = ("/// Talks to the vendor API and caps batches at fifty,\n"
                  "/// which is the largest size the vendor actually accepts.\n"
                  "pub struct Client;\n")
        self.assertEqual(blocked(source, ".rs"), [])

    def test_inner_doc_comment_is_a_doc_comment(self):
        source = f"//! {LONG}\n"
        self.assertTrue(any("budget 200" in m for m in blocked(source, ".rs")))

    def test_over_budget_doc_comment_is_blocked(self):
        source = f"/// {LONG}\npub struct Client;\n"
        self.assertTrue(any("budget 200" in m for m in blocked(source, ".rs")))

    def test_second_paragraph_is_blocked(self):
        source = ("/// Talks to the vendor API.\n"
                  "///\n"
                  "/// It handles retries and backoff.\n"
                  "pub struct Client;\n")
        self.assertIn("second paragraph", blocked(source, ".rs")[0])

    def test_markdown_section_header_that_restates_the_signature_is_blocked(self):
        source = ("/// Parses the config.\n"
                  "/// # Arguments\n"
                  "pub fn parse() {}\n")
        self.assertTrue(any("section header" in m for m in blocked(source, ".rs")))

    def test_list_in_doc_comment_is_blocked(self):
        source = ("/// Talks to the vendor API.\n"
                  "/// - retries on 500\n"
                  "pub struct Client;\n")
        self.assertTrue(any("list" in m for m in blocked(source, ".rs")))

    def test_filler_opener_is_blocked(self):
        source = "/// This function parses the config.\npub fn parse() {}\n"
        self.assertTrue(any("filler" in m for m in blocked(source, ".rs")))

    def test_block_doc_comment_is_a_doc_comment(self):
        source = ("/**\n"
                  f" * {LONG}\n"
                  " */\n"
                  "pub struct Client;\n")
        self.assertTrue(any("budget 200" in m for m in blocked(source, ".rs")))

    def test_inner_block_doc_comment_is_a_doc_comment(self):
        source = f"/*!\n * {LONG}\n */\n"
        self.assertTrue(any("budget 200" in m for m in blocked(source, ".rs")))

    def test_doc_run_does_not_merge_with_the_ordinary_comment_below_it(self):
        source = ("/// Talks to the vendor API.\n"
                  "// the vendor 500s over 50\n"
                  "// so batches are capped\n"
                  "pub struct Client;\n")
        messages = blocked(source, ".rs")
        self.assertEqual(len(messages), 1)
        self.assertIn("longer than 1 line", messages[0])


class Doctests(unittest.TestCase):
    """A doctest is executable code, and code stays outside the prose budget."""

    def test_examples_section_with_a_doctest_passes(self):
        source = ("/// Reads path and applies defaults; a missing file is not an error.\n"
                  "///\n"
                  "/// # Examples\n"
                  "///\n"
                  "/// ```\n"
                  "/// let cfg = parse_config(Path::new(\"app.toml\"))?;\n"
                  "/// # Ok::<(), io::Error>(())\n"
                  "/// ```\n"
                  "pub fn parse_config(path: &Path) -> io::Result<Config> {}\n")
        self.assertEqual((blocked(source, ".rs"), warned(source, ".rs")), ([], []))

    def test_fence_attributes_are_recognised(self):
        for info in ("rust", "no_run", "rust,ignore", "should_panic"):
            source = ("/// Reads the config.\n"
                      "///\n"
                      "/// # Examples\n"
                      "///\n"
                      f"/// ```{info}\n"
                      "/// let cfg = parse_config(Path::new(\"app.toml\"));\n"
                      "/// ```\n"
                      "pub fn parse_config(path: &Path) {}\n")
            self.assertEqual(blocked(source, ".rs"), [], info)

    def test_long_doctest_does_not_spend_the_budget(self):
        body = "\n".join(f"/// let x{i} = compute({i});" for i in range(40))
        source = ("/// Reads the config.\n"
                  "///\n"
                  "/// # Examples\n"
                  "///\n"
                  "/// ```\n"
                  f"{body}\n"
                  "/// ```\n"
                  "pub fn parse_config(path: &Path) {}\n")
        self.assertEqual(blocked(source, ".rs"), [])

    def test_doctest_code_never_trips_the_prose_rules(self):
        source = ("/// Reads the config.\n"
                  "///\n"
                  "/// # Examples\n"
                  "///\n"
                  "/// ```\n"
                  "/// // use the pool instead of a fresh connection\n"
                  "/// - not a list, this is code\n"
                  "/// # fn main() -> io::Result<()> {\n"
                  "/// let cfg = parse_config(Path::new(\"app.toml\"))?;\n"
                  "/// # Ok(()) }\n"
                  "/// ```\n"
                  "pub fn parse_config(path: &Path) -> io::Result<Config> {}\n")
        self.assertEqual(blocked(source, ".rs"), [])

    def test_doctest_straight_after_the_summary_passes(self):
        source = ("/// Reads path and applies defaults.\n"
                  "///\n"
                  "/// ```\n"
                  "/// let cfg = parse_config(Path::new(\"app.toml\"));\n"
                  "/// ```\n"
                  "pub fn parse_config(path: &Path) {}\n")
        self.assertEqual(blocked(source, ".rs"), [])

    def test_prose_padding_in_an_examples_section_is_still_capped(self):
        source = ("/// Reads the config.\n"
                  "///\n"
                  "/// # Examples\n"
                  "///\n"
                  f"/// {LONG}\n"
                  "/// ```\n"
                  "/// let cfg = parse_config(Path::new(\"app.toml\"));\n"
                  "/// ```\n"
                  "pub fn parse_config(path: &Path) {}\n")
        self.assertTrue(any("budget 200" in m for m in blocked(source, ".rs")))

    def test_fenced_code_is_skipped_in_jsdoc_too(self):
        source = ("/**\n"
                  " * Talks to the vendor API.\n"
                  " * ```\n"
                  " * - not a list, this is code\n"
                  " * ```\n"
                  " */\n"
                  "export class Client {}\n")
        self.assertEqual(blocked(source, ".ts"), [])


class RawStrings(unittest.TestCase):
    def test_hashed_raw_string_is_skipped(self):
        source = 'let q = r#"\n// not a comment\n// nor this\n"#;\n'
        self.assertEqual(blocked(source, ".rs"), [])

    def test_plain_raw_string_is_skipped(self):
        source = 'let q = r"\n// not a comment\n// nor this\n";\n'
        self.assertEqual(blocked(source, ".rs"), [])

    def test_closed_raw_string_does_not_swallow_the_file(self):
        source = ('let q = r#"select 1"#;\n'
                  "// one reason\n"
                  "// two reasons\n")
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".rs")))

    def test_backtick_in_a_string_does_not_desync(self):
        source = ('let t = "`";\n'
                  "// one reason\n"
                  "// two reasons\n")
        self.assertTrue(any("longer than 1 line" in m for m in blocked(source, ".rs")))


class ContractSections(unittest.TestCase):
    """`# Safety`/`# Errors`/`# Panics` carry what no signature does, so they stay."""

    def test_clippy_missing_safety_doc_example_passes(self):
        source = ("/// Frees ptr.\n"
                  "///\n"
                  "/// # Safety\n"
                  "///\n"
                  "/// ptr must come from Box::into_raw and must not be aliased.\n"
                  "pub unsafe fn free(ptr: *mut u8) {}\n")
        self.assertEqual(blocked(source, ".rs"), [])
        self.assertEqual(warned(source, ".rs"), [])

    def test_guideline_errors_example_passes(self):
        source = ("/// # Errors\n"
                  "///\n"
                  "/// Will return `Err` if `filename` does not exist or the user lacks\n"
                  "/// permission to read it.\n"
                  "pub fn read(filename: String) -> io::Result<String> {}\n")
        self.assertEqual(blocked(source, ".rs"), [])

    def test_guideline_panics_example_passes(self):
        source = ("/// # Panics\n"
                  "///\n"
                  "/// Will panic if y is 0\n"
                  "pub fn divide_by(x: i32, y: i32) -> i32 {}\n")
        self.assertEqual(blocked(source, ".rs"), [])

    def test_summary_plus_two_sections_passes(self):
        source = ("/// Reads the config at path.\n"
                  "///\n"
                  "/// # Errors\n"
                  "///\n"
                  "/// Returns `Err` when path is unreadable.\n"
                  "///\n"
                  "/// # Panics\n"
                  "///\n"
                  "/// Panics if the defaults table is empty.\n"
                  "pub fn parse(path: &Path) -> io::Result<Config> {}\n")
        self.assertEqual(blocked(source, ".rs"), [])

    def test_section_prose_has_its_own_budget(self):
        source = ("/// Frees ptr.\n"
                  "///\n"
                  "/// # Safety\n"
                  "///\n"
                  f"/// {LONG}\n"
                  "pub unsafe fn free(ptr: *mut u8) {}\n")
        self.assertTrue(any("`# Safety` section is" in m and "budget 200" in m
                            for m in blocked(source, ".rs")))

    def test_second_paragraph_inside_a_section_is_blocked(self):
        source = ("/// Frees ptr.\n"
                  "///\n"
                  "/// # Safety\n"
                  "///\n"
                  "/// ptr must come from Box::into_raw.\n"
                  "///\n"
                  "/// It must also outlive the call.\n"
                  "pub unsafe fn free(ptr: *mut u8) {}\n")
        self.assertTrue(any("second paragraph" in m for m in blocked(source, ".rs")))

    def test_list_inside_a_section_is_blocked(self):
        source = ("/// # Errors\n"
                  "///\n"
                  "/// - `NotFound` when path is missing\n"
                  "/// - `PermissionDenied` otherwise\n"
                  "pub fn read(path: &Path) -> io::Result<String> {}\n")
        self.assertTrue(any("list" in m for m in blocked(source, ".rs")))

    def test_summary_paragraph_break_is_still_blocked(self):
        source = ("/// Reads the config.\n"
                  "///\n"
                  "/// It handles retries and backoff.\n"
                  "///\n"
                  "/// # Errors\n"
                  "///\n"
                  "/// Returns `Err` when path is unreadable.\n"
                  "pub fn parse(path: &Path) -> io::Result<Config> {}\n")
        self.assertTrue(any("doc comment runs to a second paragraph" in m
                            for m in blocked(source, ".rs")))

    def test_arguments_and_returns_sections_stay_blocked(self):
        for header in ("# Arguments", "# Returns"):
            source = ("/// Reads the config.\n"
                      "///\n"
                      f"/// {header}\n"
                      "///\n"
                      "/// path: where the config lives.\n"
                      "pub fn parse(path: &Path) -> io::Result<Config> {}\n")
            self.assertTrue(any("section header" in m for m in blocked(source, ".rs")),
                            header)

    def test_safety_section_on_a_safe_fn_warns(self):
        source = ("/// Reads the config.\n"
                  "///\n"
                  "/// # Safety\n"
                  "///\n"
                  "/// Nothing to uphold.\n"
                  "pub fn parse(path: &Path) -> io::Result<Config> {}\n")
        self.assertEqual(blocked(source, ".rs"), [])
        self.assertTrue(any("unnecessary_safety_doc" in m for m in warned(source, ".rs")))

    def test_safety_section_survives_attributes_above_an_unsafe_fn(self):
        source = ("/// Frees ptr.\n"
                  "///\n"
                  "/// # Safety\n"
                  "///\n"
                  "/// ptr must come from Box::into_raw.\n"
                  "#[inline]\n"
                  "pub unsafe fn free(ptr: *mut u8) {}\n")
        self.assertEqual(warned(source, ".rs"), [])

    def test_module_level_safety_section_does_not_warn(self):
        source = ("//! Raw FFI bindings.\n"
                  "//!\n"
                  "//! # Safety\n"
                  "//!\n"
                  "//! Every call assumes the vendor library is initialised.\n"
                  "\n"
                  "use std::ffi::c_void;\n")
        self.assertEqual((blocked(source, ".rs"), warned(source, ".rs")), ([], []))

    def test_carve_out_is_rust_only(self):
        source = ("// Client talks to the vendor API.\n"
                  "//\n"
                  "// # Errors\n"
                  "//\n"
                  "// Returns an error when the vendor is down.\n"
                  "type Client struct{}\n")
        self.assertTrue(any("second paragraph" in m for m in blocked(source, ".go")))


if __name__ == "__main__":
    unittest.main()
