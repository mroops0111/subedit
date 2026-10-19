# subedit

Your house style, enforced in the places prose hides inside a codebase.

A subeditor is the person at a publication who makes every piece of copy match its house style. `subedit` does that job for the prose in your code.

Linters check your code. Almost nothing checks the sentences you write around it. `subedit` reads the comments and docstrings in your source, lays them out one sentence per line, and only tells you about the sentences a tool cannot fix for you.

## Example

An editor wraps a comment at whatever column it reaches, so sentences break mid clause.

```python
    # Cap the buffer at the runner limit, because an unbounded
    # read faults the job. Retry once, then give up.
```

`subedit fix --write` repairs the layout and says nothing.

```python
    # Cap the buffer at the runner limit, because an unbounded read faults the job.
    # Retry once, then give up.
```

A sentence that runs past the width with no comma has nowhere legal to break, and only its author knows where the meaning divides. That one comes back to you, or to the agent that wrote it.

```text
1 comment finding needs rewriting in src/cache.py.
Each states the fix. Apply it in place, do not add a suppression comment.

line 2  [unbreakable-sentence]
  This sentence runs to 116 characters against a budget of 114 characters and contains no comma, so there is no legal place to break it. Add a comma at a clause boundary, or split it into two sentences.
```

## Installation

Install the command line tool from PyPI.

```bash
uv tool install subedit
```

`pipx install subedit` and `pip install subedit` work as well. Add the `vale` extra, as in `uv tool install 'subedit[vale]'`, to have Vale fetched for you.

## Commands

Every command takes files or directories.

| Command | Result |
| --- | --- |
| `subedit check src/` | every finding |
| `subedit check src/ --output=actionable` | only the sentences that need rewriting |
| `subedit fix src/` | the repairs, as a diff |
| `subedit fix src/ --write` | the repairs, applied |
| `subedit stats src/` | comment shapes across the codebase, for setting thresholds from data |
| `subedit rules` | every rule and who resolves it |

`check` and `fix` exit 1 while anything needs an author, so they drop into pre-commit or CI as they are.

## Fix Kinds

Every finding says who can resolve it, and the whole design turns on that answer.

| Kind | Resolved by | Reaches you |
| --- | --- | --- |
| `TARGETED` | the tool, silently | no |
| `REFLOW` | the tool, silently | no |
| `REWRITE` | only the author | yes |

Rewriting a sentence needs its meaning, which a deterministic process cannot supply. Everything else is repaired without a word, because each message costs the reader attention.

## Agent Hook

`subedit-hook` runs after every file an agent edits. It repairs the mechanical findings in place, and exits 2 only when a sentence needs rewriting, which hands the message back to the model. In Claude Code a warning reaches the model too, as context beside the tool result, without blocking the edit.

### Claude Code

The plugin needs only [uv](https://docs.astral.sh/uv/). It runs subedit from PyPI with the `vale` extra, and warms that environment in the background when a session starts, so no edit waits on the first download.

It also ships the `subedit:judging-findings` skill, which gives the model the criteria for every finding a tool cannot fix, such as when a spec identifier stays and a ticket number goes. Criteria in your `CLAUDE.md`, `AGENTS.md`, or a skill of your own come first.

```text
/plugin marketplace add mroops0111/subedit
/plugin install subedit@mroops
```

To register it by hand instead, add this to `.claude/settings.json`.

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

### Codex

Add this to `~/.codex/hooks.json`.

```json
{
  "hooks": {
    "PostToolUse": [{ "command": "subedit-hook" }]
  }
}
```

### Several Agents

Registering the hook with both agents is the normal case. Each agent names its edit tools differently, so every payload identifies its sender, and a payload from anything else exits 0 untouched. `subedit-hook --help` prints the payload shapes it accepts.

## Languages

| Language | Files | Doc comment | Width read from |
| --- | --- | --- | --- |
| Python | `.py`, `.pyi` | `"""` docstring | `line-length` for ruff or black |
| TypeScript | `.ts`, `.mts`, `.cts`, `.tsx` | `/** */` JSDoc | `printWidth` for Prettier, `lineWidth` for Biome |

A TypeScript symbol is public when it is exported, and a class member stays public unless it is `private`, `protected`, or `#named`.
A plain comment opening a paragraph over several declarations heads them as a group, so it documents none of them. One right under another declaration may be either, so `plain-comment-on-public` reports it as a warning.
A JSDoc block keeps its frame when reflowed. Its tag section, from the first tag such as `@throws` onward, is left as written, as a docstring's sections from `Args:`, `Parameters`, or `:param` onward are.
A comment line that the language's own grammar reads as code, such as `// return result` or `# client.send(`, is left as written in either language.
A plain `/* */` block and a directive such as `// eslint-disable-next-line` carry no prose for subedit to lay out, so only Vale reads the block, and nothing reads the directive.
A directory walk skips dotted directories such as `.venv`, and the package directories each language installs into, such as `node_modules` or `venv`.

## Configuration

Settings come from `subedit.toml`, or from `[tool.subedit]` in `pyproject.toml`, whichever sits closest above the file being checked.

```toml
[subedit]
line-width = 100
exclude = ["tests/fixtures/**"]

[rules]
mid-clause-break = "error"
block-too-long = { severity = "warning", line = 3, doc-public = 20 }
```

Left unset, `line-width` follows the project's formatter, from the config the formatter would read for that file, and is 120 where no formatter sets one.

Rule names describe the problem they report. `docs/rules.md` lists every rule, generated from the rules themselves.

A rule at `error` fails `check` and stops an agent, while one at `warning` is shown as advice and blocks nothing. The same table sets the delegated Vale rules by name.

```toml
[rules]
"subedit.MidSentenceColon" = "error"
"subedit.DateRef" = "off"
```

## Delegated Tools

`check`, `fix`, and the agent hook also run two tools, and fold their findings into the same report.

- **Vale**: punctuation, banned phrasing, and anything a markup aware prose linter already handles. Vale has no autofix, so its findings come back as rewrites. It runs where it is installed, or where the `vale` extra fetched it. A repository without its own `.vale.ini` gets the style that ships with subedit, whose rules are named `subedit.*`.
- **AutoCorrect**: spacing and punctuation width between CJK and Latin text. Its corrections are applied silently, like any other mechanical fix. It arrives as a Python dependency, and reads `.autocorrectrc` from the working directory.

`--no-delegate` skips both for `check` and `fix`.

## Surfaces

Code comments are the first surface, and Markdown comes next.

| Surface | Status | Mostly enforces |
| --- | --- | --- |
| Code comments and docstrings | working | layout, since comments sit inside a column limit |
| Markdown | planned | structure, since soft wrapped text barely needs layout |
| Markdown slides | planned | Markdown, with front matter left as it is |

## Related Tools

`subedit` covers the one thing the usual linters and type checkers leave alone.

| Tool | Checks |
| --- | --- |
| ruff, ESLint | code structure |
| basedpyright, tsc | types |
| **subedit** | **the natural language inside source** |

## License

MIT
