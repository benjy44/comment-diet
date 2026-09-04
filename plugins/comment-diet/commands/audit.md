---
description: Audit existing files for comment and doc-comment violations and fix them
argument-hint: "[path] (optional; defaults to the whole repo)"
allowed-tools: Bash, Read, Edit
---

Audit already-committed code for comment violations — multi-line comment
blocks, banner and narration comments, road-not-taken comments, and bloated
doc comments, JSDoc or docstrings — and fix them. Unlike the hooks, this looks
at whole files rather than just the current change, so use it to clean up a
codebase's existing comments.

Scope: `$ARGUMENTS` if given (a directory or file path), otherwise the whole
repository.

1. Discover the files and run the deterministic linter over them:

   ```bash
   git ls-files -- "${ARGUMENTS:-.}" \
     | grep -E '\.(tf|ya?ml|sh|py|go|rs|tsx?|jsx?|mjs)$' \
     | tr '\n' '\0' \
     | xargs -0 -r python3 "${CLAUDE_PLUGIN_ROOT}/scripts/comment_diet.py"
   ```

   Pipe the list — don't collect it into a variable and expand it. zsh does not
   word-split an unquoted `$FILES`, so `python3 comment_diet.py $FILES` passes
   the entire list as one argument. `tr`/`xargs -0` is correct in every shell
   and survives paths containing spaces. `-r` keeps an empty scope silent: BSD
   xargs already skips, but GNU xargs would run the linter with no arguments
   and print its usage hint, which describes a different failure.

   Exit codes when invoked directly: **0** clean, **1** violations found, **2**
   the linter could not run (bad arguments, unreadable file, malformed config).
   Through `xargs` any non-zero becomes **123**, so judge the run by its output
   lines, and treat a `comment-diet:` error line as a broken invocation to fix
   — never as a pass.

   Lines on stdout are hard violations. Lines on stderr prefixed `warning:` are
   banners, narration, over-long one-liners, or doc comments that are merely
   getting wordy — reconsider them, but they don't block.

2. For every violation, open the file and apply the judgment the hooks ask for:
   **reduce an ordinary comment to a single non-obvious *why* line, reduce a
   doc comment to one concise summary sentence, move the explanation to the
   README, or delete it** if it only narrates or decorates. The
   `writing-comments` skill in this plugin carries the full clause test and the
   three tiers — read it before deciding what survives.

3. Re-run the command from step 1 to confirm a clean pass, then summarise what
   you changed and what you deliberately kept (a load-bearing one-liner is
   allowed to survive).

Do not touch heredoc bodies, YAML block scalars, Go and Rust raw strings,
template literals, or `#!`/`//go:`/`checkov`/`tflint`/`eslint`/`@ts-` directive
lines — the linter already excludes them. Licence and copyright headers are
free; leave them alone. Make only comment edits; never change code behaviour.
