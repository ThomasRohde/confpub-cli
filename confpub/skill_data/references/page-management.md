# Page Management: Browse, Comment, Properties, Attachments, Labels, History

Beyond publishing, confpub provides full CRUD for Confluence page resources. These commands are useful for automation, governance workflows, and agent-driven documentation management.

## Browsing Pages

```bash
# List pages in a space (paginated)
confpub page list --space SD --limit 25

# Filter by title substring
confpub page list --space SD --title "Architecture"

# Filter by label
confpub page list --space SD --label "adr"

# Paginate through results
confpub page list --space SD --start 25 --limit 25
```

## Comments

Add and list page comments. Comment body supports Markdown (converted to storage format).

```bash
# List comments on a page
confpub comment list --page-id 123456

# Add a comment with inline text
confpub comment add --page-id 123456 --text "Reviewed and approved. {status:Approved|colour=Green}"

# Add a comment from a Markdown file
confpub comment add --page-id 123456 --file review-feedback.md
```

Use cases:
- Automated review comments after CI/CD publishing
- Agent-driven feedback loops on documentation
- Governance stamps ("Published by confpub at {timestamp}")

## Page Properties

Key-value metadata on pages. Properties are invisible to readers but queryable via CQL and useful for automation.

```bash
# List all properties
confpub property list --page-id 123456

# Get a specific property
confpub property get --page-id 123456 --key "review-status"

# Set a property (plain text or JSON)
confpub property set --page-id 123456 --key "review-status" --value "approved"
confpub property set --page-id 123456 --key "metadata" --value '{"owner": "squad-atlas", "tier": 1}'

# Delete a property
confpub property delete --page-id 123456 --key "review-status"
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
confpub attachment list --page-id 123456

# Upload a file
confpub attachment upload diagram.png --page-id 123456

# Download an attachment
confpub attachment download --page-id 123456 --filename "diagram.png" --output ./downloads/diagram.png

# Delete an attachment
confpub attachment delete --page-id 123456 --filename "diagram.png"
```

Note: When publishing Markdown with images (`![](image.png)`), confpub handles attachment upload and URL rewriting automatically. Manual attachment commands are for managing files outside the publish workflow.

## Labels

Organize pages with labels for discoverability and filtering.

```bash
# List labels on a page
confpub label list --page-id 123456

# Add labels (repeatable flag)
confpub label add --page-id 123456 --label architecture --label approved

# Remove labels
confpub label remove --page-id 123456 --label draft
```

Labels are also settable during publish (`--label` flag) and in manifests. These commands are for managing labels independently of publishing.

## Page History & Versions

Inspect page version history, retrieve specific versions, and export pages.

```bash
# View version history
confpub page history --page-id 123456

# Get a specific version's content
confpub page version --page-id 123456 --version-number 3

# Export as PDF or Word
confpub page export --page-id 123456 --format pdf --output page.pdf
confpub page export --page-id 123456 --format word --output page.docx
```

## Page Operations

```bash
# Inspect a page (get metadata and content)
confpub page inspect --space SD --title "Architecture Overview"
confpub page inspect --page-id 123456 --format markdown  # convert to Markdown
confpub page inspect --page-id 123456 --raw              # full API response

# Move a page to a new parent (by title or by ID)
confpub page move --page-id 123456 --target-parent "New Parent" --space SD
confpub page move --page-id 123456 --target-parent-id 789012

# Delete a page (with optional cascade to children)
confpub page delete --space SD --title "Old Page"
confpub page delete --page-id 123456 --cascade

# Pull a page tree to local Markdown
confpub page pull --space SD --title "Engineering" --recursive --output docs/

# Pull with nested directory layout (mirrors page hierarchy)
confpub page pull --space SD --title "Engineering" --recursive --layout nested --output docs/

# Pull without downloading attachments
confpub page pull --page-id 123456 --no-attachments --output docs/
```

## Search

Find pages across spaces using CQL (Confluence Query Language) or simple filters.

```bash
# Search by title
confpub search --title "Architecture" --space SD

# Raw CQL query
confpub search --cql "label = 'adr' AND space = 'SD'"
confpub search --cql "type = 'page' AND lastModified > '2026-03-01'"

# Filter by type, with pagination
confpub search --space SD --type page --limit 50 --start 0

# Include archived spaces in results
confpub search --space SD --title "legacy" --include-archived

# Control excerpt length (0 = unlimited)
confpub search --cql "label = 'runbook'" --excerpt-length 500
```

## Space Operations

```bash
# List all accessible spaces
confpub space list

# Get detailed space info (homepage, description)
confpub space inspect --space SD
```

## Governance Automation Pattern

Combine these commands for automated documentation governance:

```bash
# After publishing, stamp the page with metadata
PAGE_ID=$(confpub page publish doc.md --space SD | jq -r '.result.changes[0].confluence_page_id')

# Set properties for tracking
confpub property set --page-id $PAGE_ID --key "published-by" --value "ci-pipeline"
confpub property set --page-id $PAGE_ID --key "publish-date" --value "2026-03-26"

# Add a review comment
confpub comment add --page-id $PAGE_ID --text "Auto-published from main branch, commit abc1234."

# Apply governance labels
confpub label add --page-id $PAGE_ID --label auto-published --label needs-review
```
