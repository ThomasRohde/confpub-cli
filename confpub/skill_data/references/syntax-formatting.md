# Formatting: Code, Math, Footnotes, Definitions, Tasks, Front-Matter

## Code Blocks

Fenced code with language → Confluence code macro with syntax highlighting.

````markdown
```python
def publish(title: str, content: str) -> dict:
    return client.create_page(space, title, content)
```

```sql
SELECT u.name, COUNT(o.id) AS order_count
FROM users u JOIN orders o ON o.user_id = u.id
GROUP BY u.name HAVING COUNT(o.id) > 10;
```
````

Supported languages include `python`, `java`, `javascript`, `typescript`, `sql`, `yaml`, `json`, `bash`, `go`, `rust`, `csharp`, `ruby`, `xml`, `html`, `css`, and many more.

## Task Lists

Native Confluence checklists with trackable checkboxes.

```markdown
- [ ] Design the API schema
- [ ] Write integration tests
- [x] Set up CI pipeline
- [x] Security review complete
```

Nested tasks:
```markdown
- [ ] Phase 1: Foundation
  - [x] Database schema
  - [ ] API endpoints
  - [ ] Authentication
- [ ] Phase 2: Features
  - [ ] Search
  - [ ] Notifications
```

## Math

LaTeX math via dollar signs.

**Inline:** `The energy is $E = mc^2$ where $m$ is mass.`

**Block:**
```markdown
$$
\int_0^\infty e^{-x^2} dx = \frac{\sqrt{\pi}}{2}
$$
```

## Definition Lists

Term-definition pairs.

```markdown
Confluence
: A team wiki and collaboration platform by Atlassian.

confpub
: An agent-first CLI for publishing Markdown to Confluence.

Storage Format
: Confluence's native XHTML representation of page content.
```

## Footnotes

```markdown
This claim needs a source[^1] and this one too[^2].

[^1]: Source: Internal architecture review, March 2026.
[^2]: Based on load testing results from sprint 14.
```

Footnotes collect at the page bottom with automatic back-links.

## Front-Matter

YAML front-matter at the top of a Markdown file. Stripped during conversion — not published as content.

```yaml
---
title: "My Custom Title"
space: SD
parent: "Engineering Docs"
labels:
  - architecture
  - approved
html_macro_name: macro-html
page_id: "123456"
---
```

**Field precedence:** CLI flags > front-matter > manifest values > filename inference.

**Title derivation order:**
1. `--title` CLI flag
2. `--title-from-h1` (first `# Heading`)
3. `title` in front-matter
4. Filename stem (hyphens/underscores → spaces, title-cased)
