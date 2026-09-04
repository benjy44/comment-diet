# comment-diet

**Puts agent-written comments on a diet: one line, or none — and one concise summary sentence for a
doc comment.**

A Claude Code plugin that blocks useless comments the moment an agent writes them — not in review,
three days later, when deleting them has become an argument.

## The problem

Coding agents narrate. Ask one for a Terraform resource and you get:

```hcl
# ---------------------------------------------------------------
# S3 bucket for findings
# ---------------------------------------------------------------
# Creates the destination bucket for Config findings. We use a
# separate bucket here rather than reusing the logging bucket so
# that the lifecycle rules don't interfere with each other.
resource "aws_s3_bucket" "findings" { ... }
```

Six lines of comment for one line of code, and every one of them is filler: a banner, a restatement
of the resource name, and a paragraph defending a decision against an alternative nobody proposed.

Agents produce this faster than any human can delete it. By the time it reaches review, it's in a
diff someone has to argue about, and "please cut the comments" is a tedious thing to say on every
PR. So it survives, and the codebase fills with prose that nobody reads and nobody trusts.

`comment-diet` moves the enforcement into the agent loop. A deterministic tripwire fires on the edit
itself, and the agent fixes it before the turn ends. You never see it.

## The rule

Not "no comments" — **one line, or none.**

A comment is allowed as a single line stating a non-obvious *why* that (a) isn't visible in the
code, (b) isn't generic language or platform behaviour a reader can look up, and (c) isn't already
written in a README. If the *why* needs more than one line, it belongs in the README.

That leaves room for the comments that earn their place:

```hcl
# CT owns the source bucket; replication attaches by name (TF needn't own it).
resource "aws_s3_bucket_replication_configuration" "x" { ... }
```

```python
# The vendor API 500s on batches over 50, despite documenting 200.
for chunk in chunked(users, 50): ...
```

Both state something you cannot learn from the code and cannot look up. Neither needs a second line.

## The three tiers

### Tier 1 — ordinary comments

One line, or none.

| | |
|---|---|
| **Blocks** | a comment block longer than one line; road-not-taken phrasing (`, not `, `instead of`, `rather than`, `to avoid`, `to prevent`, `otherwise`, `so … never`) |
| **Warns** | banners (`# ------`), narration (`# creates the bucket`), one-liners over 120 characters |

Code states what *is*; a defence against the rejected alternative belongs in the README. Warnings
are reported alongside a block, never blocking on their own.

### Tier 2 — doc comments

Go doc comments, JSDoc, Rust doc comments and Python docstrings are **not exempt**. They get their
own rule instead, because the tooling that consumes them needs a summary rather than an essay:
godoc's package index uses only [the first
sentence](https://pkg.go.dev/go/doc#Package.Synopsis), rustdoc's item tables show only the first
paragraph, and revive's `exported` rule requires a doc comment to *exist* without setting any
length.

| | |
|---|---|
| **Budget** | 200 characters of prose across the whole comment (**warns** past 120). Counted in characters, not lines, so an 80-column repo and a 120-column repo are treated identically and the hook never fires over wrapping style. Fenced code (```` ``` ````) is code, not prose — never counted. |
| **Blocks at any length** | a second paragraph (a blank `//` or `*` line); lists; section headers that restate the signature (`Args:`, `Returns:`, `Example:`, markdown `# Arguments`/`# Returns`, numpy underlines); `@param`/`@returns`/`@type` in `.ts`/`.tsx`/`.rs`; filler openers (`This function…`, `This file…`) |

`@param` and `@returns` are **allowed in `.js`/`.jsx`/`.mjs`**, where they carry the only type
information there is, and blocked in TypeScript, where the signature already says it.

Filler openers and section headers are blocked in ordinary comments too — filler is filler
regardless of where it sits.

```go
// ParseConfig reads path and applies defaults; a missing file is not an error.
func ParseConfig(path string) (*Config, error) { ... }
```

78 characters, starts with the identifier, satisfies revive and godoc, passes.

### Tier 3 — licence lines

`Copyright`, `SPDX-License-Identifier:`, `Licensed under`, `All rights reserved`, `@license`, and
MIT/Apache/BSD boilerplate are free and uncounted. Nothing else in a file header is, so a mandated
header passes while `// This file contains the HTTP handlers…` sitting beside it does not.

## Rust specifics

`///`, `//!`, `/** */` and `/*! */` are doc comments and get Tier 2. Plain `//` is an ordinary
comment and gets Tier 1 **even directly above an item** — Rust, unlike Go, marks its doc comments
explicitly. `////` is an ordinary comment too, as the compiler treats it.

**Rustdoc sections get their own paragraph.** `# Safety`, `# Errors`, `# Panics` and `# Examples`
each carry something a signature cannot — which errors an `io::Result` holds, when a call panics,
what invariant an `unsafe fn` puts on its caller, how the thing is used — so each is budgeted
separately instead of counting against the summary sentence:

````rust
/// Reads path and applies defaults; a missing file is not an error.
///
/// # Errors
///
/// Returns `Err` when path exists but cannot be read.
///
/// # Examples
///
/// ```
/// let cfg = parse_config(Path::new("app.toml"))?;
/// # Ok::<(), io::Error>(())
/// ```
pub fn parse_config(path: &Path) -> io::Result<Config> { ... }
````

**Doctests are encouraged, never counted.** A fenced block is executable code that `cargo test`
runs, not prose, so it is skipped whole: its length, its comments and any line in it that looks like
a list are all invisible to the hook. Deleting a doctest to satisfy a comment linter would delete a
test — [C-EXAMPLE](https://rust-lang.github.io/api-guidelines/documentation.html) asks for the
opposite.

`# Arguments` and `# Returns` stay blocked: the typed signature already says that. Prose inside a
kept section is still one paragraph, no lists, same 200-character budget. `// SAFETY:` beside an
`unsafe` block is an ordinary comment: one line, never read as a section header.

### Staying in sync with clippy

Nothing a clippy lint requires is blocked.

| clippy lint | Default | comment-diet |
|---|---|---|
| `missing_safety_doc` | warn | `# Safety` passes |
| `missing_errors_doc` | allow | `# Errors` passes |
| `missing_panics_doc` | allow | `# Panics` passes |
| `undocumented_unsafe_blocks` | allow | a one-line `// SAFETY:` passes |
| `unnecessary_safety_doc` | allow | **warns** on `# Safety` above a safe `fn` |
| `empty_docs` | warn | delete the `///` markers along with the prose |
| `doc_lazy_continuation` | warn | no interaction (lists are blocked outright) |
| `tabs_in_doc_comments` | warn | no interaction |
| `too_long_first_doc_paragraph` | allow | same idea, looser: 200 characters |

Where rustfmt runs with `wrap_comments = true` and `comment_width = 80`, set `"max_length": 80` so
rustfmt never rewraps a passing one-liner into a block that Tier 1 then blocks.

## Languages

`.tf` `.yml` `.yaml` `.sh` `.py` `.go` `.rs` `.ts` `.tsx` `.js` `.jsx` `.mjs`

Never counted: shebangs, `//go:*`, `nolint`, `checkov:skip=`, `tflint-ignore`, `eslint-*`,
`@ts-ignore`, `@ts-expect-error`, `prettier-ignore`, `biome-ignore`, `/// <reference`, `noqa`,
`type: ignore`, `pylint:`, `ruff:`, `mypy:`.

Never scanned: heredoc bodies (`.tf`, `.sh`), YAML block scalars, Python string bodies, Go raw
strings, Rust raw strings (`r"…"`, `r#"…"#`), and JavaScript template literals. Python is scanned
with the stdlib `tokenize` and `ast` modules; the rest track string bodies explicitly.

## Install

```
/plugin marketplace add benjy44/comment-diet
/plugin install comment-diet
```

Requires `python3` (3.9+) on `PATH`. No dependencies, no `pip install`, nothing to build — the
linter is one stdlib-only file.

## What you get

**Two hooks.** `PostToolUse` on `Write|Edit|MultiEdit` lints the file the moment an edit lands,
while the change still sits uncommitted so `git diff HEAD` scopes it correctly — and before any
same-turn `git commit` can hide it. A `Stop` hook backstops the whole turn over `git diff HEAD` plus
untracked files, for anything the first hook missed.

**Only comments the current change added or touched are evaluated**, so a pre-existing comment never
trips on an unrelated edit — you can adopt this on a large codebase without a flag day. Editing one
line inside an existing block does put the whole block in scope: touch it, tidy it. A brand-new file
is audited in full.

**A `writing-comments` skill** carrying the clause test, the three tiers, and worked examples in Go,
Rust, TypeScript, Python, HCL and Bash, so comments come out lean in the first place instead of only
getting caught. Prevention beats blocking.

**`/comment-diet:audit [path]`** audits *whole files* rather than the current change, for cleaning
up a codebase that predates the plugin.

The CLI exits **0** clean, **1** on violations, and **2** when it could not run at all — bad
arguments, an unreadable file, a malformed config. It refuses to inspect nothing quietly: pass a
path that doesn't exist, or a whole newline-joined file list as one argument (what an unquoted
`$FILES` becomes in zsh, which doesn't word-split), and you get exit 2 with a diagnosis instead of a
clean bill of health. Pipe file lists through `tr '\n' '\0' | xargs -0 -r` (`-r` so an empty scope
runs nothing instead of tripping the usage check on GNU xargs).

The division of labour is deliberate: a regex is the tripwire, the agent is the resolver. The hook
never rewrites your comment — it hands the agent the finding and the three legitimate resolutions
(keep one line, move it to the README, delete it) and lets it choose.

## Configuration

Optional. Drop `.comment-diet.json` at the repo root; every key is optional, and an absent file
means the defaults below.

```json
{
  "max_lines": 1,
  "max_length": 120,
  "max_doc_chars": 200,
  "warn_doc_chars": 120,
  "contrastive": true,
  "docstrings": true,
  "default_warn_patterns": true,
  "warn_patterns": [{ "pattern": "^TODO", "label": "unowned TODO" }],
  "exclude": ["**/vendor/**", "**/.terraform/**"]
}
```

| Key | Default | Meaning |
|---|---|---|
| `max_lines` | `1` | Longest allowed comment block. `2` if one line is too strict for you. |
| `max_length` | `120` | Warn above this many characters on a single comment line. |
| `max_doc_chars` | `200` | Block threshold for doc comment prose. |
| `warn_doc_chars` | `120` | Warn threshold for doc comment prose. |
| `contrastive` | `true` | Block road-not-taken comments. Set `false` to keep only the length rules. |
| `docstrings` | `true` | Apply Tier 2 rules to Python docstrings. |
| `default_warn_patterns` | `true` | Keep the built-in banner and narration patterns. |
| `warn_patterns` | `[]` | Extra patterns, **appended** to the built-ins. Python regex, matched against the comment text with its markers stripped. |
| `exclude` | `[]` | Glob patterns; matching paths are skipped entirely. |

JSON rather than TOML on purpose: `tomllib` landed in Python 3.11, and the hook runs under whatever
`python3` is on `PATH` — which on macOS is still 3.9.

A malformed config **warns on stderr and runs with defaults** when invoked as a hook, because a
broken config file must never wedge your agent loop. The same file makes the CLI **exit 2** with the
error, where a human is reading the output and silence would hide the mistake.

## Why a hook and not a linter rule

A comment linter in CI tells you about the problem after the agent has moved on, after you've
context-switched, and in a place where the fix costs a round trip. A hook tells the agent *while it
still has the code in mind*, and the turn doesn't end until it's resolved.

It's also why the check is deliberately dumb. A model asked to judge whether a comment is
"load-bearing" will talk itself into yes — that's exactly the rationalization the rule exists to
prevent. A regex can't be persuaded. Let the tripwire be mechanical and the resolution be
intelligent.

## Known limitations

Comment extraction is line-based, not AST-based, for every language except Python. An unbalanced
backtick inside a Go rune literal or a quoted string can desync the raw-string tracker, a nested
Rust block comment ends at the first `*/`, an unclosed code fence hides the rest of its doc comment,
and a line beginning with `//` inside an untracked string could be read as a comment. Use an
`exclude` glob where that bites.

Outside a git repository, or where `git` is unavailable, there is no diff to scope against and every
comment in the file is evaluated.

## Not in scope (yet)

PyPI packaging and a `pre-commit` hook definition, so the same linter runs in CI. Welcome as a PR.

## Development

```bash
python3 -m pytest tests -q
ruff check .
claude plugin validate . --strict
```

The version in `plugins/comment-diet/.claude-plugin/plugin.json` and the one in
`.claude-plugin/marketplace.json` must match; `--strict` is what catches a mismatch, and CI runs it.

## Credits

The doc-comment tier and the Go, Rust, TypeScript and JavaScript support come from
[Playground Tech](https://github.com/playgroundtech), whose work on this plugin is merged back
here.

## License

MIT.
