"""Hook and CLI wiring: stdin payload in, block decision out, always exit 0."""
import json

BLOCK = "# why one\n# why two\nx = 1\n"


def decision(result):
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout) if result.stdout.strip() else None


def test_post_tool_use_blocks(repo, hook):
    repo.write("a.tf", BLOCK)
    payload = json.dumps({"tool_input": {"file_path": "a.tf"}})
    out = decision(hook("--post-tool-use", payload))
    assert out["decision"] == "block"
    assert "a.tf:1-2" in out["reason"]
    assert "single non-obvious" in out["reason"]


def test_post_tool_use_passes_a_one_liner(repo, hook):
    repo.write("a.tf", "# a single non-obvious why\nx = 1\n")
    payload = json.dumps({"tool_input": {"file_path": "a.tf"}})
    assert decision(hook("--post-tool-use", payload)) is None


def test_post_tool_use_ignores_unsupported_and_missing(repo, hook):
    repo.write("a.rb", BLOCK)
    for path in ("a.rb", "gone.tf"):
        payload = json.dumps({"tool_input": {"file_path": path}})
        assert decision(hook("--post-tool-use", payload)) is None


def test_unparseable_stdin_is_a_no_op(repo, hook):
    for flag in ("--post-tool-use", "--stop-hook"):
        assert decision(hook(flag, "not json")) is None


def test_stop_hook_blocks_on_a_turn_touched_file(repo, hook):
    repo.write("a.py", BLOCK)
    out = decision(hook("--stop-hook", "{}"))
    assert out["decision"] == "block" and "a.py:1-2" in out["reason"]


def test_stop_hook_active_short_circuits(repo, hook):
    repo.write("a.py", BLOCK)
    payload = json.dumps({"stop_hook_active": True})
    assert decision(hook("--stop-hook", payload)) is None


def test_warnings_ride_along_but_never_block_alone(repo, hook):
    repo.write("a.tf", "# creates the bucket\nx = 1\n")
    assert decision(hook("--stop-hook", "{}")) is None


def test_cli_audits_whole_files_and_exits_1(repo, cli):
    repo.write("a.tf", BLOCK)
    repo.commit()
    result = cli("a.tf")
    assert result.returncode == 1
    assert "a.tf:1-2" in result.stdout


def test_cli_clean_exits_0(repo, cli):
    repo.write("a.tf", "# a single non-obvious why\nx = 1\n")
    assert cli("a.tf").returncode == 0


def test_cli_rejects_an_unsplit_file_list(repo, cli):
    """A whole newline-joined list arriving as one argument must not read as a pass.

    zsh doesn't word-split `$FILES`, so the old `python3 lint.py $FILES` passed one
    6 KB argument and exited 0 having inspected nothing.
    """
    names = [repo.write(f"a{i}.tf", BLOCK) for i in range(3)]
    result = cli("\n".join(names))
    assert result.returncode == 2
    assert "no such path" in result.stderr and "xargs" in result.stderr


def test_cli_rejects_no_arguments(repo, cli):
    result = cli()
    assert result.returncode == 2 and "usage" in result.stderr


def test_cli_rejects_a_missing_path(repo, cli):
    result = cli("nope.tf")
    assert result.returncode == 2 and "no such path" in result.stderr


def test_cli_rejects_a_scope_with_no_supported_files(repo, cli):
    repo.write("README.md", "# not code\n# at all\n")
    result = cli("README.md")
    assert result.returncode == 2 and "supported file type" in result.stderr


def test_cli_fails_on_an_undecodable_file(repo, cli):
    """UnicodeDecodeError doesn't name the file, so collect() attaches the path."""
    (repo.path / "bad.tf").write_bytes(b"# why\n\xff\xfe not utf-8\n")
    result = cli("bad.tf")
    assert result.returncode == 2
    assert "cannot read" in result.stderr and "bad.tf" in result.stderr


def test_hooks_skip_an_undecodable_file(repo, hook):
    """The hooks race an agent mid-write, so an unreadable file is skipped, not fatal."""
    (repo.path / "bad.tf").write_bytes(b"# why\n\xff\xfe not utf-8\n")
    repo.write("good.tf", BLOCK)
    out = decision(hook("--stop-hook", "{}"))
    assert out["decision"] == "block" and "good.tf" in out["reason"]
    assert "bad.tf" not in out["reason"]


def test_post_tool_use_survives_a_file_deleted_mid_turn(repo, hook):
    payload = json.dumps({"tool_input": {"file_path": "vanished.tf"}})
    assert decision(hook("--post-tool-use", payload)) is None
