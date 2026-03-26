# HTML Styling Recipes

Ready-to-use HTML macro patterns for visual designs beyond native Confluence. Use `::: html` blocks to embed these.

## KPI Cards

Colored metric cards for dashboards.

```markdown
::: html
<style>
  .kpi-row { display: flex; gap: 16px; flex-wrap: wrap; margin: 16px 0; }
  .kpi-card {
    flex: 1; min-width: 140px; padding: 20px;
    border-radius: 8px; text-align: center; border: 1px solid #DFE1E6;
  }
  .kpi-card .value { font-size: 32px; font-weight: 700; margin: 0; }
  .kpi-card .label { font-size: 12px; color: #6B778C; margin: 4px 0 0; text-transform: uppercase; letter-spacing: 0.5px; }
  .kpi-card.success { background: #E3FCEF; border-color: #36B37E; }
  .kpi-card.success .value { color: #006644; }
  .kpi-card.warning { background: #FFFAE6; border-color: #FFAB00; }
  .kpi-card.warning .value { color: #FF8B00; }
  .kpi-card.danger { background: #FFEBE6; border-color: #FF5630; }
  .kpi-card.danger .value { color: #DE350B; }
  .kpi-card.info { background: #DEEBFF; border-color: #0065FF; }
  .kpi-card.info .value { color: #0747A6; }
</style>
<div class="kpi-row">
  <div class="kpi-card success">
    <p class="value">99.97%</p>
    <p class="label">Uptime</p>
  </div>
  <div class="kpi-card warning">
    <p class="value">87%</p>
    <p class="label">SLO Budget</p>
  </div>
  <div class="kpi-card danger">
    <p class="value">3</p>
    <p class="label">Open P1s</p>
  </div>
</div>
:::
```

Customize: change card count, add `.info` class for blue, adjust `min-width` for sizing.

## Traffic Light Status Board

Grid of services with colored health dots.

```markdown
::: html
<style>
  .status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; margin: 16px 0; }
  .status-item {
    display: flex; align-items: center; gap: 10px;
    padding: 12px 16px; border-radius: 6px;
    background: #FAFBFC; border: 1px solid #DFE1E6;
  }
  .status-dot { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
  .status-dot.green { background: #36B37E; }
  .status-dot.yellow { background: #FFAB00; }
  .status-dot.red { background: #FF5630; }
  .status-name { font-weight: 600; font-size: 14px; }
</style>
<div class="status-grid">
  <div class="status-item">
    <span class="status-dot green"></span>
    <span class="status-name">API Gateway</span>
  </div>
  <div class="status-item">
    <span class="status-dot yellow"></span>
    <span class="status-name">Payment Service</span>
  </div>
  <div class="status-item">
    <span class="status-dot red"></span>
    <span class="status-name">Search Index</span>
  </div>
</div>
:::
```

Add or remove `.status-item` divs to match your service list.

## Timeline / Roadmap

Vertical timeline with milestones.

```markdown
::: html
<style>
  .timeline { position: relative; padding: 20px 0 20px 30px; }
  .timeline::before {
    content: ''; position: absolute; left: 9px; top: 0; bottom: 0;
    width: 2px; background: #DFE1E6;
  }
  .tl-item { position: relative; margin-bottom: 24px; padding-left: 20px; }
  .tl-item::before {
    content: ''; position: absolute; left: -25px; top: 6px;
    width: 12px; height: 12px; border-radius: 50%;
    border: 2px solid #0052CC; background: white;
  }
  .tl-item.done::before { background: #36B37E; border-color: #36B37E; }
  .tl-item.active::before { background: #0052CC; border-color: #0052CC; }
  .tl-date { font-size: 12px; color: #6B778C; font-weight: 600; }
  .tl-title { font-size: 16px; font-weight: 600; margin: 2px 0; }
  .tl-desc { font-size: 14px; color: #42526E; }
</style>
<div class="timeline">
  <div class="tl-item done">
    <div class="tl-date">Q1 2026</div>
    <div class="tl-title">Foundation</div>
    <div class="tl-desc">Core platform, auth, CI/CD</div>
  </div>
  <div class="tl-item active">
    <div class="tl-date">Q2 2026</div>
    <div class="tl-title">Payment Integration</div>
    <div class="tl-desc">Stripe + Adyen, reconciliation</div>
  </div>
  <div class="tl-item">
    <div class="tl-date">Q3 2026</div>
    <div class="tl-title">Scale</div>
    <div class="tl-desc">Multi-region, caching, CDN</div>
  </div>
</div>
:::
```

Add `.done` class to completed milestones, `.active` to current. Unclassed items show as pending.

## Styling Guidelines

These HTML recipes use Atlassian Design System colors for consistency with Confluence's native look:

| Purpose | Color | Hex |
|---------|-------|-----|
| Success/Green | `#36B37E` | Background: `#E3FCEF` |
| Warning/Yellow | `#FFAB00` | Background: `#FFFAE6` |
| Danger/Red | `#FF5630` | Background: `#FFEBE6` |
| Info/Blue | `#0065FF` | Background: `#DEEBFF` |
| Neutral text | `#42526E` | Secondary: `#6B778C` |
| Border | `#DFE1E6` | Background: `#FAFBFC` |
