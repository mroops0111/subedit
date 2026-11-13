---
name: settings
description: Set up a project's subedit config from what its repository already writes and what its author prefers. Use when a project adopts subedit, when the user asks to tune subedit's limits, levels, or conventions, or when subedit reports so many findings on existing prose that its defaults seem not to fit.
---

# subedit Settings

subedit's defaults come from a standard where one exists, and otherwise from judgment. This skill measures the repository, walks the author through each kind of setting in a fixed order, and writes only the values that differ from the defaults. It never rewrites prose. Findings that remain afterwards belong to the `rewrites` skill.

## Gathering

Collect everything the discussion draws on before asking anything. Run each command from the repository root.

1. **Measurements**: `subedit stats . --commits 200 --output json`. Each surface lists its widths, its sentences that cannot break at each candidate width, and an `options` entry for every count a rule takes, with its `default`, the project's `setting`, and the distribution of what the repository holds.
2. **Findings**: `subedit check . --no-delegate --output json`, which prints one JSON object per file. Count the findings by `rule`, and keep the count that needs an author apart, where `mechanical` is false.
3. **Existing Config**: read `subedit.toml`, or `[tool.subedit]` in `pyproject.toml`. Read the width other tools set too, such as ruff's `line-length`, Prettier's `printWidth`, and `max_line_length` in `.editorconfig`.
4. **Surfaces**: note which of `comments`, `markdown`, and `commit-messages` the measurements hold. Leave out every setting of a surface the repository does not have.

Drop `--commits` outside a git repository. Run `subedit rules` when a rule's purpose is unclear.

## Rounds

Discuss one category per round, in this order, since an earlier answer changes what a later one means. Skip a round that has nothing to decide.

| Round | Category | Settings | Evidence |
| --- | --- | --- | --- |
| 1 | Width | `[subedit] line-width`, `[surfaces.<name>] line-width` | `physical_widths`, `unbreakable_sentences_by_width`, the width other tools set |
| 2 | Length Limits | `comment-too-long` line counts, `max-subject-characters` | Option distributions |
| 3 | Line Breaks | `min-line-characters`, `max-item-words` | Option distributions |
| 4 | Labels | `max-label-words`, `max-bold-label-words`, `max-full-width-label-characters`, `max-tag-words` | Option distributions |
| 5 | Conventions | Title Case `style`, heading `levels`, `exceptions`, `parenthesis-style`, `subject-style` and `types`, `discouraged-word` replacements, `abbreviations`, `exclude` | Findings, commit subjects, and the author |
| 6 | Levels | Each rule as `error`, `warning`, or `off`, and each surface on or off | Findings by rule |

## Round Format

Every round has the same three parts, written in the language the user writes in.

1. **Lead**: one sentence on what the category governs.
2. **Table**: one row per setting, with these columns.

   | Setting | Default | Now | Repository | Findings | Suggested |
   | --- | --- | --- | --- | --- | --- |
   | `max-plain-lines` | 4 | 4 | p50 1, p95 2, max 4 | 0 | 4, kept |

   For a maximum, Repository gives p50, p95, and max. For a minimum, such as `min-line-characters`, it gives min, p5, and p50. Findings is the count of findings of the rule the setting belongs to.
3. **Questions**: one AskUserQuestion call per round, with one question per setting that has a choice to make, and at most four per call. A round with more settings takes further calls.

Each question follows the same shape.

- **Header**: the setting's name, cut to fit.
- **Options**: the suggested value first, labelled `(Recommended)` and explained by the measurement behind it. Then the default when it differs, and one stricter or looser value where it helps. AskUserQuestion adds Other for a value of the author's own, so never add one.
- **No Evidence**: where the data cannot decide, as with a Title Case standard, list the choices with what each changes and mark none recommended.

Wait for the answers before the next round.

## Suggestions

Derive each suggestion by these rules, so the same repository always gets the same suggestion.

- **Maximum**: keep the default when the repository's p95 fits within it. Otherwise suggest the p95, never past the max. What still lies beyond is prose worth rewriting, not a reason to raise the limit further.
- **Minimum**: keep the default when the repository's p5 is at or above it. Otherwise suggest the p5.
- **Width**: match the width another tool already sets. Without one, suggest the narrowest candidate width that leaves under 1% of sentences unable to break. A commit message keeps git's 72 unless the history runs wider at p95.
- **Commit Style**: suggest `conventional` when most recent subjects open with a type such as `feat:`, and list the types they use. Otherwise suggest `git`.
- **Exceptions**: suggest a word for `exceptions` only when the Title Case findings flag a name the project writes in lowercase, such as a product or a command.
- **Exclude**: suggest a path only when its findings are many and it holds prose nobody writes by hand, such as generated docs or test fixtures.
- **Levels**: list only the rules with findings, with the count and one example message in each option's description. Ask with `multiSelect`, as one question for rules to set to `warning` and one for rules to switch `off`, four rules per question. Recommend nothing, since how strict to be is the author's call.

## Writing

Close the discussion in three steps.

1. **Summary**: show one table of every setting that will differ from the default, with its value and the measurement or answer behind it. Ask to confirm it, and where no config exists yet, whether it goes in `subedit.toml` or under `[tool.subedit]` in `pyproject.toml`. An existing config is where it goes.
2. **Config**: write only the values that differ from the defaults, grouped as the README's configuration section shows. Put a one-line comment above each group naming the measurement or answer it came from. Keep every setting the existing config already holds unless the author changed it.
3. **Result**: run `subedit check . --no-delegate --output json` again, and show a table of each rule's findings before and after. Point the user to `subedit fix . --write` for the mechanical fixes and to the `rewrites` skill for the rest.

## Boundaries

The skill sets subedit up and leaves everything else alone.

- **Prose**: never rewrite or fix prose during setup, since the counts the discussion rests on would shift under it.
- **Scope**: write only subedit's config. Leave the formatter, the CI, and the hooks to their own steps.
- **Recounts**: findings are counted once, before the rounds, so a later round's counts do not yet reflect an earlier answer. Say so when an earlier answer, such as a new width, plainly changes them.
