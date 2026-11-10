---
name: checking-drafts
description: Check text that never lands in a file with subedit before it is published, such as a pull request or issue body, a pull request title, a release note, or a review comment. Use before running gh pr create, gh pr edit, gh issue create, gh release create, or any command that posts prose, in a repository that configures subedit.
---

# Check subedit Drafts

The subedit hook reads the files an agent edits and the commits it makes. Text passed straight to a command, such as a pull request body, never lands in a file the hook reads, so check it yourself before it is published.

## Steps

Pipe the draft through `subedit fix -`, and post what comes back.

1. Write the draft, then run `subedit fix - --stdin-filename <name>` on it. Run it from the repository, so the draft takes the repository's config.
2. Name the draft by the surface it is read as. A body or a note is Markdown, such as `pr.md`, and a title becomes a commit subject when the pull request is squashed, so it is `.git/COMMIT_EDITMSG`.
3. Read the findings on stderr. Rewrite what needs an author, and judge each warning with the `judging-findings` skill.
4. Post the fixed text from stdout, such as through `gh pr create --body-file -`, once no finding needs an author.

```sh
subedit fix - --stdin-filename pr.md < pr.md | gh pr edit 42 --body-file -
echo "Read a draft from stdin" | subedit check - --stdin-filename .git/COMMIT_EDITMSG
```

## Projects Without subedit

Skip the check where neither `subedit.toml` nor a `[tool.subedit]` table in `pyproject.toml` configures subedit. The draft would only be measured against defaults the project never chose.
