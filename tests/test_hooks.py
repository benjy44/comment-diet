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
