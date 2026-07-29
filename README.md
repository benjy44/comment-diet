# comment-diet

**Puts your comments on a diet: one line, or none.**

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

## What it flags

**Blocks:**

- a comment block longer than one line
- a comment narrating the road not taken — `# point at the file, not the dir, so the build never
  sweeps in __pycache__`. Code states what *is*; a defence against the rejected alternative belongs
  in the README.

**Warns** (reported alongside a block, never blocking on its own):

- banners and decoration — `# ---------- helpers ----------`
- narration — `# creates the bucket`, `# set up the role`
- a one-liner over 120 characters, which is a paragraph wearing a disguise

**Only comments the current change touched count.** Scoping comes from `git diff HEAD`, so a
pre-existing comment never trips on an unrelated edit — you can adopt this on a large codebase
without a flag day. A brand-new file is audited in full.

Languages: `.tf`, `.yml`/`.yaml`, `.sh`, `.py`. Never confused by a `#` inside a heredoc, a YAML
block scalar, or a Python string — Python is scanned with the stdlib tokenizer, the rest track
string bodies explicitly. Shebangs and `checkov:skip=` / `tflint-ignore` directives are exempt.

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
same-turn `git commit` can hide it. A `Stop` hook backstops the whole turn for anything the first
hook missed.

**A `writing-comments` skill** carrying the clause test, so comments come out lean in the first
place instead of only getting caught. Prevention beats blocking.

**`/comment-diet:audit [path]`** audits *whole files* rather than the current change, for cleaning
up a codebase that predates the plugin.

The CLI exits **0** clean, **1** on violations, and **2** when it could not run at all — bad
arguments, an unreadable file, a malformed config. It refuses to inspect nothing quietly: pass a
path that doesn't exist, or a whole newline-joined file list as one argument (what an unquoted
`$FILES` becomes in zsh, which doesn't word-split), and you get exit 2 with a diagnosis instead of a
clean bill of health. Pipe file lists through `tr '\n' '\0' | xargs -0`.

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
  "contrastive": true,
  "default_warn_patterns": true,
  "warn_patterns": [{ "pattern": "^TODO", "label": "unowned TODO" }],
  "exclude": ["**/vendor/**", "**/.terraform/**"]
}
```

| Key | Default | Meaning |
|---|---|---|
| `max_lines` | `1` | Longest allowed comment block. `2` if one line is too strict for you. |
| `max_length` | `120` | Warn above this many characters on a single comment line. |
| `contrastive` | `true` | Block road-not-taken comments. Set `false` to keep only the length rules. |
| `default_warn_patterns` | `true` | Keep the built-in banner and narration patterns. |
| `warn_patterns` | `[]` | Extra patterns, **appended** to the built-ins. Python regex, matched against the comment text with its `#` stripped. |
| `exclude` | `[]` | Glob patterns; matching paths are skipped entirely. |

JSON rather than TOML on purpose: `tomllib` landed in Python 3.11, and the hook runs under whatever
`python3` is on `PATH` — which on macOS is still 3.9.

A malformed config **warns on stderr and runs with defaults** when invoked as a hook, because a
broken config file must never wedge your agent loop. The same file makes the CLI **exit 2** with
the error, where a human is reading the output and silence would hide the mistake.

## Why a hook and not a linter rule

A comment linter in CI tells you about the problem after the agent has moved on, after you've
context-switched, and in a place where the fix costs a round trip. A hook tells the agent *while it
still has the code in mind*, and the turn doesn't end until it's resolved.

It's also why the check is deliberately dumb. A model asked to judge whether a comment is
"load-bearing" will talk itself into yes — that's exactly the rationalization the rule exists to
prevent. A regex can't be persuaded. Let the tripwire be mechanical and the resolution be
intelligent.

## Not in scope (yet)

- PyPI packaging and a `pre-commit` hook definition, so the same linter runs in CI
- Languages whose comments aren't hash- or `//`-prefixed line comments — `/* */`, JSDoc

Both are welcome as PRs.

## Development

```bash
python3 -m pytest tests -q
ruff check .
claude plugin validate . --strict
```

The version in `plugins/comment-diet/.claude-plugin/plugin.json` and the one in
`.claude-plugin/marketplace.json` must match; `--strict` is what catches a mismatch, and CI runs it.

## License

MIT.
