# Dashboard Skills

This directory vendors the dashboard-specific Hermes skills that are useful when editing this repository. They are copied from `~/.hermes/skills/software-development/` so dashboard contributors can use the same checklists even outside the local Hermes skill store.

## Included skills

- [`dashboard-add-tab.md`](dashboard-add-tab.md) — end-to-end recipe for adding a brand-new dashboard tab.
- [`dashboard-route-nav-patching.md`](dashboard-route-nav-patching.md) — route/nav/header mismatch checklist and verification notes.
- [`dashboard-games-watch-integration.md`](dashboard-games-watch-integration.md) — Games tab watch-server/proxy integration pattern.

## Maintenance

When a local skill changes, refresh the matching file here before committing dashboard work:

```bash
cp ~/.hermes/skills/software-development/dashboard-add-tab/SKILL.md docs/skills/dashboard-add-tab.md
cp ~/.hermes/skills/software-development/dashboard-route-nav-patching/SKILL.md docs/skills/dashboard-route-nav-patching.md
cp ~/.hermes/skills/software-development/dashboard-games-watch-integration/SKILL.md docs/skills/dashboard-games-watch-integration.md
```
