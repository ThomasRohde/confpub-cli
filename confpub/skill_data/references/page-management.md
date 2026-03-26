# Page Management: Comments, Properties, Attachments, Labels, History

Beyond publishing, confpub provides full CRUD for Confluence page resources. These commands are useful for automation, governance workflows, and agent-driven documentation management.

## Comments

Add and list page comments. Comment body supports Markdown (converted to storage format).

```bash
# List comments on a page
python -m confpub comment list --page-id 123456

# Add a comment with inline text
python -m confpub comment add --page-id 123456 --text "Reviewed and approved. {status:Approved|colour=Green}"

# Add a comment from a Markdown file
python -m confpub comment add --page-id 123456 --file review-feedback.md
```

Use cases:
- Automated review comments after CI/CD publishing
- Agent-driven feedback loops on documentation
- Governance stamps ("Published by confpub at {timestamp}")

## Page Properties

Key-value metadata on pages. Properties are invisible to readers but queryable via CQL and useful for automation.

```bash
# List all properties
python -m confpub property list --page-id 123456

# Get a specific property
python -m confpub property get --page-id 123456 --key "review-status"

# Set a property (plain text or JSON)
python -m confpub property set --page-id 123456 --key "review-status" --value "approved"
python -m confpub property set --page-id 123456 --key "metadata" --value '{"owner": "squad-atlas", "tier": 1}'

# Delete a property
python -m confpub property delete --page-id 123456 --key "review-status"
```

Use cases:
- Track document lifecycle state (`draft` → `reviewed` → `approved`)
- Store structured metadata (owner, team, tier, SLA)
- Build automation: CQL queries can filter by property values
- Version-independent metadata that persists across page updates

## Attachments

Upload, download, list, and delete file attachments on pages.

```bash
# List attachments
python -m confpub attachment list --page-id 123456

# Upload a file
python -m confpub attachment upload diagram.png --page-id 123456

# Download an attachment
python -m confpub attachment download --page-id 123456 --filename "diagram.png" --output ./downloads/diagram.png

# Delete an attachment
python -m confpub attachment delete --page-id 123456 --filename "diagram.png"
```

Note: When publishing Markdown with images (`![](image.png)`), confpub handles attachment upload and URL rewriting automatically. Manual attachment commands are for managing files outside the publish workflow.

## Labels

Organize pages with labels for discoverability and filtering.

```bash
# List labels on a page
python -m confpub label list --page-id 123456

# Add labels (repeatable flag)
python -m confpub label add --page-id 123456 --label architecture --label approved

# Remove labels
python -m confpub label remove --page-id 123456 --label draft
```

Labels are also settable during publish (`--label` flag) and in manifests. These commands are for managing labels independently of publishing.

## Page History & Versions

Inspect page version history, retrieve specific versions, and export pages.

```bash
# View version history
python -m confpub page history --page-id 123456

# Get a specific version's content
python -m confpub page version --page-id 123456 --version-number 3

# Export as PDF or Word
python -m confpub page export --page-id 123456 --format pdf --output page.pdf
python -m confpub page export --page-id 123456 --format word --output page.docx
```

## Page Operations

```bash
# Inspect a page (get metadata and content)
python -m confpub page inspect --space SD --title "Architecture Overview"
python -m confpub page inspect --page-id 123456 --format markdown  # convert to Markdown
python -m confpub page inspect --page-id 123456 --raw              # full API response

# Move a page to a new parent
python -m confpub page move --page-id 123456 --target-parent "New Parent"

# Delete a page (with optional cascade to children)
python -m confpub page delete --space SD --title "Old Page"
python -m confpub page delete --page-id 123456 --cascade

# Pull a page tree to local Markdown
python -m confpub page pull --space SD --title "Engineering" --recursive --output docs/
```

## Search

Find pages across spaces using CQL (Confluence Query Language) or simple filters.

```bash
# Search by title
python -m confpub search --title "Architecture" --space SD

# Raw CQL query
python -m confpub search --cql "label = 'adr' AND space = 'SD'"
python -m confpub search --cql "type = 'page' AND lastModified > '2026-03-01'"

# Filter by type
python -m confpub search --space SD --type page --limit 50
```

## Space Operations

```bash
# List all accessible spaces
python -m confpub space list

# Get detailed space info (homepage, description)
python -m confpub space inspect --space SD
```

## Governance Automation Pattern

Combine these commands for automated documentation governance:

```bash
# After publishing, stamp the page with metadata
PAGE_ID=$(python -m confpub page publish doc.md --space SD | jq -r '.result.changes[0].confluence_page_id')

# Set properties for tracking
python -m confpub property set --page-id $PAGE_ID --key "published-by" --value "ci-pipeline"
python -m confpub property set --page-id $PAGE_ID --key "publish-date" --value "2026-03-26"

# Add a review comment
python -m confpub comment add --page-id $PAGE_ID --text "Auto-published from main branch, commit abc1234."

# Apply governance labels
python -m confpub label add --page-id $PAGE_ID --label auto-published --label needs-review
```
