---
name: git-conventions
description: >-
  Git commit and PR conventions for marrow-core. Gitmoji prefixes,
  commit message format, and PR title format.
---

## Commit Format

```
<gitmoji> <type>: <description>
```

| Gitmoji | Type       | When to use                          |
|---------|------------|--------------------------------------|
| 🎉      | `init`     | Initial commit / project scaffolding |
| ✨      | `feat`     | New feature or capability            |
| 🐛      | `fix`      | Bug fix                              |
| 📝      | `docs`     | Documentation only                   |
| ♻️      | `refactor` | Code refactoring (no behavior change)|
| 🔧      | `chore`    | Config, tooling, or maintenance      |
| ✅      | `test`     | Add or update tests                  |
| 🔥      | `remove`   | Remove code or files                 |
| 🎨      | `style`    | Code style / formatting              |
| 🚀      | `deploy`   | Deployment related changes           |

## Examples

```
✨ feat: add checkpoint auto-pruning for artisan
🐛 fix: use loguru {} format instead of stdlib % format
📝 docs: update AGENTS.md with commit conventions
🎨 style: fix trailing blank line in test_runner.py
```

## PR Titles

Same format as commit messages:

```
✨ feat: add analyst, reviewer, watchdog agents for 5-agent expansion
```

## Rules

- One gitmoji per commit — pick the **most accurate** type
- Description is lowercase, imperative mood, no trailing period
- Keep description under 72 characters
- Body (if needed) explains *why*, not *what*
