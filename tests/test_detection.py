"""Whole-file detection, per language. No git involved — whole_file skips diff scoping."""
import pytest

import comment_diet as cd

BLOCKS = [
    ("tf multi-line block", "a.tf", "# why one\n# why two\nx = 1\n", 1),
    ("tf // multi-line block", "a.tf", "// why one\n// why two\nx = 1\n", 1),
    ("sh multi-line block", "a.sh", "# why one\n# why two\necho x\n", 1),
    ("yaml multi-line block", "a.yml", "# why one\n# why two\nkey: 1\n", 1),
    ("py multi-line block", "a.py", "# why one\n# why two\nx = 1\n", 1),
    ("two separate blocks", "a.tf", "# a\n# b\nx = 1\n# c\n# d\ny = 2\n", 2),
    ("one-liner is fine", "a.tf", "# a single non-obvious why\nx = 1\n", 0),
    ("blank line breaks the run", "a.tf", "# a\n\n# b\nx = 1\n", 0),
    ("code between breaks the run", "a.tf", "# a\nx = 1\n# b\ny = 2\n", 0),
]

CONTRASTIVE = [
    ("comma-not", "a.tf", "# point at the file, not the dir\nx = 1\n", 1),
    ("instead of", "a.py", "# use a set instead of a list here\nx = 1\n", 1),
    ("to avoid", "a.sh", "# quote it to avoid word splitting\necho x\n", 1),
    ("so ... never", "a.yml", "# pin it so the build never drifts\nkey: 1\n", 1),
    ("plain why survives", "a.tf", "# CT owns the source bucket.\nx = 1\n", 0),
]

NEGATIVES = [
    ("shebang above a comment", "a.sh", "#!/bin/sh\n# a single why\necho x\n"),
    ("checkov directive", "a.tf", "# checkov:skip=CKV_1: justified\n# a single why\nx = 1\n"),
    ("tflint directive", "a.tf", "# tflint-ignore: rule\n# a single why\nx = 1\n"),
    ("sh heredoc body", "a.sh", "cat <<EOF\n# not\n# a comment\nEOF\n"),
    ("tf heredoc body", "a.tf", "x = <<-EOT\n# not\n# a comment\nEOT\n"),
    ("yaml block scalar body", "a.yml", "script: |\n  # not\n  # a comment\nkey: 1\n"),
    ("python string body", "a.py", 'x = """\n# not\n# a comment\n"""\n'),
    ("python trailing comments", "a.py", "x = 1  # why one\ny = 2  # why two\n"),
]


def audit(repo, name, source, conf=cd.DEFAULTS):
    repo.write(name, source)
    return cd.collect([name], conf, whole_file=True)


@pytest.mark.parametrize("label,name,source,expected",
                         BLOCKS, ids=[c[0] for c in BLOCKS])
def test_multi_line_blocks(repo, label, name, source, expected):
    viols, _ = audit(repo, name, source)
    assert len(viols) == expected, viols


@pytest.mark.parametrize("label,name,source,expected",
                         CONTRASTIVE, ids=[c[0] for c in CONTRASTIVE])
def test_road_not_taken(repo, label, name, source, expected):
    viols, _ = audit(repo, name, source)
    assert len(viols) == expected, viols


@pytest.mark.parametrize("label,name,source", NEGATIVES, ids=[c[0] for c in NEGATIVES])
def test_stays_silent(repo, label, name, source):
    viols, warns = audit(repo, name, source)
    assert (viols, warns) == ([], [])


def test_unsupported_extension_ignored(repo):
    assert audit(repo, "a.rb", "# a\n# b\nx = 1\n") == ([], [])


@pytest.mark.parametrize("source,label", [
    ("# ----------------\nx = 1\n", "banner/decoration"),
    ("# creates the bucket\nx = 1\n", "narrates what the code does"),
    ("# Set up the role\nx = 1\n", "narrates what the code does"),
])
def test_warnings_do_not_block(repo, source, label):
    viols, warns = audit(repo, "a.tf", source)
    assert viols == []
    assert len(warns) == 1 and label in warns[0]


def test_over_long_one_liner_warns(repo):
    viols, warns = audit(repo, "a.tf", f"# {'x' * 200}\nx = 1\n")
    assert viols == []
    assert "over 120 chars" in warns[0]
