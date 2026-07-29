"""Diff scoping — only comments the current change touched count."""
import comment_diet as cd

BLOCK = "# why one\n# why two\n"


def test_pre_existing_comment_does_not_trip(repo):
    repo.write("a.tf", BLOCK + "x = 1\n")
    repo.commit()
    repo.write("a.tf", BLOCK + "x = 1\ny = 2\n")
    assert cd.collect(["a.tf"], cd.DEFAULTS)[0] == []


def test_editing_the_comment_trips(repo):
    repo.write("a.tf", BLOCK + "x = 1\n")
    repo.commit()
    repo.write("a.tf", "# why one\n# why two, edited\nx = 1\n")
    assert len(cd.collect(["a.tf"], cd.DEFAULTS)[0]) == 1


def test_untracked_file_is_audited_whole(repo):
    repo.write("a.tf", BLOCK + "x = 1\n")
    assert len(cd.collect(["a.tf"], cd.DEFAULTS)[0]) == 1


def test_missing_file_is_a_no_op(repo):
    assert cd.collect(["gone.tf"], cd.DEFAULTS) == ([], [])


def test_changed_files_includes_untracked_and_drops_deleted(repo):
    repo.write("kept.tf", "x = 1\n")
    repo.write("deleted.tf", "x = 1\n")
    repo.commit()
    (repo.path / "deleted.tf").unlink()
    repo.write("new.py", "x = 1\n")
    repo.write("ignored.rb", "x = 1\n")
    assert cd.changed_files() == ["new.py"]


PATCH = """\
diff --git a/a.tf b/a.tf
--- a/a.tf
+++ b/a.tf
@@ -1,0 +2 @@
+# added at line 2
@@ -9 +10 @@
-# gone
+# replaced at line 10
"""


def test_parse_added():
    assert cd.parse_added(PATCH) == {2, 10}


def test_parse_added_empty_diff():
    assert cd.parse_added("") == set()
