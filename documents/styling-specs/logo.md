---
title: Logo Specifications
description: Primary wordmark, variants, sizing rules, clear space, and asset delivery formats
status: stable
updated: 2026-04-21
---

# Logo Specifications

## Primary logo

- **Format**: Lowercase wordmark `openagentd`
- **Font**: Geist Variable at 700 weight
- **Character**: Single-weight, no decoration, no drop shadow, no lockup ornament
- **Mode-aware color**:
  - On dark backgrounds: off-white `#FAFAFA`
  - On light backgrounds: charcoal `#09090B`
- **Usage**: Use the primary logo in all standard communications — app header, docs, READMEs, social avatars

The wordmark is a utilitarian typographic mark, not a decorative logo. Its job is to name the product clearly and get out of the way.

---

## Logo variants

| Variant | Use | Color spec |
|---------|-----|------------|
| **Primary (dark)** | App, dark marketing, social cards on dark surfaces | `#FAFAFA` wordmark on `#0A0A0B` |
| **Primary (light)** | Docs, light marketing, invoices, light social cards | `#09090B` wordmark on `#FAFAFA` |
| **Gradient hero** | Hero sections, launch graphics, reserved moments | `var(--gradient-accent)` wordmark on dark — reads as brushed metal |
| **Horizontal lockup** | Wide spaces (header, footer) with tagline alongside | Wordmark + "on-machine AI agents" in `text-2`, separated by 24px vertical rule |
| **Stacked lockup** | Narrow spaces (mobile nav, portrait posters) | Wordmark above tagline, centered |
| **Monogram `o.`** | Favicon, app icon, tight spaces where wordmark is illegible | Lowercase `o` followed by period, same color rules as wordmark |

### Gradient hero — use sparingly

The gradient variant uses `linear-gradient(180deg, #FAFAFA 0%, #D4D4D8 100%)` clipped to the wordmark text. It reads as polished silver. Restrict to:
- Landing-page hero
- Launch announcements
- One instance per surface

Never use the gradient variant in documentation, the app UI, or anywhere it would appear more than once in view. Repeated metal reads as cheap, not premium.

---

## Light-background fallback rule

Silver is invisible on light backgrounds. **Never** render the wordmark in silver (`#E4E4E7`) on a light surface — it fails contrast and loses meaning.

On light backgrounds, the wordmark is always charcoal (`#09090B`). On light marketing surfaces where a "premium" treatment is required, use the gradient hero variant — but with the *light-mode gradient* (`#3F3F46 → #18181B`), which reads as graphite.

---

## Clear space & sizing

### Clear space

Maintain breathing room equal to the **height of the lowercase `o`** on all sides. Nothing — other text, images, borders — enters this space.

```
╭────────────────────────────────╮
│   ↕                            │
│   ↔   openagentd    ↔          │
│   ↕                            │
╰────────────────────────────────╯
```

### Minimum size

- **Digital**: 20px cap-height (wordmark). Below this, switch to the `o.` monogram.
- **Print**: 8mm cap-height at 300 DPI

### Maximum size

No upper limit. At display sizes (above 80px cap-height), pair with sufficient surrounding whitespace — large wordmarks on cramped backgrounds read as shouty.

### Monogram thresholds

Use the `o.` monogram when:
- Available space is smaller than 20px for the full wordmark
- The mark appears in a tight grid (favicon, app icon grid, repeated avatar)
- The context already names the product (e.g. in-app sidebar where "openagentd" is clear from context)

---

## Logo no-nos

❌ **Do not**:
- Rotate, skew, or distort the wordmark
- Add drop shadows, glows, or outer effects
- Use any color other than the mode-appropriate neutrals or the approved gradient
- Render silver on light backgrounds
- Add decorative elements, asterisks, or version numbers inside or adjacent
- Rearrange or modify letter order (the lowercase `d` at the end is load-bearing — it signals "daemon")
- Use with other wordmarks or logos in a lockup (avoid "openagentd × Partner" logo combinations)
- Stretch or compress horizontally/vertically
- Recreate the mark in a different typeface — always use Geist Variable 700

---

## Asset delivery

| Format | Use case | Specs |
|--------|----------|-------|
| **SVG** | Web, scalable graphics, app UI | Preferred for digital — single-file with both mode variants via `currentColor` |
| **PNG** | Raster fallback, slide decks | 1×, 2×, 3× exports at common display sizes |
| **PDF** | Print, design files | Vector, with bleed where appropriate |
| **ICO / ICNS** | Favicon, macOS/Windows app icons | Monogram at required sizes (16, 32, 48, 64, 128, 256, 512) |

### SVG implementation recommendation

Ship a single SVG using `currentColor` so the mark inherits the mode-appropriate text color from its container:

```svg
<svg viewBox="0 0 280 48" xmlns="http://www.w3.org/2000/svg">
  <text x="0" y="36" font-family="Geist Variable" font-weight="700" font-size="40" fill="currentColor">
    openagentd
  </text>
</svg>
```

Then render it with the desired color via CSS:

```css
.logo-mark { color: var(--color-text); }
```

All logo files should live in a centralized asset repository (Figma, Google Drive, `web/src/assets/brand/`, or equivalent).
