# Rules

`subedit` ships 18 native rules, a bundled Vale style of 6 rules, and AutoCorrect. The [README](../README.md#rules) compares what comments and Markdown share and where they differ, and this page lists every rule by group.

Every rule is set by name under `[rules]` to `"error"`, `"warning"`, or `"off"`, as in `"subedit.DateRef" = "off"`. An error fails `check` and stops an agent, while a warning is shown as advice. The fix kind states who resolves a finding, as [Fix Kinds](../README.md#fix-kinds) describes.

## Style

These rules read comments and Markdown alike, and hold the punctuation, labels, and wording of the house style.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `mid-sentence-colon` | A colon, half-width or full-width, joining clauses or leading into an inline list | Rewrite | `error` | None |
| `parenthesis-style` | Full-width parentheses, or half-width ones without a space outside or with one inside | Targeted | `error` | None |
| `bullet-label-style` | A `label: description` item whose label is not in Title Case, or not bold where the text renders | Targeted | `error` | None |
| `inclusion-verb` | A verb for *include* that the house style does not use, replaced with the one it does | Targeted | `error` | None |
| `contrast-framing` | A sentence framed as *not A, but B*, which states B against what it is not | Rewrite | `warning` | None |

A colon may stand in a heading, after a short label, or at the end of a line that a list or block follows. Parentheses around code, such as `foo(bar)`, are left alone. Bold goes only where a reader sees it rendered, in Markdown, docstrings, and JSDoc, not in a line comment. Quoted text, in a block quote or quotation marks, is left as written.

## Wording

These rules come from the bundled Vale style, and the author rewrites what they find. They run when Vale is installed, and only in a repository without its own `.vale.ini`. A repository with one runs its own styles instead, and their findings join the same report.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `subedit.EmDash` | An em dash, an en dash, or an arrow in prose | Rewrite | `error` | None |
| `subedit.Semicolon` | A semicolon, half-width or full-width, joining two clauses | Rewrite | `error` | None |
| `subedit.EditHistory` | A phrase such as "no longer" or "used to" that may narrate a change, in comments only | Rewrite | `warning` | None |
| `subedit.SignatureTag` | A tag that restates the signature, matched by text, in comments only | Rewrite | `error` | None |
| `subedit.ExternalRef` | An identifier shaped like a ticket number a reader may not be able to open, in comments only | Rewrite | `warning` | None |
| `subedit.DateRef` | A date that records when something changed, in comments only | Rewrite | `warning` | None |

Standards such as `UTF-8` and `SHA-256` are exempt from `subedit.ExternalRef`. The `subedit:judging-findings` skill gives an agent the criteria for these judgment calls.

## Spacing

AutoCorrect reads comments and Markdown alike, and autofixes the spacing between CJK and Latin text.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `autocorrect.Spacing` | Missing spaces and wrong punctuation width between CJK and Latin text | Targeted | `error` | `.autocorrectrc` |

AutoCorrect ships as a Python dependency, so it runs wherever `subedit` does, and reads `.autocorrectrc` from the working directory.

## Layout

These rules read comments, and autofix how a comment breaks across lines.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `mid-clause-break` | A sentence broken where it need not be, or a wrapped sentence that would fit one line | Reflow | `error` | None |
| `line-too-long` | A comment line past the width, counting indent and delimiter | Reflow, or Rewrite for a trailing comment | `error` | None |

A trailing comment cannot break without leaving its code behind, so `line-too-long` asks the author to shorten it or move it above the code.

## Sentence

These rules read comments, and catch the sentences no layout can save, which the author rewrites.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `unbreakable-sentence` | A sentence over the width with no clause comma, a break that would split a list, or a summary that does not fit one line | Rewrite | `error` | None |
| `stub-fragment` | A forced break that leaves a line too short to read as a clause | Rewrite | `warning` | `minimum_characters` (24) |

Reflow reads the same `minimum_characters` floor, so a fix never lays out a stub that `stub-fragment` then rejects.

## Structure

These rules read comments, and check where documentation lives and how much of it there is.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `plain-comment-on-public` | A public symbol documented with a plain comment instead of a docstring or JSDoc block | Rewrite | `error` | None |
| `signature-restating-tag` | A doc comment section that restates types the signature already carries, such as `Args:` or `@param` | Rewrite | `error` | None |
| `file-header-comment` | A banner comment opening the file before its first declaration | Rewrite | `warning` | None |
| `block-too-long` | A comment block long enough to restate the code below it | Rewrite | `warning` | `line` (4), `doc-internal` (13), `doc-public` (20) |

The `block-too-long` limits are line counts, set from the 95th percentile of a measured corpus. `subedit stats` reports the same percentiles for your codebase.

A plain comment right under another declaration may head a group rather than document one symbol, so `plain-comment-on-public` reports that case as a warning.

## Markdown

These rules read Markdown files, and keep each paragraph on one source line and each heading in its house form.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `paragraph-line-break` | A paragraph or list item broken across source lines | Reflow | `error` | None |
| `heading-wrapped-in-bold` | A heading whose whole text is bold, though a heading already renders bold | Targeted | `error` | None |
| `heading-title-case` | An English heading not in Title Case | Targeted | `error` | `keep` (`[]`) |
| `missing-lead-sentence` | A heading that opens straight into a list, with no sentence to frame it | Rewrite | `error` | None |
| `heading-not-noun-phrase` | A heading that asks a question or gives an instruction | Rewrite | `warning` | None |

GitHub issues, Notion, and Heptabase can show a source newline as a line break, so a hand-wrapped paragraph breaks once it is copied there. Joining puts no space between two CJK characters, and keeps a break the author marked with two trailing spaces or a backslash.

Title Case leaves code, file names, acronyms, and a lone lowercase word alone. A lowercase name such as `npm` goes under `keep`, which list labels follow too.
