# Rules

`subedit` ships 25 native rules, a bundled Vale style of 5 rules, and AutoCorrect. The [README](../README.md#rules) compares what comments and Markdown share and where they differ, and this page lists every rule by group.

Every rule is set by name under `[rules]` to `"error"`, `"warning"`, or `"off"`, as in `"subedit.DateRef" = "off"`. An error fails `check` and stops an agent, while a warning is shown as advice. The fix kind states who resolves a finding, as [Fix Kinds](../README.md#fix-kinds) describes.

## Style

These rules read comments and Markdown alike, and hold the punctuation, labels, and wording of the house style.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `mid-sentence-colon` | A colon, half-width or full-width, joining clauses or leading into an inline list | Rewrite | `error` | `max-label-words` (5), `max-bold-label-words` (10), `max-full-width-label-characters` (12), `max-tag-words` (3) |
| `parenthesis-style` | Parentheses around prose in the width `style` does not pick, or spaced wrong for their width | Targeted | `error` | `style` (`half-width`) |
| `list-label-title-case` | A `label: description` item whose English label is not in Title Case | Targeted | `error` | None |
| `list-label-not-bold` | A `label: description` item whose label is not bold where the text renders | Targeted | `error` | None |
| `discouraged-word` | A word the project writes otherwise, replaced with the one it prefers | Targeted | `error` | `replacements` (1 pair) |
| `contrast-framing` | A Chinese sentence framed as *not A, but B*, which states B against what it is not | Rewrite | `warning` | None |

A colon may stand in a heading, after a short label, or at the end of a line that a list or block follows. A label opens a list item, or a paragraph as a capitalized tag such as `Note`, and carries no verb such as *is* or *can*. A label the author set in bold may run longer. Words opening a list item, or set in bold, that run past these limits may still be a label, so their colon is a warning unless the project sets the rule's severity. A colon anywhere else stays an error. Both list label rules read the same limits, so every rule agrees on what a label is. Parentheses around code, such as `foo(bar)`, are left alone. `half-width` parentheses take a space outside and none inside, the house style. `full-width` follows the CJK standard, where an aside in or beside CJK text takes full-width parentheses with no spaces, and one in English keeps half-width ones. By default `discouraged-word` replaces one Chinese verb for *include* with the one the house style prefers. A project lists its own pairs under `replacements`, as in `{ utilize = "use" }`, or sets it to `{}`. A word in Latin letters matches whole, and a CJK word wherever it stands. Bold goes only where a reader sees it rendered, in Markdown, docstrings, and JSDoc, not in a line comment. Quoted text, in a block quote or quotation marks, is left as written.

## Wording

These rules come from the bundled Vale style, and the author rewrites what they find. They run when Vale is installed, and only in a repository without its own `.vale.ini`. A repository with one runs its own styles instead, and their findings join the same report.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `subedit.EmDash` | An em dash, an en dash, or an arrow in prose | Rewrite | `error` | None |
| `subedit.Semicolon` | A semicolon, half-width or full-width, joining two clauses | Rewrite | `error` | None |
| `subedit.EditHistory` | A phrase such as "no longer" or "used to" that may narrate a change, in comments only | Rewrite | `warning` | None |
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

These rules read comments and commit message bodies, and autofix how their text breaks across lines.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `mid-clause-break` | A sentence broken where it need not be, or a wrapped sentence that would fit one line | Reflow | `error` | None |
| `line-too-long` | A line past the width, counting indent and comment delimiter | Reflow, or Rewrite for a trailing comment | `error` | None |

A trailing comment cannot break without leaving its code behind, so `line-too-long` asks the author to shorten it or move it above the code.

## Sentence

These rules read comments and commit message bodies, and catch the sentences no layout can save, which the author rewrites.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `unbreakable-sentence` | A sentence over the width with no clause comma, or a summary that does not fit one line | Rewrite | `error` | None |
| `line-too-short` | A forced break that leaves a line too short to read as a clause | Rewrite | `warning` | `min-line-characters` (24) |
| `mid-list-break` | A break that seems to fall between the items of a list | Rewrite | `warning` | `max-item-words` (3) |

Reflow reads the same `min-line-characters` floor, so a fix never lays out a line that `line-too-short` then rejects.

Whether a comma parts list items, clauses, or an aside is a matter of syntax, which subedit can only guess, so `mid-list-break` is a warning. Reflow still prefers a break that splits no list when it lays a sentence out itself, but it keeps a legal break the author chose. A piece of up to `max-item-words` words between two commas may be a list item. Switching either rule off leaves its concern out of reflow too.

A period ends a sentence unless it closes an abbreviation. The abbreviations are the English ones Unicode CLDR lists, such as *Mr.* and *Ph.D.*, matched with their case, the Latin ones in lowercase, such as *e.g.* and *etc.*, and a reference such as *Fig.* or *Sec.* before a number. Many CLDR entries, such as *Go.* and *OK.*, are also words, so one ends no sentence only before a lowercase word or a number, unless it holds a period inside, as *U.S.* does. A title such as *Dr.* ends none before a name. A project adds its own under `abbreviations` in its settings, which never end a sentence.

## Structure

These rules read comments, and check where documentation lives and how much of it there is.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `plain-comment-on-public` | A public symbol documented with a plain comment instead of a docstring or JSDoc block | Rewrite | `error` | None |
| `signature-restating-tag` | A doc comment section that restates types the signature already carries, such as `Args:` or `@param` | Rewrite | `error` | None |
| `file-header-comment` | A banner comment opening the file before its first declaration | Rewrite | `warning` | None |
| `comment-too-long` | A comment long enough to restate the code below it | Rewrite | `warning` | `max-plain-lines` (4), `max-internal-doc-lines` (13), `max-public-doc-lines` (20) |

The `comment-too-long` limits are line counts, for a plain comment and for a doc comment on an internal or a public symbol, set from the 95th percentile of a measured corpus. `subedit stats` reports the same percentiles for your codebase.

A plain comment right under another declaration may head a group rather than document one symbol, so `plain-comment-on-public` reports that case as a warning.

## Markdown

These rules read Markdown files, and keep each paragraph on one source line and each heading in its house form.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `paragraph-line-break` | A paragraph or list item broken across source lines | Reflow | `error` | None |
| `heading-wrapped-in-bold` | A heading whose whole text is bold, though a heading already renders bold | Targeted | `error` | None |
| `heading-title-case` | An English heading not in Title Case | Targeted | `error` | `exceptions` (`[]`), `style` (`apa`), `levels` (`[1, 2, 3, 4, 5, 6]`) |
| `table-header-title-case` | An English table header cell not in Title Case | Targeted | `error` | None |
| `missing-lead-sentence` | A heading that opens straight into a list, with no sentence to frame it | Rewrite | `error` | None |
| `heading-not-noun-phrase` | A heading that asks a question or gives an instruction | Rewrite | `error` | `levels` (`[1, 2, 3, 4, 5, 6]`) |

GitHub issues, Notion, and Heptabase can show a source newline as a line break, so a hand-wrapped paragraph breaks once it is copied there. Joining puts no space between two CJK characters, and keeps a break the author marked with two trailing spaces or a backslash.

Title Case follows a published standard, which `style` names. `apa` lowercases articles, conjunctions, and prepositions of three letters or fewer, so it writes *Working With a List*. `chicago` lowercases articles, *and*, *but*, *for*, *or*, *nor*, and every preposition, so it writes *Working with a List*. A word such as *up* or *in* that may stand as an adverb, as in *Set Up*, keeps the case the author wrote, and a capitalized one inside a heading is a warning. Title Case leaves code, file names, acronyms, and a lone lowercase word alone. A lowercase name such as `npm` goes under `exceptions`. List labels and table headers follow `style` and `exceptions` too. A table is otherwise left unread, since its cells are fragments rather than sentences.

A heading that opens with a question word such as *How* or *What*, or ends with a question mark, is a question, so it is an error. A heading whose first word is followed straight by a word opening an object, such as *a*, *the*, or *your*, reads as an instruction, as in *Add a Rule*. That is a guess, so it is a warning unless the project sets the rule's severity. A single word such as *Install* passes, since it may name the subject. Both heading rules read only the heading levels listed under `levels`, so a project can leave out a document title or a FAQ.

## Commit Messages

These rules read the subject of a commit message, from `COMMIT_EDITMSG` and the other files git writes a message to.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `subject-too-long` | A subject past the width GitHub and `git log --oneline` show | Rewrite | `error` | `max-subject-characters` (72) |
| `subject-style` | A subject ending in a period, or off the project convention | Targeted, or Rewrite for a missing type | `error` | `style` (`git`), `types` (`['build', 'chore', 'ci', 'docs', 'feat', 'fix', 'perf', 'refactor', 'revert', 'style', 'test']`) |
| `subject-not-imperative` | A subject that reports the change, as in *Fixed* or *Fixes*, rather than giving it as an instruction | Rewrite | `warning` | None |
| `missing-blank-line` | A body that starts on the line under the subject | Targeted | `error` | None |

`style` names the convention. `git` opens the description with a capital, as git's own documentation does, and leaves a prefix such as a kernel subsystem as written. `conventional` follows Conventional Commits, so the subject opens with one of the `types`, and the description after it opens in lowercase. A word with a capital after its first letter, such as *iOS*, keeps its case under either.

Whether the first word is a verb is grammar a word list can only guess, so `subject-not-imperative` is a warning. The body is laid out by the layout and sentence rules at git's width of 72, and the wording rules read both the subject and the body. Trailers such as `Co-authored-by:` and `Closes #105`, and the comments git adds, are left unread.
