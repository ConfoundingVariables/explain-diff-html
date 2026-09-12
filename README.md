# Explain Diff (HTML)

A Claude Code skill that turns a code change into one self-contained HTML page
that teaches a reader what changed and why.

Point it at a pull request, a branch, or a commit range. It reads the diff, then
reads the code around the diff, then writes a single page with four sections:

- Background, on the system the change lands in, with the beginner-level part
  collapsed so a familiar reader can skip it.
- Intuition, on the core idea, with toy data and diagrams rather than full
  detail.
- Code walkthrough, ordered by the path a request or an action takes through the
  system, not by filename.
- Quiz, five interactive multiple-choice questions that test whether the reader
  understood why the change is shaped the way it is.

The output is one HTML file with the CSS and JavaScript inline. It opens with a
double click, reads on a phone, and follows the reader's light or dark system
theme. Nothing needs a server, a build step, or a network round trip, with one
exception: a page carrying a Mermaid diagram fetches the Mermaid library from a
CDN, so that page needs network for its diagrams to draw. Everything else on it,
including the other diagrams and the quiz, still works offline.

This is a teaching artifact, not a review. It explains a change; it does not
judge it or propose fixes.

## Samples

Open these in a browser to see what the skill produces before installing it.
Seven samples across three languages, each explaining a merged pull request in
a public repository, filed under `samples/` by the repository it came from.

| Page                                                                    | Repository                 | Pull request                                                 | What it teaches                                                                                     |
| ----------------------------------------------------------------------- | -------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| [PR 11305](samples/tanstack-query/2026-09-01-pr-11305-explanation.html) | TanStack/query, TypeScript | [11305](https://github.com/TanStack/query/pull/11305)        | A `?.field` guard answering two questions at once, so falsy errors never reached the error boundary |
| [PR 11242](samples/tanstack-query/2026-09-01-pr-11242-explanation.html) | TanStack/query, TypeScript | [11242](https://github.com/TanStack/query/pull/11242)        | A guard that reset only on the happy path, and why the fix uses `finally` with no `catch`           |
| [PR 16102](samples/fastapi/2026-09-01-pr-16102-explanation.html)        | fastapi/fastapi, Python    | [16102](https://github.com/fastapi/fastapi/pull/16102)       | A three-valued option collapsed at the public boundary, and the stack depth a warning depends on    |
| [PR 16013](samples/fastapi/2026-09-01-pr-16013-explanation.html)        | fastapi/fastapi, Python    | [16013](https://github.com/fastapi/fastapi/pull/16013)       | Double-checked locking and build-then-publish, and why the list is assigned before the version      |
| [PR 2924](samples/uportal/2026-09-01-pr-2924-explanation.html)          | uPortal, Java              | [2924](https://github.com/uPortal-Project/uPortal/pull/2924) | A catch that logs and falls through, and an `@Ignore` that had been skipping 30 tests               |
| [PR 2945](samples/uportal/2026-09-01-pr-2945-explanation.html)          | uPortal, Java              | [2945](https://github.com/uPortal-Project/uPortal/pull/2945) | Picking the type that matches the intent, so a static-analysis suppression stops being needed       |
| [PR 2983](samples/uportal/2026-09-01-pr-2983-explanation.html)          | uPortal, Java              | [2983](https://github.com/uPortal-Project/uPortal/pull/2983) | An implicit path attribute made explicit, moving resolution from the server to the browser          |

Each page was checked two ways before it shipped: a read-only pass that
re-opened every cited `file:line` at the pull request head and tried to
falsify each claim, and a cold read of the prose against the writing rules in
`SKILL.md`. Between them they caught wrong line numbers, miscounts, claims the
checkout could not support, and one diagram in the wrong family.

## Requirements

| Tool   | Needed when                              | Used for                                               |
| ------ | ---------------------------------------- | ------------------------------------------------------ |
| `git`  | Every run                                | Resolving the base, fetching the ref, reading the diff |
| `gh`   | Explaining a pull request                | Fetching the pull request title, body, and URL         |
| `node` | Every run that carries a Mermaid diagram | Running the Mermaid validator through `npx`            |

`gh` must be authenticated, not only installed. Check with `gh auth status`.

Node is a build-time validator only. Nobody needs Node to open a finished page,
because the reader's browser loads Mermaid from the CDN.

The skill's commands are POSIX shell, so it runs on Linux and macOS directly,
and on Windows through WSL or Git Bash. Windows PowerShell and `cmd.exe` are not
supported: they have no `command -v`, no `$(...)` substitution, and none of
`mktemp`, `sed`, or `openssl`. The generated page itself is plain HTML and opens
in any browser on any platform.

## Install

The repository root is the skill, so cloning it into place is the whole install.

For every project you work on:

```bash
git clone https://github.com/malav2110/explain-diff-html.git \
  ~/.claude/skills/explain-diff-html
```

For one project only, committed alongside the code so your team gets it too:

```bash
git clone https://github.com/malav2110/explain-diff-html.git \
  <your-repo>/.claude/skills/explain-diff-html
```

Claude Code reads `SKILL.md`. The `README.md` and `samples/` directory sit in
the same folder and are ignored, so nothing needs moving or deleting.

Confirm the install by asking Claude Code to list its skills, or by running
`/skill-doctor` if your version has it. `explain-diff-html` should appear with
its description.

## Use

Ask in plain language. The skill triggers on phrasing like this:

```
explain PR 1234
explain this diff
walk me through this branch
explain the changes between abc123 and def456
```

It writes the page to a `code-explanations` folder in your home directory,
`$HOME/code-explanations`, named
`YYYY-MM-DD-<KEY>-explanation.html`, and reports the path. The date comes first
so the files sort by time, and the key comes second so you can grep for a ticket
or a pull request later. `<KEY>` is an issue key such as `PROJ-1234` when the
branch name carries one, otherwise `pr-1234`, otherwise a short slug.

Output lands outside the repository on purpose. An explanation is not a project
artifact, and writing it into the working tree invites committing it by accident.

## What it is deliberately not

- Not a code review. It does not flag bugs, rank severity, or suggest changes.
- Not a summary. A summary tells you what moved. This explains why the change
  is shaped the way it is, which is the part a diff cannot tell you.
- Not a living document. Each page is a snapshot of one change at one ref. When
  the code moves on, generate a new page rather than editing the old one.

## How it works

`SKILL.md` drives Claude Code through eight steps. In outline:

1. Resolve the target and the filename key, detecting the repository's default
   branch rather than assuming `main`.
2. Gather context: the code around the diff, the pull request body, the commit
   messages, and any design records the repository keeps.
3. Draft the four sections, walking the code in flow order.
4. Build the diagrams, from three dependency-free HTML and CSS families plus
   Mermaid for state, entity-relationship, and sequence shapes.
5. Write the quiz to the question shapes that test transfer rather than recall.
6. Hand the prose to a fresh reader for an editing pass, because an author
   misses its own tells.
7. Run the self-check, including re-reading every cited `file:line` at the
   target ref.
8. Write the file.

Two of those steps exist because of specific failures worth knowing about. Step
7 checks that every code block is HTML-escaped, because a single raw `<` in a
pasted diff line opens an element HTML never closes, which swallows the rest of
the document and breaks every anchor below it. Step 7 also re-reads each cited
line at the pull request head, because a stale ref produces line numbers that
look right and point at nothing.

## Customizing

Everything visual lives in `html-template.html`, which the skill fills in rather
than rebuilding per run:

- Colors are CSS custom properties at the top, in a light set and a dark set.
  Change the two blocks to match your own palette.
- The three hand-built diagram families are plain markup: a simplified UI
  mockup, a data-flow diagram with example payloads on the arrows, and a node
  tree for recursive structures.
- The Mermaid loader pins an exact version and checks it with a Subresource
  Integrity hash. To change versions, edit the `@x.y.z` in the `src` and
  recompute the hash. `SKILL.md` carries the command. A stale hash makes the
  browser block the script and the diagrams then fail silently.
- The output directory and the filename pattern are in `SKILL.md`, under the
  output contract.

## License

MIT. See [LICENSE](LICENSE).
