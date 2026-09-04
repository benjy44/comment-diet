import io
import json
import unittest
from contextlib import redirect_stderr
from unittest import mock

from tests.loader import blocked, cd


class ParseConfig(unittest.TestCase):
    def test_defaults_when_empty(self):
        conf = cd.parse_config({})
        self.assertEqual(conf.max_lines, 1)
        self.assertEqual(conf.max_doc_chars, 200)
        self.assertEqual(conf.warn_doc_chars, 120)
        self.assertTrue(conf.docstrings)

    def test_overrides_are_applied(self):
        conf = cd.parse_config({"max_lines": 3, "max_doc_chars": 400, "exclude": ["v/**"]})
        self.assertEqual(conf.max_lines, 3)
        self.assertEqual(conf.max_doc_chars, 400)
        self.assertEqual(conf.exclude, ("v/**",))

    def test_top_level_must_be_an_object(self):
        with self.assertRaises(cd.ConfigError):
            cd.parse_config([])

    def test_wrong_type_is_rejected(self):
        with self.assertRaises(cd.ConfigError):
            cd.parse_config({"max_lines": "three"})

    def test_bool_is_not_an_int(self):
        with self.assertRaises(cd.ConfigError):
            cd.parse_config({"max_lines": True})

    def test_bad_warn_pattern_regex_is_rejected(self):
        with self.assertRaises(cd.ConfigError):
            cd.parse_config({"warn_patterns": [{"pattern": "[", "label": "x"}]})

    def test_warn_pattern_needs_both_keys(self):
        with self.assertRaises(cd.ConfigError):
            cd.parse_config({"warn_patterns": [{"pattern": "x"}]})

    def test_built_in_warn_patterns_can_be_switched_off(self):
        conf = cd.parse_config({"default_warn_patterns": False})
        self.assertEqual(conf.warn_patterns, ())

    def test_unknown_keys_are_ignored(self):
        self.assertEqual(cd.parse_config({"nonsense": 1}).max_lines, 1)


class HookDegradation(unittest.TestCase):
    def test_broken_config_falls_back_to_defaults_with_a_warning(self):
        err = io.StringIO()
        with mock.patch.object(cd, "load_config", side_effect=cd.ConfigError("bad")), \
             redirect_stderr(err):
            conf = cd.hook_config()
        self.assertIs(conf, cd.DEFAULTS)
        self.assertIn("using defaults", err.getvalue())


class BudgetIsConfigurable(unittest.TestCase):
    def test_raised_doc_budget_lets_a_longer_summary_through(self):
        body = ("Client talks to the vendor billing API, retrying on 500 because the "
                "vendor documents batches of two hundred items but in practice fails "
                "on anything above fifty per request, as we found out the hard way.")
        source = f"// {body}\ntype Client struct{{}}\n"
        self.assertTrue(any("budget 200" in m for m in blocked(source, ".go")))
        conf = cd.replace(cd.DEFAULTS, max_doc_chars=400, warn_doc_chars=400)
        self.assertEqual(blocked(source, ".go", conf), [])


class Excludes(unittest.TestCase):
    def test_glob_matches(self):
        self.assertTrue(cd.excluded("tests/x.py", ("tests/**",)))

    def test_leading_globstar_also_matches_at_top_level(self):
        self.assertTrue(cd.excluded("vendor/x.go", ("**/vendor/**",)))

    def test_non_match(self):
        self.assertFalse(cd.excluded("src/x.go", ("tests/**",)))

    def test_excluded_file_is_skipped_by_collect(self):
        conf = cd.replace(cd.DEFAULTS, exclude=("skipme/**",))
        viols, _ = cd.collect(["skipme/a.py"], conf, whole_file=True)
        self.assertEqual(viols, [])


class LangDispatch(unittest.TestCase):
    def test_every_supported_suffix_resolves(self):
        for ext in cd.SUFFIXES:
            self.assertIsNotNone(cd.lang_for("sample" + ext), ext)

    def test_tsx_does_not_resolve_as_ts(self):
        self.assertEqual(cd.lang_for("a.tsx")["doc"], "jsdoc")

    def test_mjs_is_untyped(self):
        self.assertFalse(cd.lang_for("a.mjs")["typed"])
        self.assertTrue(cd.lang_for("a.ts")["typed"])

    def test_unsupported_suffix_is_none(self):
        self.assertIsNone(cd.lang_for("a.rb"))


class ConfigFileLoading(unittest.TestCase):
    def test_missing_file_gives_defaults(self):
        with mock.patch.object(cd, "config_path", return_value="/nope/.comment-diet.json"):
            self.assertIs(cd.load_config(), cd.DEFAULTS)

    def test_malformed_json_raises(self):
        with mock.patch.object(cd, "config_path", return_value="cfg.json"), \
             mock.patch.object(cd.os.path, "exists", return_value=True), \
             mock.patch("builtins.open", mock.mock_open(read_data="{not json")), \
             self.assertRaises(cd.ConfigError):
            cd.load_config()

    def test_valid_file_is_parsed(self):
        data = json.dumps({"max_lines": 2})
        with mock.patch.object(cd, "config_path", return_value="cfg.json"), \
             mock.patch.object(cd.os.path, "exists", return_value=True), \
             mock.patch("builtins.open", mock.mock_open(read_data=data)):
            self.assertEqual(cd.load_config().max_lines, 2)


if __name__ == "__main__":
    unittest.main()
