# Rules

Generated from `RuleMetadata`. Edit the rule, not this file.

The fix kind states who resolves a finding. A mechanical kind is repaired without telling the author, so only a rewrite reaches an agent.

The level says whether a rewrite blocks. An error fails check and stops an agent, while a warning is shown as advice. Set either per rule under `[rules]`, and the Vale rules the same way by name, as in `"subedit.DateRef" = "off"`.

| Rule | Fix kind | Level | Summary |
| --- | --- | --- | --- |
| `line-too-long` | reflow | error | A physical comment line must fit the configured width, counting indent and delimiter. |
| `mid-clause-break` | reflow | error | A sentence sits on one line when it fits, and otherwise breaks at clause commas, on as few lines as it can. |
| `paragraph-line-break` | reflow | error | A Markdown paragraph stays on one source line, since a renderer or a synced copy may show every newline as a break. |
| `block-too-long` | rewrite | warning | A comment block long enough to restate the code has stopped earning its place. |
| `contrast-framing` | rewrite | warning | A sentence states what something is, rather than framing it against what it is not. |
| `file-header-comment` | rewrite | warning | A file must not open with a banner comment before its first declaration. |
| `heading-not-noun-phrase` | rewrite | warning | A Markdown heading is a noun phrase, not a question or an instruction. |
| `mid-sentence-colon` | rewrite | error | A colon stands only in a heading, after a label, or at the end of a line leading into a list or block. |
| `missing-lead-sentence` | rewrite | error | A heading opens with a sentence that frames its section, never straight into a list. |
| `plain-comment-on-public` | rewrite | error | A public symbol must be documented in the doc comment form its language renders. |
| `signature-restating-tag` | rewrite | error | A doc comment must not restate what the type signature already carries. |
| `stub-fragment` | rewrite | warning | A sentence forced to break must not leave a stub of a line behind. |
| `unbreakable-sentence` | rewrite | error | A sentence over the width must carry a clause comma, splitting no list, wherever it has to break, and a summary its style guide keeps to one line must fit it. |
| `bullet-label-style` | targeted | error | A list item label is in Title Case, and bold wherever the text renders. |
| `heading-title-case` | targeted | error | The English words of a Markdown heading are in Title Case. |
| `heading-wrapped-in-bold` | targeted | error | A Markdown heading is not wrapped in bold, since a heading already renders bold. |
| `inclusion-verb` | targeted | error | The house style writes 包含, not 包括. |
| `parenthesis-style` | targeted | error | Parentheses around prose are half-width, spaced from the words outside, and flush with the words inside. |
