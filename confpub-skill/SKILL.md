---
name: confpub-publishing
description: Create and publish professional Confluence pages using the confpub CLI. Use this skill whenever the user wants to create, write, publish, update, or manage Confluence documentation — including architecture decision records (ADRs), technical designs, runbooks, project dashboards, sprint status pages, meeting notes, retrospectives, RFCs, incident post-mortems, or any enterprise documentation. Also triggers when the user mentions confpub, Confluence publishing, "publish to Confluence", "create a Confluence page", documentation-as-code workflows, or wants to convert Markdown to Confluence storage format. Even if the user doesn't mention confpub by name but asks to "publish docs", "update the wiki", or "create documentation", this skill applies when confpub is installed in the project.
---

# Confluence Publishing with confpub

You are an expert at creating professional Confluence pages using confpub. You write Markdown that leverages confpub's extended syntax to produce pages that look native to Confluence — not like pasted Markdown.

## Design Philosophy

Great Confluence pages let readers scan — they never force anyone to read paragraphs to find status or decisions.

1. **Lead with context** — Open every page with a panel stating why this page exists, who owns it, and its current status. A reader decides in 3 seconds whether to keep reading.
2. **Containers for scanning** — Panels for key info, expand blocks for skippable details, admonitions for warnings. Never bury critical information in a paragraph.
3. **Status lozenges are free** — Use `{status:Title|colour=Color}` inline everywhere: headings, table cells, metadata panels. Colors: `Green`, `Yellow`, `Red`, `Blue`, `Purple`.
4. **Tables over prose** — If describing 2+ items with the same attributes, use a table.
5. **Task lists for actions** — Never list action items as bullets. Use `- [ ]` / `- [x]` so they're trackable.
6. **Labels for discoverability** — Every page gets labels: type (`adr`, `runbook`), domain (`payments`, `infra`), lifecycle (`draft`, `approved`).
7. **Link, don't duplicate** — Use `{include:Page Title}` or `[Link Text](Page Title)` for cross-references.

## Quick Publishing Workflow

```bash
# Single page
python -m confpub page publish page.md --space SD --parent "Engineering" --label adr

# Multi-page tree
python -m confpub plan create --manifest confpub.yaml
python -m confpub plan apply --plan confpub-plan.json

# Always dry-run first for safety
python -m confpub page publish page.md --space SD --dry-run
```

For manifest structure, labels strategy, and advanced publishing workflows, read `references/workflow.md`.

## Syntax Cheat Sheet

The essentials — for full syntax with examples, see the routing table below.

| Feature | Syntax |
|---------|--------|
| Status lozenge | `{status:Done\|colour=Green}` (escape `\|` in tables!) |
| Info box | `> [!NOTE]` / `> [!TIP]` / `> [!WARNING]` / `> [!CAUTION]` |
| Panel | `::: panel Title` ... `:::` |
| Expand | `::: expand Title` ... `:::` |
| Layout | `:::: layout two-equal` + `::: cell` ... `:::` per column |
| Excerpt | `::: excerpt` ... `:::` |
| Task list | `- [ ] unchecked` / `- [x] checked` |
| TOC | `{toc}` or `{toc:maxLevel=3}` |
| Children | `{children}` |
| Jira link | `{jira:PROJ-123}` |
| Jira query | `{jira:jql=project=PROJ AND status=Open}` |
| Include page | `{include:Page Title}` |
| Page link | `[text](Page Title)` |
| HTML block | `::: html` ... `:::` |

Layout types: `single`, `two-equal`, `two-three`, `three-equal`, `three-two-three`

**Critical: pipe escaping in tables.** The `|` character in macro parameters (like `{status:Done|colour=Green}`) conflicts with Markdown table column delimiters. Inside table cells, always escape the pipe: `{status:Done\|colour=Green}`. Outside tables (headings, paragraphs, layout cells), no escaping is needed.

## Routing Table

Read the reference file that matches the user's need. Load only what's relevant — never load all references at once.

### Document Templates

When the user asks to create a specific document type, read the matching pattern file:

| User Intent | Read |
|-------------|------|
| Architecture Decision Record | `references/patterns/adr.md` |
| Technical Design Document | `references/patterns/design-doc.md` |
| RFC / Proposal | `references/patterns/rfc.md` |
| Runbook / Playbook | `references/patterns/runbook.md` |
| Incident Post-Mortem | `references/patterns/post-mortem.md` |
| Sprint / Iteration Status | `references/patterns/sprint-status.md` |
| Retrospective | `references/patterns/retrospective.md` |
| Release Notes / Changelog | `references/patterns/release-notes.md` |
| RAID Log | `references/patterns/raid-log.md` |
| Service Catalog Entry | `references/patterns/service-catalog.md` |
| Meeting Notes | `references/patterns/meeting-notes.md` |
| Change Request | `references/patterns/change-request.md` |
| Onboarding Guide | `references/patterns/onboarding.md` |
| API Documentation | `references/patterns/api-docs.md` |

### Syntax Deep-Dives

When the user asks about specific confpub features or needs detailed syntax:

| User Intent | Read |
|-------------|------|
| Panels, expand blocks, admonitions, excerpts | `references/syntax-containers.md` |
| Status lozenges, TOC, children, Jira, anchors, includes | `references/syntax-macros.md` |
| Code blocks, math, footnotes, definition lists, task lists, front-matter | `references/syntax-formatting.md` |
| Raw HTML embedding, custom scripts/styles | `references/syntax-html-macro.md` |

### Visual Design

When the user wants professional-looking pages, dashboards, or custom styling:

| User Intent | Read |
|-------------|------|
| Multi-column layouts, composition patterns | `references/layouts.md` |
| KPI cards, status boards, timelines via HTML | `references/design-styling.md` |
| Container selection, nesting rules, page structure | `references/design-principles.md` |

### Page Management & API

When the user asks about managing existing pages or Confluence operations beyond publishing:

| User Intent | Read |
|-------------|------|
| Comments, properties, attachments, labels, history, search, export | `references/page-management.md` |

### Publishing Workflow

When the user asks about publishing, manifests, labels, or lockfiles:

| User Intent | Read |
|-------------|------|
| Manifests, labels strategy, multi-page workflows, error recovery | `references/workflow.md` |
