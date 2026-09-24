#!/usr/bin/env python3
r"""
render.py — render an explain-diff content spec into the self-contained HTML
page this skill produces.

Why this exists: the CSS, the quiz script, the Mermaid loader, and the page
scaffolding are identical across every invocation of the skill — only the
content (prose, diagrams, quiz questions) changes per diff. Rebuilding that
scaffold by hand every run wastes tokens and drifts. This script takes a small
JSON spec with just the content, validates it against the skill's output
contract, and writes the finished page.

The spec-and-render shape is adapted from Geoffrey Litt's explain-diff gist
(https://gist.github.com/geoffreylitt/a29df1b5f9865506e8952488eac3d524). The
page scaffold — layout, colors, diagram families, quiz interaction, Mermaid
loader — is ported verbatim from this repository's html-template.html, which
this renderer replaces.

Usage:
    python render.py spec.json [-o output.html]

If -o is omitted, writes to
    $HOME/code-explanations/YYYY-MM-DD-<KEY>-explanation.html
(matching the skill's output contract), where <KEY> comes from the spec's
"key" field and the date is today. The directory is created if missing. The
path of the written page is printed; report it as printed.

-o writes to an explicit path instead. It is an escape hatch for uses the
output contract does not cover, such as regenerating this repository's
samples; the skill's own workflow never passes it.

Spec format (JSON):

{
  "title": "One-line change title",
  "lead": "One-sentence summary of what the change does.",
  "provenance": "owner/repo PR 1234 at abc1234, explained 2026-09-01",
  "key": "pr-1234",
  "sections": [
    {"id": "background", "heading": "Background", "html": "<p>...</p>"},
    {"id": "intuition", "heading": "Intuition", "html": "<p>...</p>"},
    {"id": "code", "heading": "Code walkthrough", "html": "<pre>...</pre>"}
  ],
  "quiz": [
    {
      "question": "Why is the change shaped this way?",
      "options": [
        {"text": "The alternative a competent engineer would consider.", "correct": false},
        {"text": "The actual reason.", "correct": true},
        {"text": "Another plausible misunderstanding.", "correct": false}
      ],
      "feedback": "Why the correct answer is right, in the reader's terms."
    }
  ]
}

Field rules:

- Required: title, lead, provenance, key, sections, quiz. Unknown top-level
  fields are rejected, so a typo cannot silently drop content.
- "key" becomes the filename piece: letters, digits, dots, underscores, and
  hyphens only, and it must not start with a dot or hyphen, end in a dot, or
  be a Windows-reserved device name (CON, NUL, PRN, COM1-9, LPT1-9).
- sections must carry the "background", "intuition", and "code" ids, in that
  order; extra sections are allowed between and after them. Ids are unique,
  lowercase, hyphenated.
- The quiz carries exactly five questions, per the output contract. Each
  question needs 2-8 options with exactly one marked "correct",
  and non-empty "feedback" that explains why the correct answer is right.
- The option order you write is the order in the raw HTML. The page script
  shuffles options in the reader's browser on every load, so position is
  random for the reader either way; vary the correct option's position per
  question anyway, per the skill's quiz rules.
- "sections[].html" and "quiz[].feedback" are raw HTML: real markup, with
  code and Mermaid sources HTML-escaped exactly as SKILL.md step 3 and step 4
  demand. Every other field is plain text; the renderer escapes it.
- Mermaid diagrams are `<pre class="mermaid">` blocks inside section html,
  validated before they go into the spec. The loader the renderer writes is
  a no-op when the page carries none.
"""
import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path

CSS = r"""
      :root {
        --bg: #ffffff;
        --surface: #f6f7f9;
        --text: #1c2024;
        --muted: #60646c;
        --border: #d7dbdf;
        --border-strong: #848c95;
        --accent: #2f5ee0;
        --accent-soft: #e8eefc;
        --edge: #a35608;
        --edge-soft: #fbefe1;
        --ok: #1a7f47;
        --ok-soft: #e4f3ea;
        --bad: #c62a3b;
        --bad-soft: #fbe7e9;
        --measure: 68ch;
      }
      @media (prefers-color-scheme: dark) {
        :root {
          --bg: #16181b;
          --surface: #1f2226;
          --text: #eceef0;
          --muted: #9ba1a6;
          --border: #33383d;
          --border-strong: #646c75;
          --accent: #7aa2ff;
          --accent-soft: #1e2740;
          --edge: #e08c3a;
          --edge-soft: #2e2517;
          --ok: #57c98b;
          --ok-soft: #17281d;
          --bad: #f07178;
          --bad-soft: #2c1a1c;
        }
      }
      * {
        box-sizing: border-box;
      }
      html {
        scroll-behavior: smooth;
      }
      body {
        margin: 0;
        background: var(--bg);
        color: var(--text);
        font:
          17px/1.65 -apple-system,
          BlinkMacSystemFont,
          "Segoe UI",
          Roboto,
          Helvetica,
          Arial,
          sans-serif;
      }
      a {
        color: var(--accent);
      }
      a:visited {
        color: var(--accent);
      }
      .layout {
        display: grid;
        grid-template-columns: 220px minmax(0, 1fr);
        gap: 2.5rem;
        max-width: 1080px;
        margin: 0 auto;
        padding: 2.5rem 1.5rem 6rem;
      }
      nav.toc {
        position: sticky;
        top: 2.5rem;
        align-self: start;
        font-size: 0.9rem;
      }
      nav.toc strong {
        display: block;
        font-size: 0.72rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
        margin-bottom: 0.6rem;
      }
      nav.toc ol {
        list-style: none;
        margin: 0;
        padding: 0;
      }
      nav.toc li {
        margin: 0.35rem 0;
      }
      nav.toc a {
        color: var(--muted);
        text-decoration: none;
      }
      nav.toc a:hover {
        color: var(--accent);
      }
      main {
        min-width: 0;
      }
      main > header {
        border-bottom: 1px solid var(--border);
        padding-bottom: 1.25rem;
        margin-bottom: 2rem;
      }
      main > header h1 {
        font-size: 1.9rem;
        line-height: 1.2;
        margin: 0 0 0.6rem;
      }
      main > header .lead {
        color: var(--muted);
        margin: 0;
        max-width: var(--measure);
      }
      main > header .provenance {
        color: var(--muted);
        font-family: ui-monospace, monospace;
        font-size: 0.76rem;
        margin: 0.7rem 0 0;
      }
      .colophon {
        grid-column: 1 / -1;
        color: var(--muted);
        font-family: ui-monospace, monospace;
        font-size: 0.76rem;
        border-top: 1px solid var(--border);
        margin: 4rem 0 0;
        padding: 1.2rem 0 0;
      }
      .colophon a {
        color: inherit;
      }
      section {
        margin-bottom: 3.5rem;
      }
      section h2 {
        font-size: 1.4rem;
        margin: 0 0 1rem;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid var(--border);
      }
      section h3 {
        font-size: 1.05rem;
        margin: 2rem 0 0.6rem;
      }
      section p,
      section ul,
      section ol {
        max-width: var(--measure);
      }
      li {
        margin: 0.3rem 0;
      }
      /* Code blocks: white-space set here so a filled-in block cannot collapse. */
      pre,
      .code-block {
        white-space: pre-wrap;
        overflow-x: auto;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 0.9rem 1.1rem;
        font:
          0.86rem/1.55 ui-monospace,
          SFMono-Regular,
          Menlo,
          Consolas,
          monospace;
        tab-size: 2;
      }
      pre .del {
        color: var(--bad);
      }
      pre .add {
        color: var(--ok);
      }
      pre .hi {
        background: var(--accent-soft);
        border-radius: 3px;
      }
      code {
        font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        font-size: 0.9em;
        background: var(--surface);
        padding: 0.05rem 0.3rem;
        border-radius: 4px;
        overflow-wrap: anywhere;
      }
      /* Path label for the code block below it. */
      .filename {
        font-size: 0.78rem;
        color: var(--muted);
        font-family: ui-monospace, monospace;
        margin: 1.5rem 0 0.3rem;
        overflow-wrap: anywhere;
      }
      /* Comparison table: one row per case, .yes / .no / .warn on outcome cells. */
      table.vals {
        border-collapse: collapse;
        margin: 1.5rem 0;
        font-size: 0.86rem;
        width: 100%;
        max-width: 620px;
      }
      table.vals th,
      table.vals td {
        border: 1px solid var(--border-strong);
        padding: 0.4rem 0.65rem;
        text-align: left;
      }
      table.vals th {
        background: var(--surface);
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        color: var(--muted);
      }
      table.vals td.yes {
        background: var(--ok-soft);
      }
      table.vals td.no {
        background: var(--bad-soft);
      }
      table.vals td.warn {
        background: var(--edge-soft);
      }
      /* Callouts: .callout for a concept, .callout.edge for a caveat. */
      .callout {
        background: var(--accent-soft);
        border-left: 3px solid var(--accent);
        border-radius: 0 6px 6px 0;
        padding: 0.85rem 1.1rem;
        margin: 1.5rem 0;
        max-width: var(--measure);
      }
      .callout .label {
        display: block;
        font-size: 0.7rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--accent);
        font-weight: 700;
        margin-bottom: 0.3rem;
      }
      .callout.edge {
        background: var(--edge-soft);
        border-left-color: var(--edge);
      }
      .callout.edge .label {
        color: var(--edge);
      }
      /* Skippable deep-background block. */
      details.skippable {
        border: 1px solid var(--border-strong);
        border-radius: 8px;
        padding: 0.75rem 1.1rem;
        margin: 1.25rem 0;
      }
      details.skippable > summary {
        cursor: pointer;
        font-weight: 600;
        font-size: 0.92rem;
        color: var(--muted);
      }
      details.skippable[open] > summary {
        margin-bottom: 0.75rem;
      }
      /* Diagram family 1: simplified app UI mockup. */
      .ui-mockup {
        border: 1px solid var(--border-strong);
        border-radius: 10px;
        overflow: hidden;
        margin: 1.5rem 0;
        max-width: 560px;
        font-size: 0.85rem;
      }
      .ui-mockup .bar {
        background: var(--surface);
        border-bottom: 1px solid var(--border);
        padding: 0.5rem 0.85rem;
        font-weight: 600;
        font-size: 0.78rem;
        color: var(--muted);
      }
      .ui-mockup .body {
        padding: 1.1rem 0.85rem;
        font-family: ui-monospace, monospace;
        font-size: 0.78rem;
        white-space: pre-wrap;
      }
      .mock-caption {
        font-size: 0.78rem;
        color: var(--muted);
        margin: 0.3rem 0 0;
        max-width: var(--measure);
      }
      /* Diagram family 2: data flow between components, example data on the arrows. */
      .dataflow {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.5rem;
        margin: 1.5rem 0;
      }
      /* Each arrow travels with the node it points at. Without this, a flow
         wider than the column wraps between an arrow and its node, leaving the
         arrow pointing at nothing and the node stranded on the next line. */
      .dataflow .step {
        display: flex;
        align-items: center;
        gap: 0.5rem;
      }
      .dataflow .node {
        background: var(--accent-soft);
        border: 1px solid var(--accent);
        color: var(--text);
        border-radius: 8px;
        padding: 0.6rem 0.9rem;
        font-size: 0.85rem;
        text-align: center;
        max-width: 175px;
      }
      .dataflow .node.terminal {
        background: var(--surface);
        border-color: var(--border);
      }
      .dataflow .node.pass {
        background: var(--ok-soft);
        border-color: var(--ok);
      }
      .dataflow .node.fail {
        background: var(--bad-soft);
        border-color: var(--bad);
      }
      .dataflow .arrow {
        display: flex;
        flex-direction: column;
        align-items: center;
        color: var(--muted);
        font-size: 0.72rem;
        min-width: 96px;
      }
      .dataflow .arrow .line {
        width: 100%;
        border-top: 2px solid var(--border);
        position: relative;
      }
      .dataflow .arrow .line::after {
        content: "\25B6";
        position: absolute;
        right: -2px;
        top: -0.72em;
        color: var(--border);
        font-size: 0.7rem;
      }
      .dataflow .arrow .data {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 5px;
        padding: 0.05rem 0.35rem;
        margin-bottom: 0.2rem;
        font-family: ui-monospace, monospace;
      }
      .flow-label {
        font-size: 0.8rem;
        color: var(--muted);
        font-weight: 600;
        margin: 1.25rem 0 0.25rem;
      }
      /* A numbered sequence with one marked position: call stacks, retry
         counts, any ranked list. Not one of the numbered families; reach for
         it when a step in an ordered list is the point. */
      .frames {
        list-style: none;
        padding: 0;
        margin: 1.25rem 0;
        max-width: 620px;
        font-family: ui-monospace, monospace;
        font-size: 0.82rem;
      }
      .frames li {
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 0.45rem 0.7rem;
        margin: 0.3rem 0;
        background: var(--surface);
      }
      .frames li.target {
        background: var(--ok-soft);
        border-color: var(--ok);
      }
      .frames .n {
        display: inline-block;
        min-width: 2.2em;
        color: var(--muted);
      }
      /* Diagram family 3: node/recursion tree (ASTs, nesting, recursion) */
      .tree {
        margin: 1.5rem 0;
        font:
          0.82rem/1.5 ui-monospace,
          SFMono-Regular,
          Menlo,
          Consolas,
          monospace;
      }
      .tnode {
        border: 1px solid var(--border);
        border-radius: 6px;
        padding: 0.3rem 0.55rem;
        margin: 0.3rem 0;
        background: var(--surface);
        display: inline-block;
      }
      .tnode.leaf {
        background: var(--bg);
      }
      .tnode.kept {
        border-color: var(--ok);
        background: var(--ok-soft);
      }
      .tnode.skipped {
        border-color: var(--muted);
        color: var(--muted);
      }
      .tchildren {
        margin-left: 1.4rem;
        border-left: 2px dotted var(--border);
        padding-left: 0.9rem;
      }
      .tnote {
        color: var(--muted);
        font-size: 0.75rem;
        margin-left: 0.4rem;
      }

      /* Optional tabular body for .ui-mockup, when the mocked UI is a table. */
      .mock-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.82rem;
      }
      .mock-table th,
      .mock-table td {
        border: 1px solid var(--border);
        padding: 0.35rem 0.5rem;
        text-align: left;
      }
      .mock-table th {
        background: var(--surface);
        font-weight: 600;
      }
      .mock-table .col-highlight {
        background: var(--accent-soft);
      }

      .mermaid {
        margin: 1.75rem 0;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 1rem;
        overflow-x: auto;
        white-space: pre;
        font-family: ui-monospace, monospace;
        font-size: 0.8rem;
        color: var(--muted);
      }
      .mermaid .edgeLabel,
      .mermaid .edgeLabel p,
      .mermaid .edgeLabel span,
      .mermaid .edgeLabel foreignObject div {
        background: var(--surface) !important;
        color: var(--text) !important;
      }
      /* Quiz */
      .quiz-question {
        border: 1px solid var(--border-strong);
        border-radius: 10px;
        padding: 1.1rem 1.25rem;
        margin: 1.5rem 0;
        max-width: var(--measure);
      }
      .quiz-question > p.q {
        font-weight: 600;
        margin: 0 0 0.85rem;
      }
      .quiz-option {
        display: block;
        width: 100%;
        text-align: left;
        background: var(--bg);
        color: var(--text);
        border: 1px solid var(--border);
        border-radius: 7px;
        padding: 0.6rem 0.8rem;
        margin-bottom: 0.5rem;
        font: inherit;
        font-size: 0.92rem;
        cursor: pointer;
      }
      .quiz-option:hover:not(:disabled) {
        border-color: var(--accent);
      }
      .quiz-option.correct {
        background: var(--ok-soft);
        border-color: var(--ok);
      }
      .quiz-option.incorrect {
        background: var(--bad-soft);
        border-color: var(--bad);
      }
      .quiz-option:disabled {
        cursor: default;
      }
      .quiz-feedback {
        display: none;
        font-size: 0.88rem;
        padding: 0.6rem 0.8rem;
        border-radius: 7px;
        margin-top: 0.3rem;
      }
      .quiz-feedback.show {
        display: block;
      }
      .quiz-feedback.ok {
        background: var(--ok-soft);
      }
      .quiz-feedback.bad {
        background: var(--edge-soft);
      }
      a:focus-visible,
      summary:focus-visible,
      .quiz-option:focus-visible {
        outline: 3px solid var(--accent);
        outline-offset: 2px;
      }
      table.vals td.yes::before,
      .dataflow .node.pass::before,
      .tnode.kept::before,
      .quiz-option.correct::before {
        content: "\2713\00a0";
        font-weight: 700;
      }
      table.vals td.no::before,
      .dataflow .node.fail::before,
      .quiz-option.incorrect::before {
        content: "\2717\00a0";
        font-weight: 700;
      }
      table.vals td.warn::before {
        content: "\25B2\00a0";
        font-weight: 700;
      }
      .tnode.skipped::before {
        content: "\2013\00a0";
        font-weight: 700;
      }
      @media (max-width: 800px) {
        .layout {
          grid-template-columns: minmax(0, 1fr);
          gap: 1rem;
          padding: 1.25rem 1.1rem 4rem;
        }
        nav.toc {
          position: static;
          border: 1px solid var(--border);
          border-radius: 8px;
          padding: 0.75rem 1rem;
        }
        body {
          font-size: 16px;
        }
        main > header h1 {
          font-size: 1.6rem;
        }
        table.vals {
          display: block;
          overflow-x: auto;
          max-width: 100%;
        }
      }
"""

QUIZ_JS = r"""
      document.querySelectorAll(".quiz-question").forEach(function (question) {
        var feedback = question.querySelector(".quiz-feedback");

        // Shuffle the options on every load, so the correct answer's position is
        // random and a reader cannot fall into answering by position. Each option
        // is re-inserted before the feedback block, which has to stay last.
        var shuffled = Array.prototype.slice.call(
          question.querySelectorAll(".quiz-option"),
        );
        for (var i = shuffled.length - 1; i > 0; i--) {
          var j = Math.floor(Math.random() * (i + 1));
          var swap = shuffled[i];
          shuffled[i] = shuffled[j];
          shuffled[j] = swap;
        }
        shuffled.forEach(function (option) {
          question.insertBefore(option, feedback);
        });

        var options = question.querySelectorAll(".quiz-option");
        options.forEach(function (option) {
          option.addEventListener("click", function () {
            var isCorrect = option.hasAttribute("data-correct");
            options.forEach(function (other) {
              other.disabled = true;
              if (other.hasAttribute("data-correct"))
                other.classList.add("correct");
            });
            if (!isCorrect) option.classList.add("incorrect");
            feedback.classList.add("show", isCorrect ? "ok" : "bad");
            feedback.insertBefore(
              document.createTextNode(isCorrect ? "Correct. " : "Not quite. "),
              feedback.firstChild,
            );
          });
        });
      });
"""

MERMAID_JS = r"""
      // Mermaid loads without blocking: the page scripts above run first, and a slow
      // or blocked CDN never holds up the quiz or the rest of the page. This is the
      // only permitted external request, and it fires only when a .mermaid block is
      // present. Leave it in place; it is a no-op on pages without a diagram.
      (function () {
        var blocks = document.querySelectorAll(".mermaid");
        if (!blocks.length) return;

        // mermaid.run() replaces each block's text with an SVG, so the source is
        // gone after the first render. Stash it, because a theme change has to
        // parse it again.
        blocks.forEach(function (block) {
          block.dataset.source = block.textContent;
        });

        var darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

        function render() {
          blocks.forEach(function (block) {
            block.removeAttribute("data-processed");
            block.textContent = block.dataset.source;
          });
          try {
            window.mermaid.initialize({
              startOnLoad: false,
              theme: darkQuery.matches ? "dark" : "default",
            });
          } catch (e) {}
          Promise.resolve(window.mermaid.run({ nodes: blocks })).catch(
            function () {},
          );
        }

        var s = document.createElement("script");
        s.src =
          "https://cdn.jsdelivr.net/npm/mermaid@11.16.0/dist/mermaid.min.js";
        s.integrity =
          "sha384-T/0lMUdJpd2S1ZHtRiofG3htU3xPCrFVeAQ1UUE2TJwlEJSV5NUwn30kP28n238E";
        s.crossOrigin = "anonymous";
        s.onload = function () {
          render();
          // Re-render when the reader switches system theme, so the diagram does
          // not stay light on a dark page.
          if (darkQuery.addEventListener)
            darkQuery.addEventListener("change", render);
        };
        document.head.appendChild(s);
      })();
"""

REQUIRED_SECTIONS = ("background", "intuition", "code")
KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
KNOWN_FIELDS = {"title", "lead", "provenance", "key", "sections", "quiz"}


class SpecError(Exception):
    """A named contract violation in the spec, with the JSON path that failed."""


RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def fail(path, message):
    raise SpecError(f"{path}: {message}")


def require_text(spec, field):
    value = spec.get(field)
    if not isinstance(value, str) or not value.strip():
        fail(field, "required, and must be non-empty text")
    return value


def validate(spec):
    unknown = set(spec) - KNOWN_FIELDS
    if unknown:
        fail("<root>", f"unknown field(s): {', '.join(sorted(unknown))}")
    require_text(spec, "title")
    require_text(spec, "lead")
    require_text(spec, "provenance")

    key = spec.get("key")
    if not isinstance(key, str) or not KEY_RE.match(key):
        fail(
            "key",
            "required, and must be letters, digits, dots, underscores, or "
            "hyphens, not starting with a dot or hyphen",
        )
    if key.endswith(".") or key.split(".")[0].lower() in RESERVED_NAMES:
        fail(
            "key",
            f"'{key}' is not a safe filename everywhere: Windows reserves "
            "device names such as CON and NUL, and rejects a trailing dot",
        )

    sections = spec.get("sections")
    if not isinstance(sections, list) or not sections:
        fail("sections", "required, and must be a non-empty list")
    seen = []
    for i, section in enumerate(sections):
        where = f"sections[{i}]"
        if not isinstance(section, dict):
            fail(where, "must be an object")
        if set(section) != {"id", "heading", "html"}:
            fail(where, "must have exactly id, heading, and html")
        sid = section["id"]
        if not isinstance(sid, str) or not ID_RE.match(sid):
            fail(f"{where}.id", "must be lowercase, starting with a letter, hyphenated")
        if sid in seen:
            fail(f"{where}.id", f"'{sid}' is used twice")
        for field in ("heading", "html"):
            if not isinstance(section[field], str) or not section[field].strip():
                fail(f"{where}.{field}", "required, and must be non-empty")
        seen.append(sid)
    ordered = [s for s in seen if s in REQUIRED_SECTIONS]
    if tuple(ordered) != REQUIRED_SECTIONS:
        fail(
            "sections",
            "must carry the background, intuition, and code ids in that "
            f"order; found {ordered or 'none of them'}",
        )

    quiz = spec.get("quiz")
    if not isinstance(quiz, list):
        fail("quiz", "required, and must be a list")
    if len(quiz) != 5:
        fail("quiz", f"the contract is five questions; found {len(quiz)}")
    for i, question in enumerate(quiz):
        where = f"quiz[{i}]"
        if not isinstance(question, dict):
            fail(where, "must be an object")
        if set(question) != {"question", "options", "feedback"}:
            fail(where, "must have exactly question, options, and feedback")
        for field in ("question", "feedback"):
            if not isinstance(question[field], str) or not question[field].strip():
                fail(f"{where}.{field}", "required, and must be non-empty")
        options = question["options"]
        if not isinstance(options, list) or not 2 <= len(options) <= 8:
            fail(f"{where}.options", "must be a list of 2 to 8 options")
        correct = 0
        for j, option in enumerate(options):
            owhere = f"{where}.options[{j}]"
            if not isinstance(option, dict) or set(option) != {"text", "correct"}:
                fail(owhere, "must have exactly text and correct")
            if not isinstance(option["text"], str) or not option["text"].strip():
                fail(f"{owhere}.text", "required, and must be non-empty")
            if not isinstance(option["correct"], bool):
                fail(f"{owhere}.correct", "must be true or false")
            correct += option["correct"]
        if correct != 1:
            fail(f"{where}.options", f"exactly one option must be correct; found {correct}")


def render(spec):
    escape_html = html.escape
    toc_items = "\n".join(
        f'          <li><a href="#{s["id"]}">{escape_html(s["heading"])}</a></li>'
        for s in spec["sections"]
    )
    toc_items += f'\n          <li><a href="#quiz">Quiz</a></li>'

    body_sections = "\n\n".join(
        f'        <section id="{s["id"]}">\n'
        f'          <h2>{escape_html(s["heading"])}</h2>\n'
        f'{s["html"].strip()}\n'
        f"        </section>"
        for s in spec["sections"]
    )

    quiz_blocks = []
    for q in spec["quiz"]:
        buttons = "\n".join(
            f'            <button class="quiz-option"{" data-correct" if o["correct"] else ""}>'
            f'{escape_html(o["text"])}</button>'
            for o in q["options"]
        )
        quiz_blocks.append(
            f'          <div class="quiz-question">\n'
            f'            <p class="q">{escape_html(q["question"])}</p>\n'
            f"{buttons}\n"
            f'            <div class="quiz-feedback" role="status">\n'
            f'              {q["feedback"].strip()}\n'
            f"            </div>\n"
            f"          </div>"
        )
    quiz_html = "\n\n".join(quiz_blocks)

    page = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>@@TITLE@@</title>
    <style>@@CSS@@    </style>
  </head>
  <body>
    <div class="layout">
      <nav class="toc">
        <strong>Contents</strong>
        <ol>
@@TOC_ITEMS@@
        </ol>
      </nav>

      <main>
        <header>
          <h1>@@TITLE@@</h1>
          <p class="lead">
            @@LEAD@@
          </p>
          <p class="provenance">
            @@PROVENANCE@@
          </p>
        </header>

@@SECTIONS@@

        <section id="quiz">
          <h2>Quiz</h2>
@@QUIZ_BLOCKS@@
        </section>
      </main>

      <footer class="colophon">
        Generated with
        <a href="https://github.com/malav2110/explain-diff-html"
          >explain-diff-html</a
        >
      </footer>
    </div>

    <script>@@QUIZ_JS@@    </script>
    <script>@@MERMAID_JS@@    </script>
  </body>
</html>
"""
    replacements = {
        "@@TITLE@@": escape_html(spec["title"]),
        "@@CSS@@": CSS.lstrip("\n"),
        "@@TOC_ITEMS@@": toc_items,
        "@@LEAD@@": escape_html(spec["lead"]),
        "@@PROVENANCE@@": escape_html(spec["provenance"]),
        "@@SECTIONS@@": body_sections,
        "@@QUIZ_BLOCKS@@": quiz_html,
        "@@QUIZ_JS@@": QUIZ_JS.lstrip("\n"),
        "@@MERMAID_JS@@": MERMAID_JS.lstrip("\n"),
    }
    # Title appears twice (head and body); replace all occurrences.
    page = page.replace("@@TITLE@@", replacements.pop("@@TITLE@@"))
    for token, value in replacements.items():
        page = page.replace(token, value)
    return page


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("spec", type=Path, help="path to the JSON content spec")
    ap.add_argument("-o", "--output", type=Path, default=None, help="output HTML path")
    args = ap.parse_args()

    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        sys.exit(f"render.py: cannot read spec {args.spec}: {e}")
    if not isinstance(spec, dict):
        sys.exit("render.py: the spec must be a JSON object")

    try:
        validate(spec)
    except SpecError as e:
        sys.exit(f"render.py: invalid spec: {e}")

    if args.output is not None:
        out_path = args.output
        if out_path.suffix != ".html":
            sys.exit(f"render.py: output must end in .html, not '{out_path.suffix}'")
    else:
        date = datetime.date.today().isoformat()
        out_dir = Path.home() / "code-explanations"
        out_path = out_dir / f"{date}-{spec['key']}-explanation.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out_path.write_text(render(spec), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()
