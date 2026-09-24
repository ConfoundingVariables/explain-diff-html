# explain-diff-html (fork)

Fork of [malav2110/explain-diff-html](https://github.com/malav2110/explain-diff-html) — an agent skill that turns a diff, branch, or PR into one self-contained HTML explanation page; docs, samples, and rationale live upstream.
This fork replaces `html-template.html` with `render.py`: a run writes a JSON spec (content only) and renders it, the renderer validates and enforces the output contract, and the skill is user-invoked only (`disable-model-invocation: true`, needs `python` 3.8+).
Diff against upstream: `git diff upstream/main...main`. MIT; credits and origin upstream.
