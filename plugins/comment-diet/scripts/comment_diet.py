#!/usr/bin/env python3
"""Keep comments to one line, or none, in hash-comment code (.tf, .yml/.yaml, .sh, .py).

Flags a comment block longer than one line that the current change added — one
comment line is the bright line, else the explanation belongs in the README.
Also blocks a single-line comment that narrates the road not taken ("do X, not
Y, so … never …") — a comment about what the code doesn't do belongs in the
README if it belongs anywhere. Warns on banner/narration patterns and over-long
one-liners (a comment that long belongs in the README). Only comments the change
added (working tree vs HEAD) count, so pre-existing comments never trip on an
unrelated change.
String bodies that carry #-lines (tf/sh heredocs, YAML block scalars) are
skipped; Python is scanned with the stdlib tokenizer, so a # inside a string
or after code is never a comment.

Thresholds and patterns come from .comment-diet.json at the repo root; see
DEFAULTS. Extend by adding a LANGS entry (new file type).
"""
import fnmatch
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass, replace

# string_body names the #-carrying string kind (heredoc/yaml_block/pystring) whose body is skipped.
LANGS = {
    ".tf":   {"prefixes": ("#", "//"), "string_body": "heredoc"},
    ".sh":   {"prefixes": ("#",),      "string_body": "heredoc"},
    ".yml":  {"prefixes": ("#",),      "string_body": "yaml_block"},
    ".yaml": {"prefixes": ("#",),      "string_body": "yaml_block"},
    ".py":   {"prefixes": ("#",),      "string_body": "pystring"},
}
SUFFIXES = tuple(LANGS)

DIRECTIVE = re.compile(r"checkov:skip=|tflint-ignore", re.IGNORECASE)
HEREDOC_OPEN = re.compile(r"<<-?(\w+)\s*$")
YAML_BLOCK = re.compile(r"(?::|^-)\s*[|>][+-]?\d*$")
DEFAULT_WARN_PATTERNS = [
    (re.compile(r"^[-=*#_]{3,}"), "banner/decoration"),
    (re.compile(r"^(create|creates|configure|configures|define|defines|"
                r"set up|setup|sets up)\b", re.IGNORECASE),
     "narrates what the code does"),
]
# Contrastive "road not taken" phrasing — blocks, same as an over-long block.
CONTRASTIVE = re.compile(
    r",\s*not\s|\binstead of\b|\brather than\b|\bas opposed to\b|"
    r"\bto avoid\b|\bto prevent\b|\botherwise\b|\bso\b[^,.]*\bnever\b",
    re.IGNORECASE)

FIX = ("For each block: reduce to a single non-obvious 'why' line, or move the "
       "explanation to the root README. Delete banner/narration comments.")

CONFIG_FILE = ".comment-diet.json"


@dataclass(frozen=True)
class Config:
    max_lines: int = 1
    max_length: int = 120
    contrastive: bool = True
    warn_patterns: tuple = tuple(DEFAULT_WARN_PATTERNS)
    exclude: tuple = ()


DEFAULTS = Config()


class ConfigError(Exception):
    """A malformed .comment-diet.json — reported, never guessed at."""


def _typed(data, key, kind):
    """data[key], checked. `True` is an int to Python, so bools are rejected explicitly."""
    value = data[key]
    if not isinstance(value, kind) or (kind is not bool and isinstance(value, bool)):
        raise ConfigError(f"{CONFIG_FILE}: '{key}' must be {kind.__name__}")
    return value


def _compiled_warn_patterns(data):
    """User warn_patterns, appended to the built-ins unless they're switched off."""
    base = list(DEFAULT_WARN_PATTERNS) if data.get("default_warn_patterns", True) else []
    for entry in _typed(data, "warn_patterns", list) if "warn_patterns" in data else []:
        try:
            base.append((re.compile(entry["pattern"]), entry["label"]))
        except (TypeError, KeyError) as exc:
            raise ConfigError(f"{CONFIG_FILE}: each warn_patterns entry needs "
                              "'pattern' and 'label'") from exc
        except re.error as exc:
            raise ConfigError(f"{CONFIG_FILE}: bad warn_patterns regex: {exc}") from exc
    return tuple(base)


def parse_config(data):
    """Config from parsed JSON; every key optional, unknown keys ignored."""
    if not isinstance(data, dict):
        raise ConfigError(f"{CONFIG_FILE}: top level must be an object")
    fields = {}
    if "max_lines" in data:
        fields["max_lines"] = _typed(data, "max_lines", int)
    if "max_length" in data:
        fields["max_length"] = _typed(data, "max_length", int)
    if "contrastive" in data:
        fields["contrastive"] = _typed(data, "contrastive", bool)
    if "exclude" in data:
        fields["exclude"] = tuple(_typed(data, "exclude", list))
    fields["warn_patterns"] = _compiled_warn_patterns(data)
    return replace(DEFAULTS, **fields)


def config_path():
    """Path to the config file at the repo root, else the cwd."""
    root = _git("rev-parse", "--show-toplevel").strip() or "."
    return os.path.join(root, CONFIG_FILE)


def load_config():
    """Config from disk; DEFAULTS when there's no file. Raises ConfigError if broken."""
    path = config_path()
    if not os.path.exists(path):
        return DEFAULTS
    try:
        with open(path, encoding="utf-8") as f:
            return parse_config(json.load(f))
    except ValueError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def hook_config():
    """Config for a hook run: defaults with a warning if it's broken.

    A broken config must never wedge the agent loop, so the hooks degrade where
    the CLI (a human is reading) exits non-zero.
    """
    try:
        return load_config()
    except ConfigError as exc:
        print(f"comment-diet: {exc} — using defaults", file=sys.stderr)
        return DEFAULTS


def lang_for(path):
    """Language config for path's extension, or None if unsupported."""
    for ext, cfg in LANGS.items():
        if path.endswith(ext):
            return cfg
    return None


def excluded(path, patterns):
    """True if path matches an exclude glob.

    fnmatch's `*` already crosses `/`, so a leading `**/` is also tried without
    it — `**/vendor/**` should exclude a top-level `vendor/` too.
    """
    posix = path.replace(os.sep, "/")
    return any(fnmatch.fnmatch(posix, p) or fnmatch.fnmatch(posix, p.removeprefix("**/"))
               for p in patterns)


def comment_body(s, prefixes):
    """Comment text with its prefix marker stripped, so warn patterns stay prefix-agnostic."""
    for p in prefixes:
        if s.startswith(p):
            return s[len(p):].lstrip()
    return s


def py_prose_comments(lines):
    """(lineno, body) for each full-line # comment in Python source, via tokenize.

    The tokenizer reports COMMENT tokens with their real position, so a # inside
    a string or trailing a code line never registers — the counting heuristic the
    other languages use can't distinguish those. Best-effort on unparseable
    source (mid-edit): tokens seen before the error still count.
    """
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO("\n".join(lines) + "\n").readline):
            if tok.type != tokenize.COMMENT or tok.line[:tok.start[1]].strip():
                continue
            if tok.string.startswith("#!") or DIRECTIVE.search(tok.string):
                continue
            out.append((tok.start[0], comment_body(tok.string, ("#",))))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return out


def prose_comments(lines, cfg):
    """(lineno, body) for each full-line comment, skipping heredoc/block-scalar bodies.

    Shebangs and checkov/tflint directives don't count — they're allowed beside
    code, so they break a comment run just like a blank or code line does.
    """
    if cfg["string_body"] == "pystring":
        return py_prose_comments(lines)
    out = []
    heredoc = None
    block_indent = None
    for i, raw in enumerate(lines, 1):
        s = raw.strip()
        if block_indent is not None:
            if s == "" or (len(raw) - len(raw.lstrip())) > block_indent:
                continue
            block_indent = None
        if heredoc is not None:
            if s == heredoc:
                heredoc = None
        elif s.startswith(cfg["prefixes"]) and not s.startswith("#!") and not DIRECTIVE.search(s):
            out.append((i, comment_body(s, cfg["prefixes"])))
        elif cfg["string_body"] == "heredoc" and (m := HEREDOC_OPEN.search(s)):
            heredoc = m.group(1)
        elif cfg["string_body"] == "yaml_block" and YAML_BLOCK.search(s):
            block_indent = len(raw) - len(raw.lstrip())
    return out


def blocks(prose):
    """Runs of contiguous prose comment lines as (start, end) pairs."""
    runs = []
    start = prev = None
    for lineno, _ in prose:
        if prev is not None and lineno == prev + 1:
            prev = lineno
        else:
            if start is not None:
                runs.append((start, prev))
            start = prev = lineno
    if start is not None:
        runs.append((start, prev))
    return runs


def violations(prose, added, conf):
    """Comment blocks over conf.max_lines that the change added or touched."""
    return [(s, e) for s, e in blocks(prose)
            if e - s + 1 > conf.max_lines and not added.isdisjoint(range(s, e + 1))]


def contrastive(prose, added, conf):
    """Added one-line comments narrating the road not taken (blocking)."""
    if not conf.contrastive:
        return []
    return [lineno for lineno, s in prose
            if lineno in added and CONTRASTIVE.search(s)]


def warnings(prose, added, conf):
    """Added comment lines that are over-long or match a warn pattern."""
    out = []
    for lineno, s in prose:
        if lineno not in added:
            continue
        if len(s) > conf.max_length:
            out.append((lineno, f"over {conf.max_length} chars — a one-liner that "
                                "long belongs in the README"))
        for pattern, label in conf.warn_patterns:
            if pattern.match(s):
                out.append((lineno, label))
                break
    return out


def _git(*args):
    """stdout of `git <args>`, or '' if git fails or is absent."""
    try:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True,
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def parse_added(diff):
    """New-file line numbers marked + in a --unified=0 diff."""
    added = set()
    lineno = 0
    for line in diff.splitlines():
        h = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
        if h:
            lineno = int(h.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            added.add(lineno)
            lineno += 1
        elif not line.startswith("-"):
            lineno += 1
    return added


def added_linenos(path):
    """Line numbers the change adds/edits in path (working tree vs HEAD).

    None when there's no diff (e.g. a brand-new untracked file), so the caller
    audits the whole file — all of a new file is new.
    """
    diff = _git("diff", "--unified=0", "HEAD", "--", path)
    return parse_added(diff) if diff.strip() else None


def check_file(path, cfg, conf, whole_file=False):
    """Findings for one file. Raises OSError/UnicodeDecodeError if it can't be read.

    The caller decides what an unreadable file means: the CLI fails, the hooks
    skip it. A linter that silently inspects nothing must never look like a pass.
    """
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    added = None if whole_file else added_linenos(path)
    if added is None:
        added = set(range(1, len(lines) + 1))
    prose = prose_comments(lines, cfg)
    return (violations(prose, added, conf),
            contrastive(prose, added, conf),
            warnings(prose, added, conf))


def collect(paths, conf, whole_file=False, skip_unreadable=False):
    """(violation lines, warning lines) as human-readable strings across paths.

    whole_file audits every line (the CLI audit); otherwise scope to the change.
    skip_unreadable swallows a file that vanished or won't decode — the hooks race
    against an agent still editing, where the CLI wants the error.
    """
    viol_lines, warn_lines = [], []
    for path in paths:
        cfg = lang_for(path)
        if cfg is None or excluded(path, conf.exclude):
            continue
        try:
            viols, contras, warns = check_file(path, cfg, conf, whole_file)
        except (OSError, UnicodeDecodeError):
            if skip_unreadable:
                continue
            raise
        for start, end in viols:
            plural = "line" if conf.max_lines == 1 else "lines"
            viol_lines.append(f"{path}:{start}-{end}: comment block longer than "
                              f"{conf.max_lines} {plural} — keep one non-obvious "
                              f"'why' line, else the README")
        for lineno in contras:
            viol_lines.append(f"{path}:{lineno}: comment narrates the road not taken "
                              f"('do X, not Y' / what the code doesn't do) — state the "
                              f"why plainly or move it to the README")
        for lineno, why in warns:
            warn_lines.append(f"{path}:{lineno}: comment {why}")
    return viol_lines, warn_lines


def changed_files():
    """Supported files the turn touched: HEAD diff + untracked new files.

    `git diff HEAD` omits untracked files, but Claude's Write tool creates new
    files untracked, so include `ls-files --others`. The diff also reports
    deleted/renamed-away paths, so drop any that no longer exist on disk.
    """
    files = _git("diff", "--name-only", "HEAD").splitlines()
    files += _git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({p for p in files
                   if p.endswith(SUFFIXES) and os.path.exists(p)})


def _block(viol_lines, warn_lines):
    """Emit a block decision with the fix reason; 0 (no violation) otherwise."""
    if not viol_lines:
        return 0
    reason = "\n".join([*viol_lines, *warn_lines, "", FIX])
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def post_tool_use_hook():
    """PostToolUse hook for Write/Edit/MultiEdit: lint the just-edited file.

    Fires the moment an edit lands — before any same-turn `git commit`, while the
    change still sits uncommitted in the working tree, so `git diff HEAD` scopes
    it correctly. The Stop hook can't see a change committed mid-turn; this can.
    """
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    path = (payload.get("tool_input") or {}).get("file_path")
    if not path or lang_for(path) is None or not os.path.exists(path):
        return 0
    return _block(*collect([path], hook_config(), skip_unreadable=True))


def stop_hook():
    """Stop-hook backstop: catch turn-touched files the PostToolUse hook missed.

    Deterministic tripwire (the regex), LLM resolution (Claude reads `reason` and
    decides keep-one-line / move-to-README / delete). Warnings ride along in the
    reason but never trip the block on their own.
    """
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        payload = {}
    if payload.get("stop_hook_active"):
        return 0
    return _block(*collect(changed_files(), hook_config(), skip_unreadable=True))


USAGE = ("usage: comment_diet.py <file>... — audits whole files.\n"
         "Pipe a file list in rather than expanding a variable: shells differ on "
         "word-splitting (zsh doesn't split $VAR), so use\n"
         "  ... | tr '\\n' '\\0' | xargs -0 python3 comment_diet.py")


def check_argv(argv):
    """Reason the arguments can't be audited, or None.

    Guards against a mis-invocation that inspects nothing — the whole file list
    arriving as one unsplit argument, a typo'd path, a scope with no supported
    files. Each of those used to exit 0 and read as a clean bill of health.
    """
    if not argv:
        return USAGE
    missing = [p for p in argv if not os.path.exists(p)]
    if missing:
        shown = ", ".join(repr(p[:60]) for p in missing[:3])
        return (f"no such path: {shown}" +
                (f" (+{len(missing) - 3} more)" if len(missing) > 3 else "") +
                ("\n" + USAGE if len(argv) == 1 and "\n" in argv[0] else ""))
    if not any(lang_for(p) for p in argv):
        return (f"none of the {len(argv)} given path(s) is a supported file type "
                f"({', '.join(SUFFIXES)})")
    return None


def main(argv):
    """Audit the given files in full; 1 on a violation, 2 on a bad config or invocation."""
    problem = check_argv(argv)
    if problem:
        print(f"comment-diet: {problem}", file=sys.stderr)
        return 2
    try:
        conf = load_config()
    except ConfigError as exc:
        print(f"comment-diet: {exc}", file=sys.stderr)
        return 2
    try:
        viol_lines, warn_lines = collect(argv, conf, whole_file=True)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"comment-diet: cannot read {exc}", file=sys.stderr)
        return 2
    for line in viol_lines:
        print(line)
    for line in warn_lines:
        print(f"warning: {line}", file=sys.stderr)
    if viol_lines:
        print("\n" + FIX, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if sys.argv[1:2] == ["--stop-hook"]:
        sys.exit(stop_hook())
    if sys.argv[1:2] == ["--post-tool-use"]:
        sys.exit(post_tool_use_hook())
    sys.exit(main(sys.argv[1:]))
