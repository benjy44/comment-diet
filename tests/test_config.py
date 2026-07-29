"""Every config key changes behaviour, and a broken config degrades asymmetrically."""
import json

import pytest

import comment_diet as cd

BLOCK = "# why one\n# why two\nx = 1\n"


def configure(repo, data):
    repo.write(cd.CONFIG_FILE, json.dumps(data))
    return cd.load_config()


def audit(repo, source, conf, name="a.tf"):
    repo.write(name, source)
    return cd.collect([name], conf, whole_file=True)


def test_absent_config_is_defaults(repo):
    assert cd.load_config() == cd.DEFAULTS


def test_max_lines_raises_the_bar(repo):
    conf = configure(repo, {"max_lines": 3})
    assert audit(repo, BLOCK, conf)[0] == []
    assert len(audit(repo, "# a\n# b\n# c\n# d\nx = 1\n", conf)[0]) == 1


def test_max_length_tightens_the_warning(repo):
    conf = configure(repo, {"max_length": 10})
    warns = audit(repo, "# a why that is definitely longer than ten\nx = 1\n", conf)[1]
    assert "over 10 chars" in warns[0]


def test_contrastive_can_be_disabled(repo):
    source = "# point at the file, not the dir\nx = 1\n"
    assert len(audit(repo, source, cd.DEFAULTS)[0]) == 1
    assert audit(repo, source, configure(repo, {"contrastive": False}))[0] == []


def test_warn_patterns_append(repo):
    conf = configure(repo, {"warn_patterns": [{"pattern": "^TODO", "label": "unowned TODO"}]})
    assert "unowned TODO" in audit(repo, "# TODO fix this\nx = 1\n", conf)[1][0]
    assert "banner" in audit(repo, "# --------\nx = 1\n", conf)[1][0]


def test_default_warn_patterns_can_be_dropped(repo):
    conf = configure(repo, {"default_warn_patterns": False})
    assert audit(repo, "# --------\nx = 1\n", conf)[1] == []


def test_exclude_skips_matching_paths(repo):
    conf = configure(repo, {"exclude": ["**/vendor/**"]})
    assert audit(repo, BLOCK, conf, name="vendor/a.tf")[0] == []
    assert audit(repo, BLOCK, conf, name="nested/vendor/a.tf")[0] == []
    assert len(audit(repo, BLOCK, conf, name="src/a.tf")[0]) == 1


@pytest.mark.parametrize("body", [
    "{ not json",
    '["a list"]',
    '{"max_lines": "three"}',
    '{"max_lines": true}',
    '{"contrastive": 1}',
    '{"exclude": "a-string"}',
    '{"warn_patterns": [{"pattern": "("}]}',
    '{"warn_patterns": [{"nope": 1}]}',
])
def test_broken_config_raises(repo, body):
    repo.write(cd.CONFIG_FILE, body)
    with pytest.raises(cd.ConfigError):
        cd.load_config()


def test_unknown_keys_are_ignored(repo):
    assert configure(repo, {"nonsense": 1}) == cd.DEFAULTS


def test_hooks_degrade_to_defaults_on_a_broken_config(repo, hook):
    repo.write(cd.CONFIG_FILE, "{ not json")
    repo.write("a.tf", BLOCK)
    result = hook("--stop-hook", "{}")
    assert result.returncode == 0
    assert json.loads(result.stdout)["decision"] == "block"
    assert "using defaults" in result.stderr


def test_cli_exits_2_on_a_broken_config(repo, cli):
    repo.write(cd.CONFIG_FILE, "{ not json")
    repo.write("a.tf", BLOCK)
    result = cli("a.tf")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "comment-diet" in result.stderr
