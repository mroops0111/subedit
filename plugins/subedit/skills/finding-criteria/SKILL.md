---
name: finding-criteria
description: Decide what to do with a subedit finding that no tool can fix, such as subedit.ExternalRef, mid-sentence-colon, comment-too-long, heading-not-noun-phrase, subject-not-imperative, or unbreakable-sentence. Use when a subedit hook, `subedit check`, or `subedit fix` reports a finding that needs rewriting or a warning that is a judgment call.
---

# subedit Finding Criteria

subedit repairs layout on its own, in comments, Markdown, and commit messages alike. What reaches you is either an error, which blocks until the text is rewritten, or a warning, which asks for a judgment and blocks nothing. For each finding, read the flagged text, apply the criteria below, and either rewrite the text or leave it as it is.

## Project Criteria

A project or its people can judge differently. Look for their criteria before applying these, and follow theirs where the two disagree:

- `CLAUDE.md` or `AGENTS.md` in the repository, or the user's own instructions.
- A project or personal skill that covers subedit findings.
- `[tool.subedit.rules]` in `pyproject.toml`, or `[rules]` in `subedit.toml`. A rule set to `"off"` there is never reported. A rule a project wants left alone for good belongs there, not in a suppression comment.
- `[surfaces.<name>.rules]` for one surface alone, such as `commit-messages`, and `[surfaces]` for a surface switched off whole.

## Rewriting

Rewrite in place, keep the meaning, and keep a comment to the constraint the code cannot show. Never add a suppression comment, and never reword a sentence only to dodge a pattern while keeping what the rule objects to.

A commit message comes back from the hook with its findings and its text laid out, since the commit is already made. Amend it with `git commit --amend --only -F -` only while the commit is not pushed. A pushed commit stays as it is.

## Judgment Calls

A warning passes when the text meets its criterion, and so does `heading-not-noun-phrase`, an error that can mistake a noun for a verb. Leave such text exactly as it is, and say so in one line if anyone asks.

| Rule | Keep the Text When | Rewrite It When |
| --- | --- | --- |
| `subedit.ExternalRef` | The identifier is public and resolvable by anyone, such as an RFC, an MCP SEP, a PEP, a CVE, or an ISO standard. | It is a private ticket, such as a Jira key or an internal issue number. State the constraint the ticket recorded instead. |
| `subedit.DateRef` | The date names a version or a spec revision, such as the dated revision an MCP specification is named by. | It records when something happened or changed. State the constraint that holds now. |
| `subedit.EditHistory` | The phrase states a constraint that holds now, as in "a file no longer than 10 lines". | It tells how the code used to behave. State the behavior it has now. |
| `contrast-framing` | Never in the house style, unless the contrast is the point, written as 是 B 而非 A. | It frames B against what it is not. State B directly. |
| `heading-not-noun-phrase` | The heading is a noun phrase that happens to open with the flagged word. | It asks a question or gives an instruction. Name the section's subject instead. |
| `subject-not-imperative` | The flagged word is no verb, such as a name or a noun that opens the subject. | It reports the change, as in *Fixed* or *Adds*. Give it as an instruction, as in *Fix* or *Add*. |
| `comment-too-long` | Every sentence states a constraint the code cannot show. | Some sentences narrate what the code does. Cut them, or move the explanation into a name. |
| `file-header-comment` | It states a constraint about the whole module that no single declaration owns. | It is a banner or a summary of the file. Delete it, or move the constraint to the declaration it applies to. |
| `line-too-short` | Never. A line that short reads as a broken clause. | Always. Rewrite the sentence to fit one line, or split it into two complete sentences. |
| `mid-list-break` | The comma at the break parts an aside or a clause, as in "stays a reference, rewritten to X, and the component is expanded". | It parts the items of a list. Move the list to the end of the sentence, or split the sentence in two. |

## Errors

An error always needs a rewrite. The message states the fix, and these notes cover what it leaves out.

- **`unbreakable-sentence`**: a line can break only at a comma that ends a clause, and a comma inside brackets or a code span does not count. Add a comma at a clause boundary, or split the sentence in two. When the message names a style guide that keeps a summary to one line, shorten the summary and move the detail into the body.
- **`line-too-long`** (trailing comment): a comment beside code cannot break, so shorten it or move it to its own line above the code.
- **`plain-comment-on-public`**: move the text into the doc comment, a docstring in Python or a `/** */` block in TypeScript.
- **`signature-restating-tag`**: delete the tag, since the signature already says it.
- **`mid-sentence-colon`**: a colon stands only in a heading, after a short label, or at the end of a line that a list or block follows. Split the sentence in two, or turn the inline list into a list.
- **`missing-lead-sentence`**: add a sentence or two under the heading that frames what the list holds.
- **`subject-too-long`**: keep what the change does in the subject, and move why and how into the body.
- **`subject-style`** (no type): open the subject with one of the types the project lists, as in `fix: handle empty input`.
- **`subedit.Semicolon`, `subedit.EmDash`**: split into two sentences, or use a comma or parentheses.
