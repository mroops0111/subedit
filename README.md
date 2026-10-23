![subedit. Your house style, enforced on every sentence your agents write.](docs/assets/cover.svg)

<p align="center">
  <a href="https://github.com/mroops0111/subedit/actions/workflows/ci.yml"><img src="https://github.com/mroops0111/subedit/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/subedit/"><img src="https://img.shields.io/pypi/v/subedit.svg" alt="PyPI version"></a>
  <a href="https://pepy.tech/projects/subedit"><img src="https://static.pepy.tech/badge/subedit/month" alt="PyPI downloads"></a>
  <a href="https://pypi.org/project/subedit/"><img src="https://img.shields.io/pypi/pyversions/subedit.svg" alt="Python versions"></a>
  <a href="#agent-integration"><img src="https://img.shields.io/badge/Claude%20Code-plugin-d97757" alt="Claude Code plugin"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

Linters keep an agent's code in shape. Almost nothing does the same for its sentences. `subedit` is a subeditor for AI agents. It checks every sentence an agent writes into your repository, autofixes the layout without a word, and hands back to the model only what needs rewriting, with the fix stated. [Surfaces](#surfaces) lists the kinds of file it reads.

- **Built for Agents**: a post-edit hook for Claude Code and Codex checks each file an agent writes, as it lands.
- **Silent Autofix, Stated Rewrites**: layout and spacing are autofixed without a message, and only a finding that needs the sentence's meaning goes back, with its fix stated.
- **Sentence-Aware Layout**: a sentence takes one line when it fits, and otherwise breaks only at a comma that ends a clause.
- **Never Touches Code**: tree-sitter finds the prose, so code, string literals, and commented-out code are left as they are.
- **One Report, Three Engines**: native layout and structure rules, a bundled Vale style, and AutoCorrect share one config and one report.

---

## Example

An editor wraps a comment at whatever column it reaches, so sentences break mid clause.

```python
def read_chunk(stream):
    # Cap the buffer at the runner limit, because an unbounded
    # read faults the job. Retry once, then give up.
    return stream.read(LIMIT)
```

`subedit fix --write` autofixes the layout and says nothing.

```python
def read_chunk(stream):
    # Cap the buffer at the runner limit, because an unbounded read faults the job.
    # Retry once, then give up.
    return stream.read(LIMIT)
```

A sentence that runs past the width with no comma has nowhere legal to break, and only its author knows where the meaning divides. That one goes back to the agent that wrote it, or to you.

```text
1 comment finding needs rewriting in src/cache.py.
Each states the fix. Apply it in place, do not add a suppression comment.

line 2  [unbreakable-sentence]
  This sentence runs to 116 characters against a budget of 114 characters and contains no comma, so there is no legal place to break it. Add a comma at a clause boundary, or split it into two sentences.
```

## Getting Started

`subedit` runs inside an AI agent as a plugin, and on its own from the command line.

### Claude Code Plugin

The plugin needs only [uv](https://docs.astral.sh/uv/). It runs `subedit` from PyPI with the `vale` extra, and warms that environment in the background when a session starts, so no edit waits on the first download.

```text
/plugin marketplace add mroops0111/subedit
/plugin install subedit@mroops
```

The hook then acts in every project that opts in with a `subedit.toml`, which may be empty. [Agent Integration](#agent-integration) covers Codex and registering the hook by hand.

### Command Line

The command line tool needs Python 3.11 or newer, and installs from PyPI.

```bash
uv tool install 'subedit[vale]'   # recommended, fetches Vale for you
uv tool install subedit           # without Vale, the native rules and AutoCorrect still run
```

`pipx install subedit` and `pip install subedit` work as well. To try it without installing, prefix any command with `uvx`.

### Quick Start

Every command takes files or directories, and a directory walk skips dotted and vendor directories such as `.venv` and `node_modules`.

| Command | What It Does |
| --- | --- |
| `subedit check src/` | Reports every finding |
| `subedit check src/ --output=actionable` | Reports only the findings that need rewriting |
| `subedit check src/ --output=json` | Reports every finding as JSON, for other tools |
| `subedit fix src/` | Shows the autofixes as a diff |
| `subedit fix src/ --write` | Applies the autofixes in place |
| `subedit stats src/` | Measures comment lengths and widths, to set thresholds from data |
| `subedit rules` | Lists every native rule with its fix kind and default level |

To adopt `subedit` in a project, add an empty `subedit.toml` at its root, then run `fix --write` once and read what `check` still reports. `--no-delegate` skips Vale and AutoCorrect.

`check` exits 1 on any `error` finding, including ones `fix` would autofix, and `fix` exits 1 while an `error` rewrite remains. Both drop into CI or a pre-commit hook as they are.

<details>
<summary><b>CI Workflow</b>: a GitHub Actions job</summary>

<br>

```yaml
# .github/workflows/prose.yml
jobs:
  subedit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - run: uvx --from 'subedit[vale]' subedit check src/
```

</details>

## Background

A subeditor is the editor at a newspaper who makes every article follow the paper's style guide. `subedit` does that for the text AI agents write in your repository.

Agents write a lot of comments and docs, and they rarely go back to check them. Code formatters skip comments, and prose linters don't understand source files. So three kinds of problems slip through:

- **Layout**: comments are wrapped at a fixed column, so sentences break in the middle of a phrase.
- **Placement**: a public function gets a plain comment instead of a docstring, so it never shows up on hover.
- **Wording**: change history, ticket numbers, and lists that trail off end up in comments and go out of date.

Telling the agent isn't enough. Even with a style guide or a skill, agents get layout rules wrong, such as where a sentence may break, and forget them as the conversation grows. A tool that checks every edit doesn't forget.

A linter that sends back fifty layout complaints also wastes the agent's context on work a tool could do. `subedit` fixes what it can by itself, and reports only what needs a rewrite.

## Design

Every finding says who can resolve it, and the whole design turns on that answer.

### Fix Kinds

A rule declares one of three fix kinds, which decides what changes and who makes the change.

| Kind | What Changes | Resolved By | Example |
| --- | --- | --- | --- |
| `TARGETED` | A few characters, in place | The tool, silently | A missing space between CJK and Latin text |
| `REFLOW` | Where the lines of a comment break | The tool, silently | A sentence broken mid clause |
| `REWRITE` | The wording itself | The author | A sentence too long to break anywhere legal |

Targeted and reflow fixes are autofixes, which the tool applies without a message. Only a rewrite reaches the author, because changing the wording needs the sentence's meaning. The tool applies targeted edits before reflow, since a changed character can move where a line breaks.

### Severity

A level decides whether a rewrite blocks. Every rule has a default, and every rule can be moved between levels or switched off.

| Level | `check` and `fix` | Agent Hook |
| --- | --- | --- |
| `error` | Fails with exit code 1 | Blocks the edit and sends the message to the model |
| `warning` | Shows the message as advice | Sends the message as context, without blocking |
| `off` | Skips the rule | Skips the rule |

Judgment rules, such as a long block or a date in a comment, default to `warning`. A rule whose finding is wrong in almost every case defaults to `error`.

### Layout Model

Reflow works on sentences rather than lines, so the result reads the way the author would have broken it.

- **One Line When It Fits**: a sentence that fits takes one line, and a wrapped one that would fit is joined.
- **Clause Commas Only**: a longer sentence breaks only at a comma that ends a clause, never inside a list, brackets, or a code span.
- **No Stubs**: no break leaves a line shorter than the `stub-fragment` floor, 24 characters by default.
- **Verbatim Blocks**: code examples, docstring sections, and JSDoc tags are left as written.

### Pipeline

A file takes the same path through `subedit` whether the CLI or the agent hook started it.

![subedit pipeline. An author or agent runs the CLI or the agent hook, which reads subedit.toml. subedit parses the comments and docstrings, lints them with its own rules, Vale, and AutoCorrect, then triages each finding by fix kind and level. An autofix is written back silently, and a rewrite is sent back to the author with its fix stated.](docs/assets/pipeline.svg)

1. **Resolve**: the CLI or the hook finds the closest `subedit.toml`, or `[tool.subedit]` in `pyproject.toml`, and reads the rules and the width.
2. **Parse**: the language profile parses the file with tree-sitter and builds a ProseMap of every comment and docstring, with its placement and the symbol it documents.
3. **Lint**: the native rules run over each comment group, while Vale and AutoCorrect run over the file. A delegated finding is kept only when it lands inside comment prose.
4. **Autofix**: the Fixer applies targeted edits, then reflow edits, and runs the rules again, for up to ten rounds until nothing mechanical is left.
5. **Report**: what remains is a rewrite, reported as a blocking error or as advice.

### Architecture

The package follows a layered design, so a new language, rule, or delegated tool is one class behind an existing port.

![subedit layers. presentation holds the CLI, the agent hook, and the reports, and calls application, which holds the Linter, the Fixer, the report aggregator, and the corpus meter. application uses domain, which holds the models, the rules, and the ports. infrastructure holds the tree-sitter parser, the config source, and the Vale and AutoCorrect adapters. presentation wires infrastructure in, and infrastructure implements the domain ports.](docs/assets/layers.svg)

| Layer | Holds | Extension Point |
| --- | --- | --- |
| `domain` | Comment groups, prose and sentence models, diagnostics, the native rules | `Rule`, `SourceParser`, `LanguageConventions`, `ExternalLinter` |
| `application` | Linting, the fix loop, report merging, corpus statistics | None, it composes the ports |
| `infrastructure` | The tree-sitter parser and language profiles, config sources, Vale and AutoCorrect adapters | A `LanguageProfile` per language |
| `presentation` | The Typer CLI, the agent hook, one harness per agent, report formatters | An `AgentHarness` per agent |

Rules never see a syntax tree. A profile turns the tree into comment groups that carry their form, placement, and the symbol they document, so the same rules serve every language. A new surface plugs in the same way, as an extractor that hands prose to the rules.

## Reference

The sections below are for looking things up, from the hook's behavior to every rule and setting.

### Agent Integration

`subedit-hook` runs after every file an agent edits. It applies the autofixes in place, and exits 2 only when a sentence needs rewriting, which hands the message back to the model. In Claude Code a warning reaches the model too, as context beside the tool result, without blocking the edit.

The hook acts only in a project that opts in, with a `subedit.toml` or a `[tool.subedit]` table in `pyproject.toml`, in the edited file's directory or a parent. An empty table is enough. Elsewhere it exits 0 and changes nothing, so a plugin installed for every session stays out of projects that never asked for it.

#### Claude Code

The [plugin](#claude-code-plugin) registers the hook for you. It also ships the `subedit:judging-findings` skill, which gives the model the criteria for every finding a tool cannot fix, such as when a spec identifier stays and a ticket number goes. Criteria in your `CLAUDE.md`, `AGENTS.md`, or a skill of your own come first.

<details>
<summary><b>Manual Hook Registration</b>: without the plugin</summary>

<br>

With `subedit` installed as a tool, add this to `.claude/settings.json`.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [{ "type": "command", "command": "subedit-hook" }]
      }
    ]
  }
}
```

</details>

#### Codex

Add this to `~/.codex/hooks.json`.

```json
{
  "hooks": {
    "PostToolUse": [{ "command": "subedit-hook" }]
  }
}
```

#### Several Agents

Registering the hook with both agents is the normal case. Each agent names its edit tools differently, so every payload identifies its sender, and a payload from anything else exits 0 untouched. `subedit-hook --help` prints the payload shapes it accepts.

### Configuration

Settings come from `subedit.toml`, or from `[tool.subedit]` in `pyproject.toml`, whichever sits closest above the file being checked. Without either, `check` and `fix` run with the defaults.

```toml
[subedit]
line-width = 100
exclude = ["tests/fixtures/**"]

[rules]
mid-clause-break = "error"                                       # set a level
file-header-comment = "off"                                      # switch a rule off
block-too-long = { severity = "warning", line = 3, doc-public = 20 }  # level and options
stub-fragment = { minimum_characters = 30 }                      # options only

# Delegated rules are set the same way, by name.
"subedit.MidSentenceColon" = "error"
"subedit.DateRef" = "off"
```

In `pyproject.toml`, the same keys sit under `[tool.subedit]` and `[tool.subedit.rules]`.

<details>
<summary><b>Configuration Reference</b>: every key and its default</summary>

<br>

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `line-width` | Integer | The formatter's width, else 120 | The column every comment line must fit, counting indent and delimiter |
| `exclude` | List of globs | `[]` | Paths a directory walk skips, relative to the config file |
| `rules.<name>` | `"error"`, `"warning"`, or `"off"` | The rule's default | The level of one rule, native or delegated |
| `rules.<name>` | Table | The rule's default | `severity` plus the rule's own options |

Left unset, `line-width` follows the formatter that would format the file, read from its own config.

| Language | Width Read From |
| --- | --- |
| Python | `line-length` for ruff or black |
| TypeScript | `printWidth` for Prettier, `lineWidth` for Biome |

</details>

### Rules

`subedit` ships 8 native rules, a bundled Vale style of 9 rules, and AutoCorrect. Every rule below is set by name under `[rules]`, as in [Configuration](#configuration).

- **Level**: every rule accepts `"error"`, `"warning"`, or `"off"` in place of its default.
- **Fix Kind**: `Targeted` and `Reflow` are autofixes, applied silently by `fix` and the hook. `Rewrite` goes back to the agent or the author, with the fix stated, as [Fix Kinds](#fix-kinds) explains.

<details>
<summary><b>Layout</b>: how a comment breaks across lines, autofixed</summary>

<br>

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `mid-clause-break` | A sentence broken where it need not be, or a wrapped sentence that would fit one line | Reflow | `error` | None |
| `line-too-long` | A comment line past the width, counting indent and delimiter | Reflow, or Rewrite for a trailing comment | `error` | None |

A trailing comment cannot break without leaving its code behind, so `line-too-long` asks the author to shorten it or move it above the code.

</details>

<details>
<summary><b>Sentence</b>: sentences no layout can save, rewritten by the author</summary>

<br>

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `unbreakable-sentence` | A sentence over the width with no clause comma, a break that would split a list, or a summary that does not fit one line | Rewrite | `error` | None |
| `stub-fragment` | A forced break that leaves a line too short to read as a clause | Rewrite | `warning` | `minimum_characters` (24) |

Reflow reads the same `minimum_characters` floor, so a fix never lays out a stub that `stub-fragment` then rejects.

</details>

<details>
<summary><b>Structure</b>: where documentation lives and how much of it there is</summary>

<br>

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `plain-comment-on-public` | A public symbol documented with a plain comment instead of a docstring or JSDoc block | Rewrite | `error` | None |
| `signature-restating-tag` | A doc comment section that restates types the signature already carries, such as `Args:` or `@param` | Rewrite | `error` | None |
| `file-header-comment` | A banner comment opening the file before its first declaration | Rewrite | `warning` | None |
| `block-too-long` | A comment block long enough to restate the code below it | Rewrite | `warning` | `line` (4), `doc-internal` (13), `doc-public` (20) |

The `block-too-long` limits are line counts, set from the 95th percentile of a measured corpus. `subedit stats` reports the same percentiles for your codebase.

A plain comment right under another declaration may head a group rather than document one symbol, so `plain-comment-on-public` reports that case as a warning.

</details>

<details>
<summary><b>Wording</b>: the bundled Vale style, rewritten by the author</summary>

<br>

These rules run when Vale is installed, and only in a repository without its own `.vale.ini`. A repository with one runs its own styles instead, and their findings join the same report.

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `subedit.EmDash` | An em dash, an en dash, or an arrow in prose | Rewrite | `error` | None |
| `subedit.Semicolon` | A semicolon joining two clauses | Rewrite | `error` | None |
| `subedit.Ellipsis` | A list that trails off with an ellipsis or its Latin abbreviation, in place of named examples | Rewrite | `error` | None |
| `subedit.EditHistory` | Narration of how the code behaved before a change, instead of the constraint it holds now | Rewrite | `error` | None |
| `subedit.SignatureTag` | A tag that restates the signature, matched by text | Rewrite | `error` | None |
| `subedit.ExternalRef` | An identifier shaped like a ticket number a reader may not be able to open | Rewrite | `warning` | None |
| `subedit.DateRef` | A date that records when something changed | Rewrite | `warning` | None |
| `subedit.MidSentenceColon` | A colon joining clauses in code comments | Rewrite | `warning` | None |
| `subedit.MidSentenceColonMarkup` | The same check for Markdown, with markup taken into account | Rewrite | `warning` | None |

Standards such as `UTF-8` and `SHA-256` are exempt from `subedit.ExternalRef`. The `subedit:judging-findings` skill gives an agent the criteria for these judgment calls.

</details>

<details>
<summary><b>Spacing</b>: AutoCorrect, autofixed</summary>

<br>

| Rule | Catches | Fix Kind | Default | Options |
| --- | --- | --- | --- | --- |
| `autocorrect.Spacing` | Missing spaces and wrong punctuation width between CJK and Latin text | Targeted | `error` | `.autocorrectrc` |

AutoCorrect arrives as a Python dependency, so it runs wherever `subedit` does, unless `--no-delegate` is passed. It reads `.autocorrectrc` from the working directory for its own settings.

</details>

The generated [rule reference](docs/rules.md) lists the native rules straight from their metadata, and `subedit rules` prints the same table.

### Surfaces

A surface is a kind of file where prose lives. Every surface goes through the same pipeline.

| Surface | Status | Focus |
| --- | --- | --- |
| Code comments and docstrings | Available | Layout, because a comment must fit a column limit |
| Markdown | Planned | Structure, such as headings and lists, because Markdown text wraps on its own |

Editor diagnostics over LSP are planned as well, so the same findings show as you type ([#19](https://github.com/mroops0111/subedit/issues/19)).

#### Languages

Each language is a profile that knows its comment forms, its doc comment, and what counts as public.

| Language | Files | Doc Comment | Public Symbol |
| --- | --- | --- | --- |
| Python | `.py`, `.pyi` | Docstring, `"""` | A name without a leading underscore |
| TypeScript | `.ts`, `.mts`, `.cts`, `.tsx` | JSDoc, `/** */` | An exported symbol, and its members unless `private`, `protected`, or `#named` |

<details>
<summary><b>Content Left Alone</b>: what every profile skips</summary>

<br>

- **Commented-Out Code**: a comment line the language's own grammar reads as code, such as `// return result` or `# client.send(`, is left as written.
- **Doc Sections**: a docstring's sections from `Args:`, `Parameters`, or `:param` onward, and a JSDoc block's tags from the first one such as `@throws` onward, are left as written. A JSDoc block keeps its frame when reflowed.
- **Directives**: a directive such as `// eslint-disable-next-line` or `# type: ignore` carries no prose, so nothing reads it.
- **Plain Blocks**: a plain `/* */` block is read by Vale only, with no layout applied.
- **String Literals**: AutoCorrect edits are kept only inside comment prose, so a string in code is never changed.
- **Group Headings**: a plain comment opening a paragraph over several declarations heads them as a group, so it documents none of them.

</details>

## License

[MIT](LICENSE)
