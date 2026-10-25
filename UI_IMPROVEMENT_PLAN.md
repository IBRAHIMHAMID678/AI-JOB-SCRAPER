# AI Job Pilot — UI Improvement Plan

> A prioritized, code-grounded proposal for making the dashboard faster, safer, and
> nicer to use. Every recommendation below is tied to something observed while running
> and testing the live app (`localhost:8000`) or to the current source in
> `static/index.html`, `static/style.css`, and `static/script.js`.

---

## TL;DR — Top 5 wins, in order

| # | Change | Why | Effort |
|---|--------|-----|--------|
| 1 | Stop injecting scraped text via `innerHTML` | **Security**: job descriptions from external boards are rendered as live HTML (XSS) | Low |
| 2 | Add a toast/notification system | Errors currently vanish into `console.error` — users never see "Mark applied failed" | Low |
| 3 | Consolidate the responsive CSS + fix the header overlap | 7 scattered/duplicated breakpoints; header badges collide at mobile width | Medium |
| 4 | Close modals on `Escape` + trap focus | Confirmed bug: Escape does nothing; keyboard users get stuck | Low |
| 5 | Virtualize / paginate the jobs table | 120+ rows render at once; will get sluggish as the cache grows | Medium |

---

## 1. Security first: stop trusting scraped HTML  🔴

**Where:** `static/script.js:683` and `:735`

```js
inspectDesc.innerHTML = job.description || "No full description text…";
document.getElementById("modal-job-desc").innerHTML = job.description || "…";
```

`job.description` is **scraped from external job boards** and injected straight into
the DOM as HTML. A malicious (or merely malformed) posting can run script in your
dashboard — this is a real stored-XSS vector, and the modal even renders inside your
"Mission Control" shell next to your auth/Mongo status.

**Fix:**
- Render descriptions as text (`textContent`) or sanitize with DOMPurify before
  injection.
- If you want the rich formatting (bold, lists, links), sanitize to an allow-list and
  `rel="noopener noreferrer"` any outbound anchors.
- The `extractSkills()` helper already uses `RegExp` on raw text safely — keep that
  pattern; avoid `new Function` / `innerHTML` with scraped data anywhere else.

---

## 2. Add a toast + real error surfacing  🟠

**Where:** every `catch` in `static/script.js` (`:565, :651, :792, :878, :974`…) currently does:

```js
catch (err) { console.error("Mark applied error:", err); }
```

Network or DB failures are **invisible** to the user — the UI just silently does
nothing. Meanwhile the backend already tags log lines `[ERROR]`
(`script.js:336`), so the data is there.

**Fix:**
- Add a lightweight toast stack (top-right, auto-dismiss, `role="alert"` /
  `aria-live="polite"` so screen readers announce it).
- Route three sources into it: (a) `catch` blocks, (b) SSE `log` lines containing
  `[ERROR]`, (c) success confirmations ("Marked as applied", "Cache purged").
- Keep the existing console log as the detailed history; toasts are the at-a-glance
  layer.

---

## 3. Responsive cleanup + fix the header overlap  🟠

**Where:** `static/style.css` — media queries at lines **503, 509, 515, 804, 810, 923, 1633**
(7 breakpoints, with `600px` and `1024px`-class rules duplicated across unrelated
sections).

Observed bug: at ~440px width the `.header-telemetry` pills overlap the
`.brand-block` — "Candidate:" collides with the "Junior AI / Full Stack (0-2y)"
value. It looks fine at desktop width, so this only bites phones/tablets.

**Fix:**
- Adopt a single breakpoint scale (e.g. `1200 / 900 / 600`) and remove duplicates.
- In `.app-header`, switch to `flex-wrap: wrap` and let `.header-telemetry` wrap to a
  second row instead of overlapping; add `min-width: 0` on the brand text so the
  subtitle truncates instead of pushing pills off.
- Add `overflow-wrap: anywhere` on `.pill-value` for long values.
- Add a mobile card-view for the jobs table below ~600px: today the 5-column table
  just squashes. A stacked "card per job" layout reads far better on a phone.

---

## 4. Modal accessibility + Escape-to-close  🟡

**Where:** `#verification-modal` (`index.html:502`) and the inspect modal.

Confirmed: pressing `Escape` does **not** close the open modal (only the × works).
There's also no focus trap, so tabbing can leave the modal and land on the page behind
the overlay.

**Fix (small, high-value):**
- Centralize modal open/close in one function; on open, store the previously focused
  element, focus the first control, listen for `Escape`, and trap Tab within the card.
- On close, restore focus to the trigger (e.g. the "Inspect" button that opened it).
- Add `role="dialog" aria-modal="true" aria-labelledby=…` and lock body scroll while
  open (the page behind currently stays scrollable).

---

## 5. Table performance & usability  🟡

**Where:** `#jobs-body` (`index.html:490`) — all matched rows render at once
(120 in the current cache; will grow).

**Fix:**
- **Virtualize or paginate.** Even simple "Show 25 / Load more" beats rendering
  hundreds of `<tr>`. Keeps the SSE `addJobRow()` path fast while a run streams in.
- **Sort controls** on the headers (fit score, pay, company). Today it's fixed
  score-descending; letting the user re-sort is the single most-requested table feature
  in tools like this.
- **Persist filter + search in the URL** (`?filter=high&q=langchain`) so a refresh or a
  shared link restores the view.
- Add a **skeleton loading state** for the table instead of the current empty-state
  flash when a run clears and refills rows.

---

## 6. Pipeline feedback & empty/error states  🟡

**Where:** the launch button + source cards + SSE stream.

**Fixes:**
- The launch button shows "Extracting…" per-card, but there's **no aggregate progress**
  (e.g. "3 / 10 lanes complete · 240 scraped"). The SSE stream already emits per-source
  counts — surface a determinate progress bar in the hero card.
- Add a **cancel** action. `is_running` is tracked server-side but there's no way to
  stop a run from the UI; a `POST /api/stop` + button would help when a slow lane
  (JobSpy deep crawl) hangs.
- Distinguish **"no results yet"** from **"lane returned 0 after finishing"** — right
  now a lane that legitimately finds nothing looks identical to one still running.

---

## 7. Design-system polish & accessibility  🔵

The visual language (neon-on-dark, JetBrains Mono, ambient glows) is strong and
consistent. To make it production-grade:

- **Theme toggle.** The dark palette is hardcoded. A light mode (or at least honoring
  `prefers-color-scheme`) broadens usability; the colors are already CSS variables in
  `:root`, so this is mostly additive.
- **Respect `prefers-reduced-motion`.** The pulsing logo, radar rings, and beacon
  animations should disable for users who opt out.
- **Focus-visible states.** Custom checkboxes (`.source-checkbox`) and the preset /
  filter pills need a clear `:focus-visible` ring for keyboard users.
- **Contrast audit.** Some neon accents on the dark card backgrounds sit near the WCAG
  AA boundary — verify `--neon-cyan` / muted grays against their backgrounds.
- **Emoji-only affordances.** Buttons rely heavily on emoji (⚡ 🗑️ 📊). Keep them, but
  ensure every icon has a text label or `aria-label` (most already do — audit the few
  icon-only action buttons like `+` and the modal `×`).

---

## 8. Micro-interactions  🔵

- **Number transitions.** Metric counters (`#metric-scraped`, `#metric-matched`) snap
  to their value; a short count-up animation makes a big scrape feel alive.
- **Row hover affordance.** Add a subtle hover/zebra highlight and a one-click
  "copy link" on the job URL.
- **Inline apply status.** "Mark as Applied" updates the row, but reflect it with a
  persistent badge so users don't lose track in a long list (ties into the filter tab).
- **Keyboard shortcuts.** `/` to focus search, `Enter` on a row to open Inspect, `Esc`
  to close (see #4). Cheap to add, big power-user win.

---

## Suggested sequencing

**Week 1 (safety + quick wins):** #1 XSS fix, #2 toasts, #4 modal Escape/focus.
**Week 2 (layout):** #3 responsive consolidation + mobile table cards.
**Week 3 (scale + polish):** #5 table virtualization/sort, #6 progress/cancel,
then #7/#8 as capacity allows.

Items #1 and #4 are the only ones I'd call *bugs* rather than enhancements — they're
small, self-contained, and worth doing regardless of the rest.
