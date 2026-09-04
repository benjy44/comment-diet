#!/usr/bin/env python3
"""Keep comments to one line, and doc comments to one summary sentence; see the README."""
import ast
import fnmatch
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field, replace

# string_body names the string kind whose body is skipped; doc, the doc-comment convention.
_HASH = {"prefixes": ("#",), "kind": "hash"}
_SLASH = {"prefixes": ("//",), "kind": "slash", "string_body": "backtick"}
LANGS = {
    ".tf":   {**_HASH, "prefixes": ("#", "//"), "string_body": "heredoc", "doc": None},
    ".sh":   {**_HASH, "string_body": "heredoc", "doc": None},
    ".yml":  {**_HASH, "string_body": "yaml_block", "doc": None},
    ".yaml": {**_HASH, "string_body": "yaml_block", "doc": None},
    ".py":   {**_HASH, "string_body": "pystring", "doc": "docstring"},
    ".go":   {**_SLASH, "doc": "godoc", "typed": True},
    ".rs":   {**_SLASH, "prefixes": ("///", "//!", "//"), "string_body": "rust_raw",
              "doc": "rustdoc", "doc_openers": ("///", "//!", "/**", "/*!"),
              "typed": True, "sections": True},
    ".ts":   {**_SLASH, "doc": "jsdoc", "typed": True},
    ".tsx":  {**_SLASH, "doc": "jsdoc", "typed": True},
    ".js":   {**_SLASH, "doc": "jsdoc", "typed": False},
    ".jsx":  {**_SLASH, "doc": "jsdoc", "typed": False},
    ".mjs":  {**_SLASH, "doc": "jsdoc", "typed": False},
}
SUFFIXES = tuple(LANGS)

# godoc is missing here because it needs a declaration under it, per is_doc.
DOC_STYLES = ("jsdoc", "docstring", "rustdoc")

HEREDOC_OPEN = re.compile(r"<<-?(\w+)\s*$")
YAML_BLOCK = re.compile(r"(?::|^-)\s*[|>][+-]?\d*$")
BACKTICK = re.compile(r"(?<!\\)`")
RUST_RAW = re.compile(r'r(#*)"')
GO_DECL = re.compile(r"^(func|type|const|var|package)\b")

# Matched against a comment stripped of its #, / and * markers.
DIRECTIVE = re.compile(
    r"^(go:\w+|nolint|lint:ignore|gosec|nosec|eslint-|@ts-(ignore|expect-error|nocheck)"
    r"|prettier-ignore|biome-ignore|<reference\b|noqa|type:\s*ignore|pylint:|ruff:|mypy:"
    r"|fmt:\s*(on|off)|istanbul\b|c8\b|v8\b|@flow\b|jshint\b|jslint\b|global\b|deno-lint)"
    r"|checkov:skip=|tflint-ignore", re.IGNORECASE)

# An opener frees its whole run: MIT/Apache/BSD boilerplate runs on into lines matching nothing.
LICENCE = re.compile(
    r"^(copyright\b|\(c\)\s|©|spdx-|licensed under\b"
    r"|all rights reserved\b|@license\b|this file is part of\b)", re.IGNORECASE)
LICENCE_OPENER = re.compile(
    r"^(licensed under the\b|permission is hereby granted\b"
    r"|redistribution and use in source\b|this program is free software\b)", re.IGNORECASE)

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

_SECTIONS = (r"parameters|params|arguments|args|returns?|throws|raises|yields"
             r"|examples?|usage|notes?|attributes|see also")
# Only the headers that duplicate a signature; the rest fall to the paragraph rule.
DOC_SECTION = re.compile(
    rf"^(#{{1,6}}\s+(parameters|params|arguments|args|returns?)\b|({_SECTIONS})\b\s*:)",
    re.IGNORECASE)
# Sections rustdoc readers and clippy expect, each budgeted as its own paragraph.
KEPT_SECTION = re.compile(r"^#{1,6}\s+(safety|errors|panics|examples?)\b", re.IGNORECASE)
SAFETY_SECTION = re.compile(r"^#{1,6}\s+safety\b", re.IGNORECASE)
DOC_FENCE = re.compile(r"^(```|~~~)")
# Attributes and directives may sit between a doc comment and the item it documents.
RUST_SKIP = ("#[", "#![", "//")
RUST_FN = re.compile(r"^(pub\s*(\([^)]*\)\s*)?)?"
                     r'(default\s+|const\s+|async\s+|extern\s+"[^"]*"\s+)*fn\b')
DOC_UNDERLINE = re.compile(r"^[-=~^]{3,}\s*$")
DOC_BULLET = re.compile(r"^([-*+•]|\d+[.)])\s+")
DOC_TYPE_TAG = re.compile(r"^@(param|returns?|type|arg|argument)\b", re.IGNORECASE)
DOC_PREAMBLE = re.compile(
    r"^this (file|function|method|type|struct|class|package|module|interface"
    r"|component|constant|variable|field|const|var|script|module-level)\b"
    r"|^(a |the )?(helper|utility|convenience) (function|method|type|class|struct)\b"
    r"|^(function|method|class|struct|type) (that|which|to)\b", re.IGNORECASE)
DOC_SIGNATURE = re.compile(r"\b(takes|accepts|receives)\b.{0,80}\breturns?\b", re.IGNORECASE)

SUMMARY_SAYS = ("doc comment", "keep the summary sentence, move the rest to the README",
                "cut to one concise summary sentence")


FIX = ("For each finding: reduce to a single non-obvious 'why' line (a doc comment "
       "to one concise summary sentence), or move the explanation to the README. "
       "Delete banners, narration and restated signatures.")

CONFIG_FILE = ".comment-diet.json"


@dataclass(frozen=True)
class Config:
    max_lines: int = 1
    max_length: int = 120
    max_doc_chars: int = 200
    warn_doc_chars: int = 120
    contrastive: bool = True
    docstrings: bool = True
    warn_patterns: tuple = field(default_factory=lambda: tuple(DEFAULT_WARN_PATTERNS))
    exclude: tuple = ()


DEFAULTS = Config()


@dataclass(frozen=True)
class Run:
    """One contiguous comment: its line span, its prose lines, and its style."""
    start: int
    end: int
    lines: tuple
    style: str


@dataclass(frozen=True)
class Finding:
    start: int
    end: int
    level: str
    message: str


class ConfigError(Exception):
    """A malformed .comment-diet.json — reported, never guessed at."""


class ReadError(Exception):
    """A file that couldn't be read, named — UnicodeDecodeError alone doesn't say which."""


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
    for key in ("max_lines", "max_length", "max_doc_chars", "warn_doc_chars"):
        if key in data:
            fields[key] = _typed(data, key, int)
    for key in ("contrastive", "docstrings"):
        if key in data:
            fields[key] = _typed(data, key, bool)
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
    """Config for a hook run: defaults with a warning if it's broken, never a hard fail."""
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
    """True if path matches an exclude glob, with or without a leading `**/`."""
    posix = path.replace(os.sep, "/")
    return any(fnmatch.fnmatch(posix, p) or fnmatch.fnmatch(posix, p.removeprefix("**/"))
               for p in patterns)


def comment_body(s, prefixes):
    """Comment text with its prefix marker stripped, so patterns stay prefix-agnostic."""
    for p in prefixes:
        if s.startswith(p):
            return s[len(p):].lstrip()
    return s


def is_directive(body):
    """True for a tooling pragma, which is allowed beside code and never counted."""
    return bool(DIRECTIVE.search(body.lstrip("/*# ").strip()))


def _run(pairs, style):
    return Run(pairs[0][0], pairs[-1][0], tuple(b for _, b in pairs), style)


def group(prose, style="line"):
    """Contiguous (lineno, body) pairs grouped into Runs."""
    runs, cur = [], []
    for lineno, body in prose:
        if cur and lineno == cur[-1][0] + 1:
            cur.append((lineno, body))
        else:
            if cur:
                runs.append(_run(cur, style))
            cur = [(lineno, body)]
    if cur:
        runs.append(_run(cur, style))
    return runs


def py_hash_comments(lines):
    """(lineno, body) per full-line # comment; on a syntax error, the tokens seen so far count."""
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO("\n".join(lines) + "\n").readline):
            if tok.type != tokenize.COMMENT or tok.line[:tok.start[1]].strip():
                continue
            if tok.string.startswith("#!") or is_directive(tok.string):
                continue
            out.append((tok.start[0], comment_body(tok.string, ("#",))))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return out


def hash_comments(lines, cfg):
    """(lineno, body) for each full-line comment, skipping heredoc/block-scalar bodies."""
    if cfg["string_body"] == "pystring":
        return py_hash_comments(lines)
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
        elif s.startswith(cfg["prefixes"]) and not s.startswith("#!") and not is_directive(s):
            out.append((i, comment_body(s, cfg["prefixes"])))
        elif cfg["string_body"] == "heredoc" and (m := HEREDOC_OPEN.search(s)):
            heredoc = m.group(1)
        elif cfg["string_body"] == "yaml_block" and YAML_BLOCK.search(s):
            block_indent = len(raw) - len(raw.lstrip())
    return out


def _block_piece(s):
    """(text, closed) for a /* */ line, minus the `*` gutter, so `* - item` reads as a list."""
    closed = "*/" in s
    text = (s.split("*/", 1)[0] if closed else s).strip()
    if text.startswith("*"):
        text = text[1:].lstrip()
    return text, closed


def comment_style(s, cfg, default):
    """The run style for a comment opener: the language's doc style, or `default`."""
    if s.startswith("////") or not s.startswith(cfg.get("doc_openers", ("/**",))):
        return default
    return cfg["doc"] if cfg["doc"] in DOC_STYLES else "jsdoc"


def raw_open(s, mode):
    """State of a string left open on line s, or None when none is."""
    if mode == "rust_raw":
        for m in RUST_RAW.finditer(s):
            if ('"' + m.group(1)) not in s[m.end():]:
                return len(m.group(1))
        return None
    return True if len(BACKTICK.findall(s)) % 2 else None


def raw_closed(s, state, mode):
    """True if line s closes the open string described by state."""
    if mode == "rust_raw":
        return ('"' + "#" * state) in s
    return len(BACKTICK.findall(s)) % 2 == 1


def slash_runs(lines, cfg):
    """Runs for a //-comment language, skipping raw string and template literal bodies."""
    runs, pending = [], []
    raw = block_start = block_style = None
    block_body = []
    style = "line"
    mode = cfg["string_body"]

    def flush():
        if pending:
            runs.extend(group(pending, style))
            pending.clear()

    for i, rawline in enumerate(lines, 1):
        s = rawline.strip()
        if block_start is not None:
            text, closed = _block_piece(s)
            block_body.append(text)
            if closed:
                runs.append(Run(block_start, i, tuple(block_body), block_style))
                block_start = None
            continue
        if raw is not None:
            if raw_closed(s, raw, mode):
                raw = None
            continue
        if s.startswith("//"):
            if is_directive(s):
                flush()
            else:
                line_style = comment_style(s, cfg, "line")
                if line_style != style:
                    flush()
                    style = line_style
                pending.append((i, comment_body(s, cfg["prefixes"])))
            continue
        flush()
        if s.startswith("/*"):
            block_style = comment_style(s, cfg, "block")
            head = s[3:] if block_style in DOC_STYLES else s[2:]
            text, closed = _block_piece(head)
            if closed:
                runs.append(Run(i, i, (text,), block_style))
            else:
                block_start, block_body = i, [text]
            continue
        raw = raw_open(s, mode)
    flush()
    if block_start is not None:
        runs.append(Run(block_start, len(lines), tuple(block_body), block_style))
    return sorted(runs, key=lambda r: r.start)


def docstring_runs(source):
    """Runs for module, class and function docstrings, via the stdlib ast module."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []
    out = []
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        text = ast.get_docstring(node, clean=True)
        if text is None:
            continue
        expr = node.body[0]
        out.append(Run(expr.lineno, expr.end_lineno,
                       tuple(ln.strip() for ln in text.splitlines()), "docstring"))
    return sorted(out, key=lambda r: r.start)


def is_doc(run, lines, cfg):
    """True if the run is a doc comment under its language's convention."""
    if run.style in DOC_STYLES:
        return True
    if cfg["doc"] != "godoc" or run.style not in ("line", "block"):
        return False
    i = run.end
    while i < len(lines) and lines[i].strip().startswith("//") and is_directive(lines[i]):
        i += 1
    return i < len(lines) and bool(GO_DECL.match(lines[i]))


def strip_licence(run):
    """(lineno, body) prose pairs, licence boilerplate removed and blank ends trimmed."""
    kept, licensed = [], False
    for offset, body in enumerate(run.lines):
        if LICENCE_OPENER.match(body):
            licensed = True
            continue
        if licensed or LICENCE.match(body):
            continue
        kept.append((run.start + offset, body))
    while kept and not kept[0][1]:
        kept.pop(0)
    while kept and not kept[-1][1]:
        kept.pop()
    return kept


def content_findings(prose):
    """Findings that hold for every comment, doc or not — filler is filler at any length."""
    out = []
    for lineno, body in prose:
        if DOC_PREAMBLE.match(body):
            out.append(Finding(lineno, lineno, "block",
                               "comment opens with filler ('This function…', 'This file…') "
                               "— name the thing and say what it is for, or delete it"))
        elif DOC_SECTION.match(body):
            out.append(Finding(lineno, lineno, "block",
                               "comment has a section header (Args:/Returns:/Example:) "
                               "— the signature already says this"))
        elif DOC_SIGNATURE.search(body):
            out.append(Finding(lineno, lineno, "warn", "comment restates the signature"))
    return out


def trim(pairs):
    """pairs with blank lines dropped from both ends."""
    out = list(pairs)
    while out and not out[0][1]:
        out.pop(0)
    while out and not out[-1][1]:
        out.pop()
    return out


def strip_fences(prose):
    """prose with fenced blocks and their fences dropped — a doctest counts as code."""
    out, inside = [], False
    for pair in prose:
        if DOC_FENCE.match(pair[1]):
            inside = not inside
        elif not inside:
            out.append(pair)
    return out


def split_sections(prose, cfg):
    """(summary, sections) split at the first header that stands on its own."""
    if cfg.get("sections"):
        for i, (_, body) in enumerate(prose):
            if KEPT_SECTION.match(body):
                return prose[:i], prose[i:]
    return prose, []


def section_chunks(sections):
    """One [header, *body] chunk per section."""
    chunks = []
    for pair in sections:
        if KEPT_SECTION.match(pair[1]):
            chunks.append([pair])
        elif chunks:
            chunks[-1].append(pair)
    return chunks


def safe_fn_below(run, lines):
    """True where the run documents a plainly safe fn — clippy's unnecessary_safety_doc."""
    for raw in lines[run.end:]:
        s = raw.strip()
        if s and not s.startswith(RUST_SKIP):
            return bool(RUST_FN.match(s))
    return False


def section_says(header):
    """Finding wording for one section, named by its own header."""
    return (f"the `{header}` section", "keep one paragraph, move the rest to the README",
            "cut to one concise paragraph")


def para_findings(run, prose, conf, cfg, say):
    """Structural bans at any length, then the prose-character budget, for one paragraph."""
    label, trim_advice, cut_advice = say
    out = []
    for lineno, body in prose:
        if not body:
            out.append(Finding(run.start, run.end, "block",
                               f"{label} runs to a second paragraph — {trim_advice}"))
            break
        if DOC_UNDERLINE.match(body):
            out.append(Finding(lineno, lineno, "block", f"{label} has a section underline"))
        elif DOC_BULLET.match(body):
            out.append(Finding(lineno, lineno, "block",
                               f"{label} contains a list — a list belongs in the README"))
        elif cfg.get("typed") and DOC_TYPE_TAG.match(body):
            out.append(Finding(lineno, lineno, "block",
                               "@param/@returns duplicates the typed signature"))
    chars = len(" ".join(body for _, body in prose).strip())
    if chars > conf.max_doc_chars:
        out.append(Finding(run.start, run.end, "block",
                           f"{label} is {chars} chars of prose, budget "
                           f"{conf.max_doc_chars} — {cut_advice}"))
    elif chars > conf.warn_doc_chars:
        out.append(Finding(run.start, run.end, "warn",
                           f"{label} is {chars} chars of prose — getting wordy, "
                           f"{conf.warn_doc_chars} is the comfortable ceiling"))
    return out


def doc_findings(run, prose, conf, cfg, lines):
    """Tier 2 findings: the summary paragraph, then each section in its own right."""
    summary, sections = split_sections(prose, cfg)
    out = para_findings(run, trim(summary), conf, cfg, SUMMARY_SAYS)
    for chunk in section_chunks(sections):
        lineno, header = chunk[0]
        out += para_findings(run, trim(chunk[1:]), conf, cfg, section_says(header))
        if SAFETY_SECTION.match(header) and safe_fn_below(run, lines):
            out.append(Finding(lineno, lineno, "warn",
                               f"`{header}` documents a safe fn — clippy's "
                               "unnecessary_safety_doc flags this; drop the section"))
    return out


def ordinary_findings(run, prose, conf):
    """Tier 1 findings: one line, or none."""
    out = []
    if len(prose) > conf.max_lines:
        plural = "line" if conf.max_lines == 1 else "lines"
        out.append(Finding(run.start, run.end, "block",
                           f"comment block longer than {conf.max_lines} {plural} — keep "
                           f"one non-obvious 'why' line, else the README"))
    for lineno, body in prose:
        if len(body) > conf.max_length:
            out.append(Finding(lineno, lineno, "warn",
                               f"comment over {conf.max_length} chars — a one-liner that "
                               "long belongs in the README"))
        for pattern, label in conf.warn_patterns:
            if pattern.match(body):
                out.append(Finding(lineno, lineno, "warn", f"comment {label}"))
                break
    return out


def run_findings(run, lines, conf, cfg):
    """Every finding for one comment run, licence lines excluded from the reckoning."""
    prose = strip_licence(run)
    doc = is_doc(run, lines, cfg)
    if doc:
        prose = strip_fences(prose)
    if not prose:
        return []
    out = content_findings(prose)
    if conf.contrastive:
        for lineno, body in prose:
            if CONTRASTIVE.search(body):
                out.append(Finding(lineno, lineno, "block",
                                   "comment narrates the road not taken ('do X, not Y' / "
                                   "what the code doesn't do) — state the why plainly "
                                   "or move it to the README"))
    if doc:
        return out + doc_findings(run, prose, conf, cfg, lines)
    return out + ordinary_findings(run, prose, conf)


def file_runs(lines, source, conf, cfg):
    """Every comment run in the file, across both the comment and doc-comment syntaxes."""
    runs = slash_runs(lines, cfg) if cfg["kind"] == "slash" else group(hash_comments(lines, cfg))
    if cfg["doc"] == "docstring" and conf.docstrings:
        runs += docstring_runs(source)
    return sorted(runs, key=lambda r: r.start)


def check_file(path, cfg, conf, whole_file=False):
    """Findings for one file. Raises OSError/UnicodeDecodeError if it can't be read."""
    with open(path, encoding="utf-8") as f:
        source = f.read()
    lines = source.splitlines()
    added = None if whole_file else added_linenos(path)
    if added is None:
        added = set(range(1, len(lines) + 1))
    out = []
    for run in file_runs(lines, source, conf, cfg):
        if added.isdisjoint(range(run.start, run.end + 1)):
            continue
        out.extend(run_findings(run, lines, conf, cfg))
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
    """Line numbers the change adds or edits in path, or None when there's no diff."""
    diff = _git("diff", "--unified=0", "HEAD", "--", path)
    return parse_added(diff) if diff.strip() else None


def collect(paths, conf, whole_file=False, skip_unreadable=False):
    """(blocking lines, warning lines) as human-readable strings across paths."""
    viol_lines, warn_lines = [], []
    for path in paths:
        cfg = lang_for(path)
        if cfg is None or excluded(path, conf.exclude):
            continue
        try:
            findings = check_file(path, cfg, conf, whole_file)
        except (OSError, UnicodeDecodeError) as exc:
            if skip_unreadable:
                continue
            raise ReadError(f"{path}: {exc}") from exc
        for f in findings:
            span = f"{f.start}" if f.start == f.end else f"{f.start}-{f.end}"
            target = viol_lines if f.level == "block" else warn_lines
            target.append(f"{path}:{span}: {f.message}")
    return viol_lines, warn_lines


def changed_files():
    """Supported files the turn touched: the HEAD diff plus untracked new files."""
    files = _git("diff", "--name-only", "HEAD").splitlines()
    files += _git("ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({p for p in files
                   if p.endswith(SUFFIXES) and os.path.exists(p)})


def _block(viol_lines, warn_lines):
    """Emit a block decision with the fix reason, or return 0 when nothing was flagged."""
    if not viol_lines:
        return 0
    reason = "\n".join([*viol_lines, *warn_lines, "", FIX])
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


def post_tool_use_hook():
    """Lint the just-edited file, before any same-turn commit moves it out of the diff."""
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    path = (payload.get("tool_input") or {}).get("file_path")
    if not path or lang_for(path) is None or not os.path.exists(path):
        return 0
    return _block(*collect([path], hook_config(), skip_unreadable=True))


def stop_hook():
    """Backstop the whole turn: a regex is the tripwire, the agent is the resolver."""
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
    """Reason the arguments can't be audited, or None — a bad scope must never read as a pass."""
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
    except ReadError as exc:
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
