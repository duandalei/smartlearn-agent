# Design

## Theme

**墨与朱 · 书院笔记 (Ink & Vermilion · Scholar's Desk)**

A personal study notebook, not an admin console. The page is rice paper; text is ink; a single vermilion accent marks what needs attention. Structure comes from hairlines, folios and margins rather than rounded cards and shadows. Chinese serif carries page titles and numbers; a plain UI sans carries labels, forms and dense data. The mood is quiet, tactile and deliberate: a desk lamp, a notebook, a red pen.

## Color

| Token | Hex | OKLCH | Role |
|---|---|---|---|
| `--paper` | `#F7F6F2` | `oklch(0.965 0.006 95)` | page canvas |
| `--paper-2` | `#FBFAF6` | `oklch(0.977 0.006 95)` | raised surface, inputs, cards |
| `--paper-3` | `#EFEDE5` | `oklch(0.937 0.009 90)` | sunken panels, table headers, board columns |
| `--ink` | `#1C2A24` | `oklch(0.27 0.02 160)` | primary text, sidebar |
| `--ink-2` | `#33443B` | `oklch(0.36 0.02 158)` | strong secondary text |
| `--ink-3` | `#5E6B63` | `oklch(0.52 0.015 155)` | secondary text, captions |
| `--ink-4` | `#6E7A72` | `oklch(0.57 0.012 155)` | placeholder (AA on paper) |
| `--vermilion` | `#B3402F` | `oklch(0.52 0.15 32)` | primary action, active nav, key marks |
| `--vermilion-2` | `#C95643` | `oklch(0.59 0.14 33)` | hover |
| `--vermilion-wash` | `#F4E5E0` | `oklch(0.93 0.02 35)` | selected / tinted background |
| `--jade` | `#4F7A5E` | `oklch(0.54 0.04 155)` | success, mastered |
| `--ochre` | `#A97A2F` | `oklch(0.62 0.10 80)` | warning, attention |
| `--dust` | `#6B7F8C` | `oklch(0.58 0.028 235)` | info, neutral data |
| `--line` | `#DDD8CB` | `oklch(0.88 0.012 90)` | default hairline |
| `--line-strong` | `#C3BCAB` | `oklch(0.80 0.018 90)` | emphasized rule |
| `--danger` | `#A83A2C` | `oklch(0.49 0.14 32)` | destructive |

Rules:
- Color is a mark, not a fill. Vermilion appears on primary actions, active navigation, key data points and seals. Never as a large background wash except the active nav item.
- Body text is `--ink` or `--ink-2`. Secondary copy is `--ink-3`. Never lighter than `--ink-4` for readable text.
- Charts use ink as the base line/bar, vermilion for the current or weak signal, jade for positive, ochre for warning, dust for comparison.

## Typography

- **Display / numbers:** `Georgia, 'Noto Serif SC', 'Source Han Serif SC', 'Songti SC', 'SimSun', serif`
  - Page title 32px / 600 / 1.25; section title 20px / 600 / 1.4; metric value 38–44px / 600 / 1.05; card title 16px / 600.
  - Use `font-variant-numeric: lining-nums tabular-nums` on numbers.
- **UI / body:** `'Segoe UI', 'Microsoft YaHei', 'PingFang SC', 'Noto Sans SC', system-ui, sans-serif`
  - Body 14px / 1.7; labels 12–13px; table 13px; button 14px / 500.
- **Mono:** `'Cascadia Mono', Consolas, 'SFMono-Regular', monospace`
  - Dates, durations, identifiers, folios. 11–12px, letter-spacing 0.02em.
- Body line length capped at 68ch; prose blocks 65–72ch.
- No all-caps body copy. Chinese headings get `letter-spacing: 0.01em`; Latin display gets `-0.01em`.

## Layout

- App shell: ink sidebar 248px + paper content. Top bar 64px with hairline bottom edge.
- Content: max-width 1360px, padding 32px 40px 56px; 24px gutters.
- Spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.
- Page rhythm: folio line → title → lead → rule → content. One `PageHeader` per page.
- Radii: 2px for controls, cards and tags. Circles only for progress rings and status dots.
- Borders: 1px `--line` is the default separator. Shadows are nearly absent: `0 1px 0 rgba(28,42,36,.04)`; hover lift `0 4px 18px rgba(28,42,36,.07)`.
- Paper grain: a fixed SVG noise overlay at 2.5% opacity on the app background.
- Breakpoints: 1200px (columns collapse), 960px (sidebar becomes a drawer), 720px (single column, filter bar wraps).

## Components

- **Sidebar:** ink surface, vermilion seal mark, serif wordmark, grouped folio nav. Items numbered `01–10`; active item is a solid vermilion block with paper text. Bottom shows today's date and the product loop.
- **Top bar:** folio of the current section on the left; date, local-user status and a small seal on the right. No page title duplication.
- **Page header:** mono folio, serif title, one-sentence lead, optional actions on the right, hairline rule with a 28px vermilion start.
- **Ledger row:** metrics separated by vertical hairlines, large serif values, small sans labels. Used instead of four identical stat cards.
- **Panel:** paper-2 surface, 1px line, 2px radius, serif 16px title, 1px bottom rule. Nested panels are forbidden.
- **Buttons:** rectangular 2px radius. Primary = vermilion fill, paper text. Secondary = paper fill, ink border, ink text. Text actions = vermilion, no background. Destructive = danger text, only filled for final confirmation.
- **Inputs:** paper-2 fill, 1px inset line, 2px radius. Focus = 1px vermilion ring (no glow).
- **Tables:** transparent surface, paper-3 header, 13px, row rules 1px. Hover = `--paper-3` at 50%. No zebra striping.
- **Tags:** 2px radius, 1px border, transparent fill, 12px. Semantic tint only.
- **Tabs:** underline 2px vermilion for active; ink-3 for inactive; no pills.
- **Dialogs / drawers:** paper surface, hairline header and footer, serif 20px title, 2px radius, overlay `rgba(28,42,36,.42)`.
- **Charts:** ink axes and 11px labels, dashed horizontal grid at 8% ink, vermilion current point, area fill at 6% vermilion or jade. Tooltip is a paper card with 1px line.
- **Empty states:** a vermilion seal glyph, one sentence of direction, one primary action. No decorative illustration.
- **Motion:** 160ms for state, 220ms for entrances, `cubic-bezier(0.22, 1, 0.36, 1)`. No page-load choreography. Reduced motion = instant/crossfade.

## Do / Don't

- Do let whitespace and rules carry structure.
- Do use serif for titles and numbers, sans for controls.
- Do keep one strong accent per screen.
- Don't use gradient text, glass cards, neon, or 9999 z-indexes.
- Don't use colored left-stripe borders on cards or alerts; use full borders, background tints or a leading mark.
- Don't put an uppercase tracked eyebrow above every section.
- Don't nest cards inside cards or turn every row into a card.
