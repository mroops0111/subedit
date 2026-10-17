---
name: judging-findings
description: Decide what to do with a subedit finding that no tool can fix, such as subedit.ExternalRef, subedit.DateRef, subedit.MidSentenceColon, block-too-long, or unbreakable-sentence. Use when a subedit hook, `subedit check`, or `subedit fix` reports a finding that needs rewriting or a warning that is a judgment call.
---

# Judge subedit Findings

subedit repairs comment layout on its own. What reaches you is either an error, which blocks until the text is rewritten, or a warning, which asks for a judgment and blocks nothing. For each finding, read the flagged comment, apply the criteria below, and either rewrite the text or leave it as it is.

## Project Criteria Come First

A project or its people can judge differently. Look for their criteria before applying these, and follow theirs where the two disagree:

- `CLAUDE.md` or `AGENTS.md` in the repository, or the user's own instructions.
- A project or personal skill that covers subedit findings.
- `[tool.subedit.rules]` in `pyproject.toml`, or `[rules]` in `subedit.toml`. A rule set to `"off"` there is never reported. A rule a project wants left alone for good belongs there, not in a suppression comment.

## Rewriting

Rewrite in place, keep the meaning, and keep the comment to the constraint the code cannot show. Never add a suppression comment, and never reword a sentence only to dodge a pattern while keeping what the rule objects to.

## Warnings

A warning passes when the text meets its criterion. Leave such text exactly as it is, and say so in one line if anyone asks.

| Rule | Keep the text when | Rewrite it when |
| --- | --- | --- |
| `subedit.ExternalRef` | The identifier is public and resolvable by anyone, such as an RFC, an MCP SEP, a PEP, a CVE, or an ISO standard. | It is a private ticket, such as a Jira key or an internal issue number. State the constraint the ticket recorded instead. |
| `subedit.DateRef` | The date names a version or a spec revision, such as the dated revision an MCP specification is named by. | It records when something happened or changed. State the constraint that holds now. |
| `subedit.MidSentenceColon` | The colon introduces a list, an indented block, or a label such as `Note:`. | The sentence runs on after the colon. Split it into two sentences, or join the clauses with a comma and a conjunction. |
| `block-too-long` | Every sentence states a constraint the code cannot show. | Some sentences narrate what the code does. Cut them, or move the explanation into a name. |
| `file-header-comment` | It states a constraint about the whole module that no single declaration owns. | It is a banner or a summary of the file. Delete it, or move the constraint to the declaration it applies to. |
| `stub-fragment` | Never. A stub reads as a broken clause. | Always. Rewrite the sentence to fit one line, or split it into two complete sentences. |

## Errors

An error always needs a rewrite. The message states the fix, and these notes cover what it leaves out.

- `unbreakable-sentence`: a line can break only at a comma that ends a clause, and a comma inside brackets or a code span does not count. Add a comma at a clause boundary, or split the sentence in two. When every such comma would split a list, move the list to the end of the sentence. A Python docstring's summary must fit one line, so shorten it and move the detail into the body.
- `line-too-long` (trailing comment): a comment beside code cannot break, so shorten it or move it to its own line above the code.
- `plain-comment-on-public`: move the text into the doc comment, a docstring in Python or a `/** */` block in TypeScript.
- `signature-restating-tag` and `subedit.SignatureTag`: delete the tag, since the signature already says it.
- `subedit.EditHistory`: state the current behavior, not its history.
- `subedit.Semicolon`, `subedit.EmDash`: split into two sentences, or use a comma or parentheses.
- `subedit.Ellipsis`: name two or three concrete examples after "such as", as in "a transport failure, such as a connect, timeout, or DNS error". Dropping the trailing word and joining the rest with "or" turns a sample into the whole set, which narrows what the sentence claims.
