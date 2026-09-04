---
name: writing-comments
description: How to write a comment that earns its place — one line stating a non-obvious why, or none at all, and one concise summary sentence for a doc comment. TRIGGER when writing or editing comments, doc comments, JSDoc, rustdoc or docstrings in any source file, and whenever the comment-diet hook blocks an edit and you need to decide what survives. DO NOT TRIGGER for prose documents (README, docs, ADRs, commit messages, PR descriptions) — those are meant to be long.
allowed-tools: Read, Edit
---

# Writing comments

The default is **zero**. There are three tiers, and everything falls into one
of them.

## Tier 1 — ordinary comments: one line, or none

A comment is allowed only as a **single line** stating a non-obvious *why*
that:

- **(a)** isn't visible in the code,
- **(b)** isn't generic language/framework/platform behaviour a reader can look
  up, and
- **(c)** isn't already written in a README, rule, or `CLAUDE.md`.

If the *why* needs more than one line — or more than ~120 characters on that
one line — it belongs in the README. Don't dodge the one-line rule by cramming
a paragraph onto a single long line.

In a block whose sibling entries are bare, a new entry gets none either. **When
unsure, delete.**

## Tier 2 — doc comments: one concise summary sentence

Go doc comments, JSDoc, Rust doc comments (`///`, `//!`, `/** */`, `/*! */`) and
Python docstrings are **not exempt**. They exist for godoc, rustdoc, IDE hover
and the linters, so they may exist — but the tooling needs a summary, not an
essay. godoc's package index uses only the first sentence, rustdoc's item tables
show only the first paragraph, and `revive`'s `exported` rule sets no length at
all. Everything past that first sentence is padding nobody reads.

**The budget is 200 characters of prose across the whole comment, and 200 is a
ceiling you should rarely approach — not a target.** Past 120 characters you
are already being wordy. Aim for one sentence that names the thing and says
what it is for.

These are banned outright, at any length:

- **A second paragraph** — a blank `//` or `*` line inside the comment.
- **Lists** — bullets or numbered items. A list belongs in the README.
- **Section headers that restate the signature** — `Args:`, `Parameters:`,
  `Returns:`, `Throws:`, `Example:`, `Usage:`, `Notes:`, numpy-style
  underlines, and rustdoc's `# Arguments` and `# Returns`.
- **`@param` / `@returns` / `@type` in TypeScript and Rust** — the signature is
  already typed. They are allowed in plain `.js`, where they carry the only
  type information there is.
- **Filler openers** — `This function…`, `This method…`, `This type…`,
  `This class…`, `This package…`, `This file…`, `Helper function…`,
  `Utility function…`. Start with the identifier's name instead.

**Rustdoc's sections are the exception.** `# Safety`, `# Errors`, `# Panics`
and `# Examples` each say what a signature cannot, and clippy asks for the
first three (`missing_safety_doc` is warn-by-default), so each is allowed as
its own paragraph — one paragraph, no lists, the same character budget. Don't
put `# Safety` on a safe `fn`: clippy's `unnecessary_safety_doc` flags that,
and so does the hook.

**Write the doctest.** A fenced block is code `cargo test` runs, not prose, so
it is never counted — length, contents and all. Never delete a doctest to get
past this hook; that trades a test for nothing.

When you delete a doc comment, delete its `///` markers too — a bare `///`
trips `clippy::empty_docs`.

## Tier 3 — licence lines: free

`Copyright`, `SPDX-License-Identifier:`, `Licensed under`, `All rights
reserved`, `@license`, and MIT/Apache/BSD boilerplate are uncounted. Nothing
else in a file header is. A licence header passes; a licence header with
`// This file contains the HTTP handlers…` bolted onto it does not.

## The clause test

**Test every clause, not the whole comment.** A comment can be half
load-bearing and half filler and still *feel* justified. Keep only the clauses
that carry non-obvious *why*, and delete each clause that:

- **restates a value or name in the code below** — `# runs in log-archive`
  above `account_id = "…log-archive…"`;
- **restates the signature** — `takes a path and returns a Config` when the
  signature says exactly that;
- **names something the reader can discover** — a file, action, symbol, or rule
  they can grep, or generic language/framework/cloud behaviour they can look
  up. Don't teach the platform;
- **narrates migration provenance** — that a value was frozen from a retired
  system, that a resource was imported, or how the old code shaped it. Code
  describes what *is*, not what it used to be;
- **narrates the road not taken** — what the code does *not* do, avoids, or
  prevents, and the bad thing it dodges. A comment defending the choice against
  the rejected alternative belongs in the README if it's load-bearing at all;
- **repeats rationale already written elsewhere** — point to it, don't
  reproduce it.

Comments that legitimately survive: a linter-suppression justification
(`checkov:skip`, `tflint-ignore`, `nolint`, `noqa`), a trust or security
rationale, a non-obvious platform constraint, a workaround for a named upstream
bug. Put shared rationale in one place and leave each site a pointer at most.

## Examples

```go
// BAD — filler opener, and an essay where a sentence belongs
// This function is responsible for parsing the configuration file.
//
// It reads the file from disk, unmarshals the YAML, applies defaults,
// and returns the resulting Config struct along with any error.
func ParseConfig(path string) (*Config, error) { ... }

// OK — names the identifier, one sentence, non-obvious constraint included
// ParseConfig reads path and applies defaults; a missing file is not an error.
func ParseConfig(path string) (*Config, error) { ... }

// BAD — file header narrating the file's contents
// Copyright 2026 Example Ltd.
// This file contains the HTTP handlers for the billing service.

// OK — licence only
// Copyright 2026 Example Ltd.
// SPDX-License-Identifier: MIT
```

```typescript
/**
 * BAD — @param/@returns duplicate the types, and it runs to a second paragraph
 * Parses the config.
 *
 * @param path - the path to the config file
 * @returns the parsed config
 */
export function parseConfig(path: string): Config { ... }

/** OK — one sentence, says the thing the types can't */
export function parseConfig(path: string): Config { ... }
```

```python
# BAD — Google-style sections restating a typed signature
def parse_config(path: str) -> Config:
    """Read the config.

    Args:
        path: the path to the config file.
    Returns:
        The parsed config.
    """

# OK
def parse_config(path: str) -> Config:
    """Read path, applying defaults; a missing file is not an error."""
```

````rust
// BAD — an ordinary comment, so Tier 1 applies: `//` above an item is not a
// doc comment in Rust, however much it reads like one.
pub struct Client { ... }

// BAD — `# Arguments` restates the signature, and the summary runs on into a
// second paragraph of prose
/// Parses the config.
///
/// It reads the file, applies defaults and returns the Config.
///
/// # Arguments
///
/// * `path` - the path to the config file
pub fn parse_config(path: &Path) -> io::Result<Config> { ... }

// OK — one summary sentence, the section clippy asks for, and a doctest
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

// OK — the justification an unsafe block owes the reader, on one line
// SAFETY: ptr came from Box::into_raw and is never aliased.
unsafe { drop(Box::from_raw(ptr)) };
````

```hcl
# BAD — narration
# create the bucket
resource "aws_s3_bucket" "x" { bucket = "..." }

# BAD — road not taken (do X, not Y, so the bad thing never happens)
# Point at the file, not the dir, so the build never sweeps in __pycache__
source = "./main.tf.json"

# OK — one line, non-obvious project why, documented nowhere else
# CT owns the source bucket; replication attaches by name (TF needn't own it).
resource "aws_s3_bucket_replication_configuration" "x" { ... }
```

```bash
# BAD — narrates the obvious
# exit if the file is missing
[ -f "$f" ] || exit 1

# OK — non-obvious platform behaviour
# BSD sed needs the empty -i argument; GNU sed rejects it.
sed -i '' 's/a/b/' "$f"
```

## Rationalizations that don't fly

| Excuse | Reality |
|---|---|
| "It's a doc comment, so the length rule doesn't apply" | It applies. 200 characters, and you should be well under it. |
| "Go/revive requires a doc comment here" | It requires one to *exist*, and sets no length. One sentence satisfies it. |
| "The budget is 200, so I have room" | 200 is the ceiling, not the target. Past 120 you're padding. |
| "This entry is non-obvious, a brief comment is warranted" | If sibling entries are bare, the new one is too. |
| "Keep the old value as a reference" | Dead code you touch gets deleted, not commented around. |
| "I'll do the comment pass after it works" | Lean is how it's written, not a follow-up nobody asks for twice. |
| "The hook is being pedantic here" | The hook is a tripwire, not a judge. It hands you the decision — make it honestly, don't reword the comment to slip past the regex. |

## When the hook blocks you

The block reason lists each offending block or line. For each one, choose — and
say which you chose:

1. **Keep one line** — the *why* survives the clause test and fits in one line
   (or, for a doc comment, one concise summary sentence).
2. **Move it to the README** — it's load-bearing but needs room.
3. **Delete it** — it narrates, decorates, or repeats what's already written.

Never restructure the comment purely to dodge the pattern. If the explanation
matters, it belongs in the README; if it doesn't, it belongs nowhere.
