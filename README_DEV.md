# Smart Manufacturing — Dashboard

## Version history

- **V1**: initial prototype (dark theme, KPI row, machine cards, dropdown-based selection)
- **V2**: product-style polish (clickable cards, de-emphasized status labels, insight panels, auto-generated interpretation text)
- **V3**: Decision Support Module V1 — rule-based factory-manager recommendations
- **V4**: product-style hero header, a working Historical Timeline slider, dark Bloomberg/Grafana-style tables, restructured Decision Support panel
- **V4.1**: UI/UX bug-fix and polish pass (fixed timeline data flow, removed fragile card-click hack, fixed table overflow)
- **V6**: Premium SaaS visual polish pass (Linear / Stripe / Vercel aesthetic) — unified visual system, premium panels everywhere, genuinely whole-card clickable
- **Final polish** (current): mentor-demo readiness pass — see "What changed in the final polish" below. Visual system, layout, colors, and typography are unchanged from V6; this pass is display-naming, wording, and a timeline-sync audit only.

## What this is

A **presentation-layer prototype** for the Smart Manufacturing Forecasting
project. It reads three files already produced by the ML pipeline and
displays them — it does **not** train models, does **not** recompute any
metrics, and does **not** modify any results files.

```
results/machine_status_summary.csv         -> "as of now" snapshot, 1 row/machine
results/dashboard_forecast_predictions.csv -> full test-period actual vs. predicted history
results/dashboard_metrics.json             -> fleet-wide aggregate model quality
```

## How to run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the URL Streamlit prints (usually `http://localhost:8501`).

## What changed in the final polish

This pass makes the demo clearer for a non-technical audience (a mentor
reviewing the project) without touching the V6 visual system, layout,
colors, typography, or any calculation logic. Four scoped changes:

### 1. Clean display names ("Production Unit 01"-"34")
Raw IDs like `machine_13` / `machine_47` are not sequential and look
arbitrary in a demo. `build_machine_display_map()` now builds a
one-time, deterministic mapping - machine_ids are sorted **numerically**
(not alphabetically; a plain string sort would put `machine_12` before
`machine_2`) and assigned `Production Unit 01`, `02`, `03`, ... in that
order. This is presentation-only:

- `st.session_state["selected_machine"]`, all `snapshot_df` /
  `predictions_df` filtering, and every chart query still use the raw
  `machine_id` exactly as before - verified by keeping the dropdown's
  underlying *value* as the raw id (`st.selectbox(..., format_func=get_display_name)`
  changes only the label Streamlit shows, not what gets stored).
- The full name (`Production Unit 21`) is used in Factory Insights,
  Rankings, Machine Detail, the dropdown, and Decision Support text.
- **One exception, found during testing**: inside the Factory Overview
  cards specifically, the full name overflowed (six cards share a row,
  and `Production Unit 19` is roughly twice as wide as the space
  available per card - this was verified, not guessed: 0/34 names fit
  before switching approach). Cards use a shorter `Unit 19` form instead
  (same underlying number, just less padding-heavy), while a hover
  tooltip on the card title shows the full name. Every other section
  still shows the full "Production Unit NN" form.
- `decision_engine.py`'s `recommendation_text` embeds the raw machine_id
  internally (it has no concept of display names, nor should it - it's
  a pure calculation module). Rather than modify that module, the
  presentation layer does one exact substring replace after getting the
  result back, swapping the raw id for the display name before
  rendering. `decision_engine.py` itself was **not changed**.

### 2. Historical Timeline stays secondary, wording updated
Still the last section on the page, still compact. Timestamp line now
reads "Hour 331 / 467" instead of "331 / 467 hours" per the requested
wording.

### 3. Timeline-sync audit (no bugs found - already correct since V4.1)
Re-verified end to end that `snapshot_df` (derived fresh from the
selected timestamp on every rerun) - not `machine_status_summary.csv` -
drives every timestamp-dependent value: KPI cards, Factory Insights,
machine cards, ranking tables, Machine Detail's current
energy/predicted average/change%/trend, and the Decision Support
temporary row. Only `regression_rmse`, `predicted_status`, and the
fallback `predicted_24h_max_energy` still come from the static summary
CSV, exactly as specified. Confirmed with an automated test that moves
the slider and asserts each section's rendered content actually changes.

### 4. Sorting explanation in Factory Overview
A small line - "Sorted by: **Predicted 24h Avg Energy**" (or whichever
option is active) - now sits directly under the sort controls and
updates live when the sort choice changes, so the card order never
looks arbitrary. The "machine_id" sort option was also relabeled "Unit
Number" (it sorts by the same underlying number as the display-name
mapping) to avoid surfacing raw-ID language in the UI.



V6 is a pure visual/UX polish pass aimed at an internship-presentation-ready
look (Linear / Stripe / Vercel, not Grafana). **Zero changes** to
`src/decision_engine.py`, CSV/JSON loading, KPI/RMSE/ranking/sorting math,
or the Historical Timeline's underlying data logic — every change below is
CSS, HTML structure, or a client-side interaction affordance.

### 1. Unified visual system
Colors updated to the exact V6 spec: background `#0B0F17`, panels
`#151B26`, border `#2B3548`, accent blue `#4EA1FF`, muted text `#A0A7B5`.

### 2 & 4. Premium panels everywhere (including the header)
Every major section - KPI Summary, Factory Insights, Factory Overview,
Rankings, Machine Detail, Decision Support, and Historical Timeline - now
shares one identical "premium panel" treatment (dark background, border,
16px radius, soft shadow, 28px padding, 40px gap between sections).
Implemented via a small reusable pattern: each section is rendered into
its own `st.container()`, with an invisible marker div as its first
child; one shared CSS rule uses `:has()` to detect that marker and apply
the panel styling to exactly that container - no per-section styling
code duplicated, and no risk of the "wrap columns in a bordered box"
problem that naive HTML nesting runs into with Streamlit.

### 3. Typography system
One consistent scale used everywhere: 28px section titles, 15px muted
subtitles, uppercase-letter-spaced card labels, 34px bold KPI values
(see note below), 20px bold machine name in Machine Detail.

*Note on "44-48px metric values":* the brief's literal 44-48px was
applied to the KPI Summary cards' spirit but tuned down to 34px in
practice - at 44-48px the 5-across KPI row and the small Factory
Insight cards (whose "value" is a machine name string, not a bare
number) started wrapping/overflowing on a standard 1600px-wide screen,
which conflicts with the explicit "no overflowing text" requirement.
34px is the largest size that stays crisp and unclipped at 5-up while
still reading as unmistakably the dominant number on the page.

### 6 & 7. Machine cards - polish + genuinely whole-card clickable
Fixed real alignment bugs found during testing: the header row's
machine name was truncating (`machin...`) even for short names, and the
"Predicted 24h Avg Energy" label was wrapping to two lines and pushing
the RMSE row out of the fixed-height card, colliding visually with the
button below it. Root causes and fixes:
  - Flexbox truncation bug: `.machine-id` needed `min-width: 0` (a
    well-known flex gotcha - without it, ellipsis truncation kicks in
    too aggressively even when there is visually enough room).
  - Label wrapping: shortened "Predicted 24h Avg Energy" to "Predicted
    24h Avg" and tightened card/pill padding, freeing enough horizontal
    room that every one of the 34 machine names now renders in full
    (verified programmatically - 0 of 34 truncated).
  - Card height increased slightly (178px → 216px) so all rows,
    including RMSE, always fit with `overflow: hidden` as a safety net.

  **Whole-card click**: clicking anywhere on a card - not just "View
  Detail" - now selects that machine. First attempt used a plain
  `onclick=` HTML attribute, which turned out to be silently stripped by
  Streamlit's markdown sanitizer (a real bug caught during testing, not
  just a style choice) - clicking any card appeared to "work" only
  because it happened to land on whichever card matched the
  already-selected default. The actual fix uses the same proven pattern
  already used elsewhere in this app for the scroll-to-Machine-Detail
  behavior: a small script, delivered via `st.iframe()` (which runs in a
  real, non-sanitized frame), reaches back into the main page via
  `window.parent.document` and binds a delegated click listener to every
  card. A `MutationObserver` re-applies this after each Streamlit rerun.
  This was verified with an automated test that clicks four different
  non-default cards (scrolled into view first) and confirms each one
  actually changes the selected machine - not just that the app doesn't
  crash.

### 8. Ranking tables
Header row, row hover, alignment, and padding refined; each panel
(title + subtitle + table) still renders as one HTML block (a fix
carried over from V4.1) so nothing can visually separate from its
container.

### 9-12. Factory Insights, Machine Detail, Decision Support, Historical Timeline
Spacing, padding, and typography brought in line with the shared system
above; no layout or logic changes beyond that. Decision Support's field
grid (Risk/Priority, Forecast Quality, Cause, Recommendation, Suggested
Action, Confidence Note) now has consistent 18-32px gaps and aligned
labels.

### 13. Hover states
Cards, KPI tiles, insight cards, and ranking panels all get a subtle
150ms border/shadow transition on hover; no bouncing, scaling, or other
attention-grabbing animation.



V4.1 is a bug-fix and polish pass only — no new features, no ML changes.
`src/decision_engine.py` was **not modified**.

### 1. Fixed: Historical Timeline only updated Factory Insights
This was a real bug in V4, not just a perception issue. **Root cause**:
although `snapshot_df` was correctly threaded through every section's
*rendering* code, the page's visual section order in V4 happened to let
this go unnoticed since Factory Insights sat right under the slider.
**Fix**: `get_timestamp_snapshot(predictions_df, summary_df,
selected_timestamp)` is now unambiguously the single source of truth,
and — more importantly — the selected timestamp is now **read from
`st.session_state["selected_ts_index"]` once, at the very top of the
script**, before *any* section renders. The slider widget itself is
drawn much later (see #2 below), but Streamlit ties a widget's value to
its `key` in session_state independently of where in the script it is
physically drawn - so one compact slider at the bottom still correctly
drives the KPI row, Factory Insights, every machine card, all three
ranking tables, Machine Detail, Decision Support, and the forecast
chart's marker, all from the same read. This was verified with an
automated test that changes the slider and asserts each section's
rendered content actually changes (not just "no crash") - see the
"What changed in V4.1" verification in the project's test history.

### 2. Fixed: Historical Timeline was too large and too high on the page
Moved to the bottom of the page (new layout order: Header → KPIs →
Factory Insights → Factory Overview → Ranking panels → Machine Detail →
Decision Support → Historical Timeline) and shrunk to a compact
single-panel widget: one-line title, one-line subtitle, the slider
itself, and a small "Viewing: ..." status line. It no longer dominates
the page.

### 3. Fixed: machine card titles clipped/misaligned + removed the fragile click hack
The V4 "invisible full-card button overlay" trick (a real Streamlit
button stretched to invisibly cover the card via absolute positioning)
was fragile and caused layout bugs. **It has been completely removed.**
Cards now render in **normal document flow** with a fixed height, a
proper flexbox header row (`machine-id` on the left with
`text-overflow: ellipsis` for long names, the status pill on the right,
both vertically centered), and a real, visible **"View Detail →"**
button underneath, styled as a slim outlined CTA rather than a default
gray button. Clicking it updates `selected_machine`, scrolls to Machine
Detail, and updates the chart and Decision Support - exactly like
before, but with a stable, debuggable layout instead of a CSS hack that
fought Streamlit's internal styles.

### 4. Fixed: ranking table titles/subtitles overflowing the table border
Each ranking panel (Top Future Energy / Most Reliable Forecasts /
Largest Expected Increase) is now rendered as **one single HTML block**
(`render_ranking_panel()`) containing the title, subtitle, and table
together inside one `.ranking-panel` div - so the border, padding, and
background can never visually separate from the title the way three
independent `st.markdown()` calls could in V4. All three panels share
the same `min-height`, padding, and border-radius for clean, equal-height
alignment.

### 5. Header hierarchy strengthened
Hero title font size increased and given tighter letter-spacing for a
bolder look; eyebrow label made more prominent; spacing tightened
throughout the hero panel.

### 6-9. General polish
Unified spacing, fixed a few remaining hard-coded colors to use the
shared palette constants, tightened Factory Insight card heights, and
adjusted the forecast chart's title/legend vertical spacing so they no
longer visually crowd each other.



### A. Product-style hero header
Replaced the plain title with a two-sided hero panel: left side has an
eyebrow label ("SMART MANUFACTURING"), a large product name ("Forecast
Intelligence Platform"), a one-line subtitle, and four status chips (34
Machines / 24h Forecast / Decision Support / Historical Timeline). Right
side shows "Production Demo · Version 1.0 · Last Update" metadata. A
subtle blue top-border and gradient background give it a distinct "this
is a product, not a document" feel, per the brief.

### B. A real, working Historical Timeline
This is the headline feature of V4. The old disabled placeholder slider
is gone — `render_historical_timeline()` now drives an `st.select_slider`
over every hourly timestamp common to **all 34 machines** in
`dashboard_forecast_predictions.csv` (467 shared hours, from Feb 18 20:00
to Mar 10 06:00). Moving the slider calls `get_timestamp_snapshot()`,
which re-derives a per-machine snapshot (actual/predicted energy AS OF
that hour) that flows into everything below it on the page: the KPI row,
Factory Insights, every machine card, all three ranking tables, and
Decision Support all update together from the same selected timestamp.

**Important, and stated directly in the UI subtitle**: this is a
*historical inspection* tool, not a forecast-version replay. The model
ran once and produced one fixed prediction per hour; the slider lets you
look back at what those (fixed) actual/predicted numbers looked like at
any point in the evaluation window - it does not re-run or regenerate
any forecast.

*(Why the intersection of timestamps, not each machine's own full range:
each machine's train/test split lands on a slightly different hour,
because machines have slightly different missing-value counts. Using
only the common hours guarantees every one of the 34 machines has a
fully defined snapshot at every slider position - nothing ever silently
disappears from a card or table as you move the slider.)*

### C. Dark ranking tables
All three ranking panels (`render_dark_table()`) are now custom dark
HTML tables instead of `st.dataframe` — matching backgrounds, light
text, subtle grid lines, and colored Change % cells (amber = increasing,
green = decreasing). No white/light table blocks remain anywhere on the
page. Panels renamed and re-columned per the brief:
- **Top Future Energy** — Machine, Pred 24h Avg, Current, Change %
- **Most Reliable Forecasts** — Machine, RMSE, Pred 24h Avg
- **Largest Expected Increase** — Machine, Current, Pred 24h Avg, Change %

### D. Factory Overview cards
Predicted 24h Avg Energy is now the dominant number on each card (large,
blue). A small trend indicator (↑ Increasing / → Stable / ↓ Decreasing)
sits right underneath it, using the exact same thresholds as the
decision engine (imported, not re-implemented, so the arrow can never
disagree with Decision Support). Status stays a small, secondary pill.

### E. Decision Support — structured fields, not paragraphs
Rebuilt as a small "management system" style panel: Risk/Priority,
Forecast Quality, Cause (a short auto-generated phrase like "predicted
peak energy is high; energy demand is trending upward"), Recommendation,
Suggested Action, and a muted Confidence Note - all in a clean two-column
grid instead of one long paragraph. Still entirely rule-based (see
"Decision Support V1" below); `src/decision_engine.py` itself was **not
modified** — the new "Cause" text is presentation logic built in
`app.py` from the engine's existing output fields.

### F. Forecast chart
Added a dotted vertical line at the selected timestamp with a "Selected
Time" annotation, plus a diamond marker showing the predicted 24h max at
that hour. Hover text cleaned up on both the actual and predicted lines.

### G. Unified visual system
Every color in the app now comes from one named palette (background,
panel, border, primary blue, text, muted text, warning amber, critical
red, healthy green) instead of scattered hex codes, matching the exact
values in the V4 brief.

### H. Code structure
Reorganized around the requested helper functions: `load_data()`,
`format_timestamp()`, `render_header()`, `render_kpi_card()`,
`get_timestamp_snapshot()`, `render_machine_card()`, `render_dark_table()`,
`render_machine_detail()`, `render_decision_support()`,
`render_historical_timeline()`, plus small supporting helpers
(`get_common_timestamps()`, `trend_arrow()`, `build_cause_text()`).
`src/decision_engine.py` was not touched.



### What it is

`src/decision_engine.py` converts the ML pipeline's saved forecast numbers
(`current_energy`, `predicted_24h_avg_energy`, `predicted_24h_max_energy`,
`regression_rmse` — all already in `machine_status_summary.csv`) into a
plain-language recommendation for a factory manager: is this machine's
energy trending up or down, how much can the forecast be trusted, how
urgent is it, and what should someone actually do about it.

### It is rule-based, not an LLM

Every output comes from a fixed chain of `if/else` thresholds — there is
no model call, no prompt, no external API. Concretely:

- **Trend direction**: compares `predicted_24h_avg_energy` to
  `current_energy` (±10% band = "Stable", above = "Increasing", below =
  "Decreasing").
- **Forecast quality**: thresholds on `regression_rmse` (≤0.33 = High,
  ≤0.40 = Medium, else Low).
- **Priority level**: thresholds on `predicted_24h_max_energy` (≥4.75 =
  High, ≥4.50 = Medium, else Low).
- **Recommendation**: a small decision table combining trend + priority
  (a *decreasing* trend always produces a maintenance-window suggestion,
  even if the priority level would otherwise read "High" — winding down
  is an opportunity, not a concern).
- **Confidence note**: directly tied to forecast quality, so a
  low-reliability forecast is never presented with unwarranted confidence.

This is intentionally simple. Every threshold is a plain number that can
be questioned, verified against real operational data, and adjusted by a
domain expert without touching any modeling code.

### Where it shows up in the dashboard

- **Factory Insights** (top of page): fleet-wide rollup — the machine
  with the highest predicted peak, the largest predicted increase, the
  most reliable forecast, and a count of High-priority machines.
  Computed by `generate_fleet_insights()`, which just runs the
  per-machine engine 34 times and aggregates.
- **Decision Support** (inside Machine Detail, below the forecast chart):
  the full recommendation for whichever machine is currently selected —
  trend direction, energy change %, forecast quality, priority level,
  recommendation text, suggested action, and confidence note.

### This is a prototype layer, not a final decision system

Decision Support V1 exists to make the forecast numbers *actionable* in
the simplest, most auditable way possible — a baseline that any future,
more sophisticated approach should be measured against. Natural next
steps (not built here):

- Replace or augment the fixed thresholds with an **LLM** that can read
  the same numbers plus free-text context (maintenance logs, shift
  notes, order backlogs) and produce a richer, situation-aware
  recommendation.
- Replace the threshold-based priority ranking with a proper
  **domain-specific optimization** (e.g. actual energy cost curves,
  machine-specific safety limits, production scheduling constraints)
  instead of a single global peak-energy cutoff that treats every
  machine the same way.
- Feed recommendation outcomes back into the system (did a manager act
  on a "High priority" flag? did it help?) to eventually validate or
  retrain against real decisions, rather than fixed thresholds chosen
  up front.



**A. Header and wording**
- Title changed to "AI Factory Energy Monitoring Dashboard" (product-style, not "Fleet Overview")
- Subtitle now explains what the dashboard does in one line
- A small note near the KPIs states forecasts come from saved pipeline outputs and status labels are experimental
- "Last Updated" now renders as a single clean line ("Mar 10, 2025 · 10:00") via a new `format_timestamp()` helper, instead of Streamlit's default multi-line datetime wrapping

**B. Status label de-emphasis** — this was the most important change. The Normal/Warning/Critical classifier scores ~33.5% accuracy on 3 classes (chance level ≈ 33%), so V2 makes sure it can never look like a trustworthy signal:
- Renamed everywhere from "risk" to "Experimental Status"
- Status pill is now small, low-opacity, and uses muted colors (no bright alarm-red) instead of a dominant colored badge
- An explicit caveat box ("⚠ Status labels are experimental...") sits directly next to every place status is shown
- **`predicted_24h_max_energy` is now the primary sort/ranking signal everywhere** (default card sort, the main insight panel, the visual hierarchy inside each card) — status is demoted to a small secondary label, never the primary way to rank or highlight machines

**C. Machine card interaction**
- Every one of the 34 cards is genuinely clickable (not just visually - a real click target covers the whole card; see the CSS section in `app.py` for how this was made to work reliably against Streamlit's own internal button styling)
- Each card shows a small "View Detail →" hint so it visually reads as actionable
- Clicking a card updates `st.session_state`, updates the Machine Detail panel and Forecast Trend chart, and auto-scrolls the page down to Machine Detail
- The dropdown in Machine Detail still exists as a backup/secondary selector and stays perfectly in sync with card clicks (same session state key)
- The selected card gets a distinct blue glow/border so it's obvious which machine is currently open

**D. Factory overview cards — visual hierarchy**
- Machine ID: large, bold, top of card
- **Predicted 24h Max Energy: emphasized** (larger, colored, labeled) since it's now the primary operational signal
- Current / Predicted 24h Avg: small, muted, secondary rows
- RMSE: small, muted
- Experimental Status: small pill, de-emphasized
- Cards stay compact (~168px) despite the extra visual hierarchy

**E. New insight panels** (Bloomberg-style, three side by side)
- Top 5 — Predicted 24h Max Energy (the main operational ranking)
- Top 5 — Lowest RMSE (which machines have the most reliable forecasts)
- Top 5 — Highest Current Energy (current operational load)

**F. Machine Detail panel**
- Same summary card + forecast trend chart as V1, with clearer axis labels
- **New: auto-generated interpretation text**, built from the selected machine's actual row in `machine_status_summary.csv` (see `build_interpretation_text()` — it is not a hardcoded template per machine, it's one function that reads whichever machine is selected)

**G. Time Navigation → "Time Replay / Simulation"**
- Renamed and re-worded per the V2 brief; still a non-functional placeholder by design

**H. Visual style**
- Softer, less saturated status colors (no bright alarm-red)
- Reduced default vertical gaps/margins for a denser, more "terminal-like" feel
- Section subtitles added under a couple of panel headers for extra context without clutter

**I. Code quality**
- Reorganized into named helper functions: `load_data()`, `format_timestamp()`, `render_kpi_card()`, `render_machine_card()`, `render_ranking_table()`, `render_machine_detail()`, `build_interpretation_text()`, `select_machine()`
- No ML code added; no results files modified

## Design direction, and where each reference shows up

| Reference | Where it shows up |
|---|---|
| **Grafana** (dark ops dashboard) | Overall dark theme, panel-style sections with left-accent-bar titles, dense single-page layout |
| **Tesla vehicle status UI** | Each machine card shows "current state + near-future condition" (current energy vs. predicted 24h avg/max), clickable like tapping into a vehicle's detail view, with a glowing highlight on the selected one |
| **Apple Health** | The top KPI row: soft rounded cards, small uppercase label, one large number |
| **Bloomberg Terminal** | The three Top-5 ranking panels: dense, numeric-first tables meant to be scanned quickly |

## Known limitations — please read before showing this to anyone

- **`predicted_status` (Normal / Warning / Critical)**: ~33.5% accuracy on 3 classes — essentially tied with always guessing the single most common class. V2 makes this impossible to miss (small pill, muted color, caveat box everywhere it appears, no longer used for ranking), but the underlying number is still real pipeline output and is still displayed, by design, rather than hidden.
- **`confidence_or_risk_score`** (shown in the full-fleet data, not surfaced as prominently in V2): this is the classifier's own predicted probability. Since the classifier is unreliable, high confidence does not mean the status is correct.
- The **24h avg/max energy regression numbers** are on firmer footing (~25-32% real improvement over a realistic naive baseline across 34 machines) and are reasonable to present as directional forecasts, with RMSE shown alongside as an honest error bar. This is why V2 makes them the primary signal throughout.

## Files in this delivery

- `app.py` — the Streamlit app (run this)
- `src/decision_engine.py` — rule-based Decision Support V1 engine (unchanged since V3)
- `README_dashboard.md` — this file
- `requirements.txt` — includes `streamlit` and `plotly` alongside the ML dependencies
- `dashboard_v2_top.png` / `dashboard_v2_detail.png` — V2 reference screenshots
- `dashboard_v3_top.png` / `dashboard_v3_decision_support.png` — V3 reference screenshots
- `dashboard_v4_top.png` / `dashboard_v4_timeline.png` / `dashboard_v4_decision_support.png` — V4 reference screenshots
- `dashboard_v4_1_top.png` / `dashboard_v4_1_cards.png` / `dashboard_v4_1_tables.png` / `dashboard_v4_1_detail.png` — V4.1 reference screenshots
- `dashboard_v6_top.png` / `dashboard_v6_cards.png` / `dashboard_v6_tables.png` / `dashboard_v6_detail.png` — V6 reference screenshots
- `dashboard_final_top.png` / `dashboard_final_cards.png` / `dashboard_final_detail.png` / `dashboard_final_timeline.png` — final polish reference screenshots (current)

## Not in scope for V2 (by design)

- No authentication / multi-user support
- No live data ingestion — reads static CSV/JSON snapshots
- No working time-replay/simulation (placeholder only)
- No editing of underlying data or re-triggering of model training from the UI
- No deep nested pages/navigation — everything is on one scrollable page

