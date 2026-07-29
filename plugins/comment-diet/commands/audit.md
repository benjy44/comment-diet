---
description: Audit existing .tf/.yml/.yaml/.sh/.py files for comment violations and fix them
argument-hint: "[path] (optional; defaults to the whole repo)"
allowed-tools: Bash, Read, Edit
---

Audit already-committed code for comment violations (multi-line comment blocks, banner and
narration comments, road-not-taken comments) and fix them. Unlike the hooks, this looks at whole
files rather than just the current change — use it to clean up a codebase's existing comments.

Scope: `$ARGUMENTS` if given (a directory or file path), otherwise the whole repository.

1. Discover the files and run the deterministic linter over them:

   ```bash
   FILES=$(git ls-files -- ${ARGUMENTS:-.} | grep -E '\.(tf|ya?ml|sh|py)$')
   [ -n "$FILES" ] && python3 "${CLAUDE_PLUGIN_ROOT}/scripts/comment_diet.py" $FILES
   ```

   Each `path:start-end: comment block longer than N line(s)` line is a hard violation, as is any
   `comment narrates the road not taken`; each `warning: path:line: comment ...` is a banner,
   narration, or over-long one-liner to reconsider.

2. For every violation, open the file and apply the same judgment the hooks ask for: **reduce the
   block to a single non-obvious *why* line, move the explanation to the README, or delete it** if
   it only narrates or decorates. The `writing-comments` skill in this plugin carries the full
   clause test — read it before deciding what survives. Don't reproduce rationale the code or a doc
   already carries.

3. Re-run the command from step 1 to confirm a clean pass, then summarise what you changed and what
   you deliberately kept (a load-bearing one-liner is allowed to survive).

Do not touch heredoc/YAML block-scalar bodies or `#!`/checkov/tflint directive lines — the linter
already excludes them. Make only comment edits; never change code behaviour.
