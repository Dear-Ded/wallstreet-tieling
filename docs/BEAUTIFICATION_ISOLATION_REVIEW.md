# Beautification Isolation Review

Review date: `2026-07-06`

Scope reviewed:

- `deliverables/beautification-helper/portal-report.html`
- `deliverables/beautification-helper/verify-portal-static.cjs`
- `deliverables/beautification-helper/V120_FINAL_VISUAL_HANDOFF_AUDIT_NOTE.md`
- `deliverables/beautification-helper/V121_REPORT_PACKET_INTEGRATION_MAP.md`
- `deliverables/beautification-helper/V122_VERIFIER_GATE_HARDENING_NOTE.md`
- `deliverables/beautification-helper-codex-worktrees/*`
- `wallstreet-tieling-codex-worktrees/beautification-portal-v111-*`
- `wallstreet-tieling-codex-worktrees/beautification-portal-v112-*`

## Current Judgment

The beautification isolation lane produced real product value. It should not be
discarded as a visual experiment.

The current strongest artifact is:

- `deliverables/beautification-helper/portal-report.html`

Static verification passed:

```text
node deliverables/beautification-helper/verify-portal-static.cjs
{"ok":true,"scripts":1,"fallbackExperts":26,"dataSlots":31,"readingKinds":7,"evidenceIdMarkers":38,"bytes":204589}
```

The page has progressed beyond decoration. It preserves report packet fields,
desktop-agent handoff concepts, formal reading sections, evidence bindings,
export cards, attachments, expert opinions, print rules, reduced-motion rules,
and the 4K video invariant described in the V120-V122 notes.

## Completion Level

| Area | Status | Evidence |
| --- | --- | --- |
| Visual baseline | strong prototype | V120 browser audit recorded desktop, reading, and mobile passes. |
| Formal report reading | implemented in isolation | Static verifier finds required reading sections and data slots. |
| Evidence display | implemented in isolation | Static verifier finds 38 `data-evidence-id` markers. |
| Expert surface | implemented in isolation | 26 fallback expert markers, 13 expert cards in browser notes. |
| Agent handoff visibility | partially integrated | V121 maps `report_exports`, `agent_handoff`, source resilience, QYYJT, capital, and relationship fields. |
| Production export integration | not complete | Real runtime packet injection into this premium HTML is still undecided. |
| Package/release inclusion | not complete | `deliverables/` remains local-only and ignored. |
| Asset governance | needs cleanup | The isolation folder mixes source notes, screenshots, browser profiles, and old prototypes. |

## What Can Move Into Main Project

Do not copy the isolated HTML directly into production `index.html`.

Migrate only these parts through narrow, tested changes:

- The `WTL_REPORT_PACKET` normalization contract for premium HTML.
- The data-slot idea for report fields that must survive visual rendering.
- The static verifier requirements from `verify-portal-static.cjs`.
- The V121 mapping for `report_exports.directory_bundle.agent_handoff`,
  `one_click_readiness`, `qyyjt_public_origin_handoff`,
  `source_resilience`, `capital_risk_panel`, and
  `relationship_graph_audit`.
- The V120 browser acceptance checklist for desktop, mobile, reading layer,
  evidence modal, print, and reduced-motion.
- The final screenshot candidates from V120 if marketplace/operator assets are
  needed.

## What Should Stay Isolated

Keep these out of production and public package until explicitly selected:

- Browser profiles such as `.edge-*`.
- `.playwright-mcp/` folders.
- Early cocoon, model, tree-stump, and wallpaper experiments.
- Massive iteration ledgers and old prompt packets that are not referenced by a
  current integration task.
- Screenshot sequences before V120 unless needed for before/after evidence.
- Any 3D/model sourcing material without a clear license and product use.

## Direct Cleanup Guidance

The isolation approach is still useful, but only if it stops producing
unbounded files.

New rule for future beautification work:

- Keep one active artifact: `portal-report.html`.
- Keep one verifier: `verify-portal-static.cjs`.
- Keep one current coordination file: `BEAUTIFICATION_CURRENT.md` or the latest
  `V###_*` note.
- Put final screenshots under a single `release-candidates/` directory.
- Put browser profiles and temporary captures under `scratch/` or delete them
  after the note is written.
- Do not create new top-level `V###` files for every tiny iteration unless the
  iteration changes a product requirement or acceptance gate.

## Instructions To Beautification Worker

Read this file first:

- `docs/BEAUTIFICATION_ISOLATION_REVIEW.md`

Then read the current source-of-truth files:

- `deliverables/beautification-helper/V120_FINAL_VISUAL_HANDOFF_AUDIT_NOTE.md`
- `deliverables/beautification-helper/V121_REPORT_PACKET_INTEGRATION_MAP.md`
- `deliverables/beautification-helper/V122_VERIFIER_GATE_HARDENING_NOTE.md`
- `deliverables/beautification-helper/verify-portal-static.cjs`
- `deliverables/beautification-helper/portal-report.html`

Your job is no longer to make more scattered visual versions. Your job is to
prepare this isolation lane for production integration:

- Reduce the working context to the current artifact, verifier, V120-V122 notes,
  and final screenshot candidates.
- Propose the minimal adapter-level integration path that converts a real
  `investigation_packet` or report bundle into the premium HTML packet.
- Do not edit production `index.html`.
- Do not edit runtime code unless the main developer assigns a narrow
  integration branch.
- Do not add more browser profiles, repeated screenshots, or new visual
  experiments without deleting or archiving the old scratch.
- Preserve the hard visual invariants: no whiteboard feel, no cursor halo, no
  connector lines, no dot navigation, no purple-gradient default look, no video
  filter, and no downgrade from the 4K CHROMA video source in the isolated
  prototype.
- Preserve the hard product invariants: the report cannot collapse into prose;
  evidence, tables, charts, images, attachments, export files, expert opinions,
  and agent handoff fields must remain visible.

## Isolation Strategy Assessment

Isolation was the correct choice while the visual direction was unstable. It
prevented experimental HTML, browser caches, and large screenshot/model assets
from polluting the desktop-agent release.

It is no longer efficient as an open-ended lane. The efficient route now is:

1. Freeze the isolated prototype as the visual reference.
2. Extract its packet contract and verifier into a narrow production integration
   task.
3. Keep screenshots and visual QA notes as release assets.
4. Archive or delete scratch profiles and obsolete exploration files after the
   integration task is accepted.

This keeps the main project fast while still preserving the best visual work.
