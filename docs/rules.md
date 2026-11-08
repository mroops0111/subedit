# Rules

`subedit` ships 25 native rules, a bundled Vale style of 5 rules, and AutoCorrect. This page lists every rule by the concern it holds, and the [README](../README.md#rules) compares how the surfaces differ.

The Surfaces column names what each rule reads, by the names a project writes under `[surfaces]`. A rule is set for every surface by name under `[rules]`, to `"error"`, `"warning"`, or `"off"`, as in `"subedit.DateRef" = "off"`. It is set for one surface alone under `[surfaces.<name>.rules]`, as the [README](../README.md#configuration) shows. An error fails `check` and stops an agent, while a warning is shown as advice. The fix kind states who resolves a finding, as [Fix Kinds](../README.md#fix-kinds) describes.

## Style

These rules hold the punctuation, labels, and wording of the house style on every surface.

| Rule | Catches | Surfaces | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- | --- |
| `mid-sentence-colon` | A colon, half-width or full-width, joining clauses or leading into an inline list | `comments`, `markdown`, `commit-messages` | Rewrite | `error` | `max-label-words` (5), `max-bold-label-words` (10), `max-full-width-label-characters` (12), `max-tag-words` (3) |
| `parenthesis-style` | Parentheses around prose in the width `style` does not pick, or spaced wrong for their width | `comments`, `markdown`, `commit-messages` | Targeted | `error` | `style` (`half-width`) |
| `list-label-title-case` | A `label: description` item whose English label is not in Title Case | `comments`, `markdown`, `commit-messages` | Targeted | `error` | None |
| `list-label-not-bold` | A `label: description` item whose label is not bold where the text renders | `comments`, `markdown`, `commit-messages` | Targeted | `error` | None |
| `discouraged-word` | A word the project writes otherwise, replaced with the one it prefers | `comments`, `markdown`, `commit-messages` | Targeted | `error` | `replacements` (1 pair) |
| `contrast-framing` | A Chinese sentence framed as *not A, but B*, which states B against what it is not | `comments`, `markdown`, `commit-messages` | Rewrite | `warning` | None |

A colon may stand in a heading, after a short label, or at the end of a line that a list or block follows. A label opens a list item, or a paragraph as a capitalized tag such as `Note`, and carries no verb such as *is* or *can*. A label the author set in bold may run longer. Words opening a list item, or set in bold, that run past these limits may still be a label, so their colon is a warning unless the project sets the rule's severity. A colon anywhere else stays an error. Both list label rules read the same limits, so every rule agrees on what a label is. Parentheses around code, such as `foo(bar)`, are left alone. `half-width` parentheses take a space outside and none inside, the house style. `full-width` follows the CJK standard, where an aside in or beside CJK text takes full-width parentheses with no spaces, and one in English keeps half-width ones. By default `discouraged-word` replaces one Chinese verb for *include* with the one the house style prefers. A project lists its own pairs under `replacements`, as in `{ utilize = "use" }`, or sets it to `{}`. A word in Latin letters matches whole, and a CJK word wherever it stands. Bold goes only where a reader sees it rendered, in Markdown, docstrings, and JSDoc, not in a line comment. Quoted text, in a block quote or quotation marks, is left as written.

## Wording

These rules come from the bundled Vale style, and the author rewrites what they find. They run when Vale is installed, and only in a repository without its own `.vale.ini`. A repository with one runs its own styles instead, and their findings join the same report.

| Rule | Catches | Surfaces | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- | --- |
| `subedit.EmDash` | An em dash, an en dash, or an arrow in prose | `comments`, `markdown`, `commit-messages` | Rewrite | `error` | None |
| `subedit.Semicolon` | A semicolon, half-width or full-width, joining two clauses | `comments`, `markdown`, `commit-messages` | Rewrite | `error` | None |
| `subedit.EditHistory` | A phrase such as "no longer" or "used to" that may narrate a change | `comments` | Rewrite | `warning` | None |
| `subedit.ExternalRef` | An identifier shaped like a ticket number a reader may not be able to open | `comments` | Rewrite | `warning` | None |
| `subedit.DateRef` | A date that records when something changed | `comments` | Rewrite | `warning` | None |

Standards such as `UTF-8` and `SHA-256` are exempt from `subedit.ExternalRef`. The last three guard a comment against going stale, while a Markdown note and a commit message may tell a history, cite an issue, or date a release on purpose. The `subedit:judging-findings` skill gives an agent the criteria for these judgment calls.

## Spacing

AutoCorrect autofixes the spacing between CJK and Latin text on every surface.

| Rule | Catches | Surfaces | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- | --- |
| `autocorrect.Spacing` | Missing spaces and wrong punctuation width between CJK and Latin text | `comments`, `markdown`, `commit-messages` | Targeted | `error` | `.autocorrectrc` |

AutoCorrect ships as a Python dependency, so it runs wherever `subedit` does, and reads `.autocorrectrc` from the working directory.

## Layout

These rules autofix where text breaks across lines. A surface laid out against a width breaks only between clauses, and Markdown, which has none, keeps each paragraph on one line.

| Rule | Catches | Surfaces | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- | --- |
| `mid-clause-break` | A sentence broken where it need not be, or a wrapped sentence that would fit one line | `comments`, `commit-messages` | Reflow | `error` | None |
| `line-too-long` | A line past the width, counting indent and comment delimiter | `comments`, `commit-messages` | Reflow, or Rewrite for a trailing comment | `error` | None |
| `paragraph-line-break` | A paragraph or list item broken across source lines | `markdown` | Reflow | `error` | None |
| `missing-blank-line` | A body that starts on the line under the subject | `commit-messages` | Targeted | `error` | None |

A trailing comment cannot break without leaving its code behind, so `line-too-long` asks the author to shorten it or move it above the code.

GitHub issues, Notion, and Heptabase can show a source newline as a line break, so a hand-wrapped paragraph breaks once it is copied there. Joining puts no space between two CJK characters, and keeps a break the author marked with two trailing spaces or a backslash.

git reads every line up to the first blank one as a commit subject, so `missing-blank-line` puts a blank line between the subject and the body.

## Sentence

These rules catch the sentences no layout can save on a surface laid out against a width, and the author rewrites them.

| Rule | Catches | Surfaces | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- | --- |
| `unbreakable-sentence` | A sentence over the width with no clause comma, or a summary that does not fit one line | `comments`, `commit-messages` | Rewrite | `error` | None |
| `line-too-short` | A forced break that leaves a line too short to read as a clause | `comments`, `commit-messages` | Rewrite | `warning` | `min-line-characters` (24) |
| `mid-list-break` | A break that seems to fall between the items of a list | `comments`, `commit-messages` | Rewrite | `warning` | `max-item-words` (3) |

Reflow reads the same `min-line-characters` floor, so a fix never lays out a line that `line-too-short` then rejects.

Whether a comma parts list items, clauses, or an aside is a matter of syntax, which subedit can only guess, so `mid-list-break` is a warning. Reflow still prefers a break that splits no list when it lays a sentence out itself, but it keeps a legal break the author chose. A piece of up to `max-item-words` words between two commas may be a list item. Switching either rule off leaves its concern out of reflow too.

A period ends a sentence unless it closes an abbreviation. The abbreviations are the English ones Unicode CLDR lists, such as *Mr.* and *Ph.D.*, matched with their case, the Latin ones in lowercase, such as *e.g.* and *etc.*, and a reference such as *Fig.* or *Sec.* before a number. Many CLDR entries, such as *Go.* and *OK.*, are also words, so one ends no sentence only before a lowercase word or a number, unless it holds a period inside, as *U.S.* does. A title such as *Dr.* ends none before a name. A project adds its own under `abbreviations` in its settings, which never end a sentence.

## Structure

These rules check where documentation lives, how much of it there is, and how a section opens.

| Rule | Catches | Surfaces | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- | --- |
| `plain-comment-on-public` | A public symbol documented with a plain comment instead of a docstring or JSDoc block | `comments` | Rewrite | `error` | None |
| `signature-restating-tag` | A doc comment section that restates types the signature already carries, such as `Args:` or `@param` | `comments` | Rewrite | `error` | None |
| `file-header-comment` | A banner comment opening the file before its first declaration | `comments` | Rewrite | `warning` | None |
| `comment-too-long` | A comment long enough to restate the code below it | `comments` | Rewrite | `warning` | `max-plain-lines` (4), `max-internal-doc-lines` (13), `max-public-doc-lines` (20) |
| `missing-lead-sentence` | A heading that opens straight into a list, with no sentence to frame it | `markdown` | Rewrite | `error` | None |

The `comment-too-long` limits are line counts, for a plain comment and for a doc comment on an internal or a public symbol, set from the 95th percentile of a measured corpus. `subedit stats` reports the same percentiles for your codebase.

A plain comment right under another declaration may head a group rather than document one symbol, so `plain-comment-on-public` reports that case as a warning.

## Titles

These rules hold the form of a title, a Markdown heading or table header and a commit subject alike.

| Rule | Catches | Surfaces | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- | --- |
| `heading-wrapped-in-bold` | A heading whose whole text is bold, though a heading already renders bold | `markdown` | Targeted | `error` | None |
| `heading-title-case` | An English heading not in Title Case | `markdown` | Targeted | `error` | `exceptions` (`[]`), `style` (`apa`), `levels` (`[1, 2, 3, 4, 5, 6]`) |
| `table-header-title-case` | An English table header cell not in Title Case | `markdown` | Targeted | `error` | None |
| `heading-not-noun-phrase` | A heading that asks a question or gives an instruction | `markdown` | Rewrite | `error` | `levels` (`[1, 2, 3, 4, 5, 6]`) |
| `subject-too-long` | A subject past the width GitHub and `git log --oneline` show | `commit-messages` | Rewrite | `error` | `max-subject-characters` (72) |
| `subject-style` | A subject ending in a period, or off the project convention | `commit-messages` | Targeted, or Rewrite for a missing type | `error` | `style` (`git`), `types` (`['build', 'chore', 'ci', 'docs', 'feat', 'fix', 'perf', 'refactor', 'revert', 'style', 'test']`) |
| `subject-not-imperative` | A subject that reports the change, as in *Fixed* or *Fixes*, rather than giving it as an instruction | `commit-messages` | Rewrite | `warning` | None |

Title Case follows a published standard, which `style` names. `apa` lowercases articles, conjunctions, and prepositions of three letters or fewer, so it writes *Working With a List*. `chicago` lowercases articles, *and*, *but*, *for*, *or*, *nor*, and every preposition, so it writes *Working with a List*. A word such as *up* or *in* that may stand as an adverb, as in *Set Up*, keeps the case the author wrote, and a capitalized one inside a heading is a warning. Title Case leaves code, file names, acronyms, and a lone lowercase word alone. A lowercase name such as `npm` goes under `exceptions`. List labels and table headers follow `style` and `exceptions` too. A table is otherwise left unread, since its cells are fragments rather than sentences.

A heading that opens with a question word such as *How* or *What*, or ends with a question mark, is a question, so it is an error. A heading whose first word is followed straight by a word opening an object, such as *a*, *the*, or *your*, reads as an instruction, as in *Add a Rule*. That is a guess, so it is a warning unless the project sets the rule's severity. A single word such as *Install* passes, since it may name the subject. Both heading rules read only the heading levels listed under `levels`, so a project can leave out a document title or a FAQ.

`style` names the convention. `git` opens the description with a capital, as git's own documentation does, and leaves a prefix such as a kernel subsystem as written. `conventional` follows Conventional Commits, so the subject opens with one of the `types`, and the description after it opens in lowercase. A word with a capital after its first letter, such as *iOS*, keeps its case under either.

Whether the first word of a subject is a verb is grammar a word list can only guess, so `subject-not-imperative` is a warning.
