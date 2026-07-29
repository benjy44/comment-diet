import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "plugins" / "comment-diet" / "scripts" / "comment_diet.py"
sys.path.insert(0, str(SCRIPT.parent))


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """An initialised git repo, cwd'd into, with helpers to commit and write files."""
    monkeypatch.chdir(tmp_path)
    def run(*args):
        return subprocess.run(args, cwd=tmp_path, check=True,
                              capture_output=True, text=True)

    run("git", "init", "-q", "-b", "main")
    run("git", "config", "user.email", "t@example.com")
    run("git", "config", "user.name", "t")

    class Repo:
        path = tmp_path

        def write(self, name, text):
            p = tmp_path / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text)
            return name

        def commit(self, message="c"):
            run("git", "add", "-A")
            run("git", "commit", "-q", "-m", message)

    return Repo()


@pytest.fixture
def hook(repo):
    """Invoke the script as a subprocess with a JSON payload on stdin."""
    def call(flag, stdin):
        return subprocess.run([sys.executable, str(SCRIPT), flag], input=stdin,
                              cwd=repo.path, capture_output=True, text=True)
    return call


@pytest.fixture
def cli(repo):
    """Invoke the script as a subprocess in CLI (whole-file audit) mode."""
    def call(*paths):
        return subprocess.run([sys.executable, str(SCRIPT), *paths],
                              cwd=repo.path, capture_output=True, text=True)
    return call
