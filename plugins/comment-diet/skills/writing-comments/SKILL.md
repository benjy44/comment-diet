---
name: writing-comments
description: How to write a comment that earns its place — one line stating a non-obvious why, or none at all. TRIGGER when writing or editing comments in any source file, and whenever the comment-diet hook blocks an edit and you need to decide what survives. DO NOT TRIGGER for prose documents (README, docs, ADRs, commit messages, PR descriptions) — those are meant to be long.
allowed-tools: Read, Edit
---

# Writing comments

The default is **zero**. A comment is allowed only as a **single line** stating a non-obvious *why*
that:

- **(a)** isn't visible in the code,
- **(b)** isn't generic language/framework/platform behaviour a reader can look up, and
- **(c)** isn't already written in a README, rule, or `CLAUDE.md`.

If the *why* needs more than one line — or more than ~120 characters on that one line — it belongs
in the README. Don't dodge the one-line rule by cramming a paragraph onto a single long line.

In a block whose sibling entries are bare, a new entry gets none either. **When unsure, delete.**

## The clause test

**Test every clause, not the whole comment.** A comment can be half load-bearing and half filler and
still *feel* justified. Keep only the clauses that carry non-obvious *why*, and delete each clause
that:

- **restates a value or name in the code below** — `# runs in log-archive` above
  `account_id = "…log-archive…"`;
- **names something the reader can discover** — a file, action, symbol, or rule they can grep, or
  generic language/framework/cloud behaviour they can look up. Don't teach the platform;
- **narrates migration provenance** — that a value was frozen from a retired system, that a resource
  was imported, or how the old code shaped it. Code describes what *is*, not what it used to be. If
  the migration context matters it goes in the README;
- **narrates the road not taken** — what the code does *not* do, avoids, or prevents, and the bad
  thing it dodges. Code states what *is*; a comment defending the choice against the rejected
  alternative belongs in the README if it's load-bearing at all;
- **repeats rationale already written elsewhere** — point to it, don't reproduce it.

The result is one line, or none — never a paragraph.

Comments that legitimately survive: a linter-suppression justification (`checkov:skip`,
`tflint-ignore`, `noqa`), a trust or security rationale, a non-obvious platform constraint, a
workaround for a named upstream bug. Put shared rationale in one place and leave each site a
pointer at most.

## Examples

```hcl
# BAD — narration
# create the bucket
resource "aws_s3_bucket" "x" { bucket = "..." }

# BAD — restates the constraint already in the code
# block public access
block_public_access = "BlockAll"

# BAD — file-inventory header narrating what the resources below are
# Findings bucket plus the cross-account replication wiring.
module "findings" { ... }

# BAD — migration provenance; belongs in the README if anywhere
# Frozen /20s from the retired registry, cross-checked against live VPCs
cidr_allocations = { ... }

# BAD — road not taken (do X, not Y, so the bad thing never happens)
# Point at the file, not the dir, so the build never sweeps in __pycache__
source = "./main.tf.json"

# OK — one line, non-obvious project why, documented nowhere else
# CT owns the source bucket; replication attaches by name (TF needn't own it).
resource "aws_s3_bucket_replication_configuration" "x" { ... }
```

```python
# BAD — banner
# ---------- helpers ----------

# BAD — narrates what the code does
# loop over the users and send each one an email
for user in users: ...

# BAD — teaches the language
# dict comprehension builds a lookup keyed by id
by_id = {u.id: u for u in users}

# OK — non-obvious why, unlookupable
# The vendor API 500s on batches over 50, despite documenting 200.
for chunk in chunked(users, 50): ...
```

```yaml
# BAD — restates the key below
# set the timeout to 30 seconds
timeout: 30

# OK — a constraint the reader can't derive
# Runner images cache pip under /opt, which the sandbox mounts read-only.
env: { PIP_CACHE_DIR: /tmp/pip }
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
| "This entry is non-obvious, a brief comment is warranted" | If sibling entries are bare, the new one is too. Rationale lives in the doc, not the site. |
| "Keep the old value as a reference" | Dead code you touch gets deleted, not commented around. |
| "A literal with a comment explaining the gap is fine for now" | The excuse-comment is the smell. Fix the source — a module, a constant, a convention. |
| "I'll do the comment pass after it works" | Lean is how it's written, not a follow-up step nobody asks for twice. |
| "The hook is being pedantic here" | The hook is a tripwire, not a judge. It hands you the decision — make it honestly, don't reword the comment to slip past the regex. |

## When the hook blocks you

The block reason lists each offending block or line. For each one, choose — and say which you chose:

1. **Keep one line** — the *why* survives the clause test and fits in one line.
2. **Move it to the README** — it's load-bearing but needs room.
3. **Delete it** — it narrates, decorates, or repeats what's already written.

Never restructure the comment purely to dodge the pattern. If the explanation matters, it belongs in
the README; if it doesn't, it belongs nowhere.
