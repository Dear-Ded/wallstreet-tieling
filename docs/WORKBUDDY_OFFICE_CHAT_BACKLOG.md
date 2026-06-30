# WorkBuddy Office Chat Backlog

Scope: WorkBuddy support work for the persona office chat surface.

WorkBuddy is not the backend implementation agent. WorkBuddy must not design
the investigation engine, change evidence logic, or edit core product
architecture. WorkBuddy's job is to prepare low-risk UI support materials for
Codex to later build or review the office-chat interface.

## 0. Role Boundary

WorkBuddy may work only on documentation, fixtures, and QA materials under:

- `docs/workbuddy/`
- `audit_reports/` only when explicitly writing a visual QA note

WorkBuddy must not touch:

- `core/`
- `api/`
- `adapters/`
- `tests/` unless Codex explicitly asks for UI fixture tests
- `index.html`
- data-source logic
- evidence admission logic
- QYYJT logic
- cookies, tokens, browser profiles, local DBs, `.tmp/`, or `outputs/`

WorkBuddy must not claim that UI work is production-ready. Codex owns final UI
quality.

## 1. Output Directory

Create this directory if missing:

```text
docs/workbuddy/
```

All WorkBuddy outputs below must be placed there.

## 2. Required Work Order

Complete these files in order. Do not stop after one file.

### WB-001: Interface References

Output:

```text
docs/workbuddy/office_chat_references.md
```

Content:

- collect layout patterns from Feishu/Lark, DingTalk, WeChat, Slack, Linear,
  Discord, and iMessage-style chat surfaces;
- summarize only observable UI patterns;
- include desktop and mobile notes;
- identify what makes the interface feel like real collaboration software;
- identify what makes an interface feel like a generic AI dashboard.

Do not copy licensed assets. Do not paste large copyrighted screenshots into
the repo. Short links or textual observations are enough.

### WB-002: Office Chat Structure

Output:

```text
docs/workbuddy/office_chat_structure.md
```

Describe a real social-software layout:

- left conversation list;
- middle chat stream;
- right evidence/context panel;
- top channel header;
- bottom composer;
- group chat;
- private chat between sentinel and general manager;
- role presence;
- evidence badges;
- source/status chips;
- message search/filter;
- mobile collapsed layout.

Use concrete UI requirements, not vague adjectives.

### WB-003: Persona Role Sheet

Output:

```text
docs/workbuddy/persona_chat_roles.md
```

For each persona, write:

- `role_id`;
- name;
- investigation lane;
- job responsibility;
- what the role may say;
- what the role must not say;
- group-chat tone;
- private-chat tone;
- evidence citation style;
- example messages.

Tone requirements:

- match the persona's job and authority;
- no generic assistant voice;
- concise, direct, with modern Chinese internet rhythm where appropriate;
- professional enough for a business investigation product;
- no fake certainty when evidence is weak;
- no decorative chatter without evidence or task value.

Use this style target:

- general manager: decisive, short, pushes next action;
- sentinel: quiet, alert, only reports meaningful signals or blockers;
- finance role: precise, number/evidence oriented;
- industry role: market and supply-chain oriented;
- legal/risk role: cautious, source-bound;
- data/source role: explains source status, access issues, and confidence.

### WB-004: Chat Fixture JSON

Output:

```text
docs/workbuddy/office_chat_fixture.json
```

Create static demo data only. No secrets. No real personal data.

Required shape:

```json
{
  "channels": [],
  "roles": [],
  "messages": []
}
```

Messages:

- at least 30 group messages;
- at least 10 sentinel-to-general-manager private messages;
- at least 10 general-manager instruction messages;
- each message must include:
  - `message_id`;
  - `channel_id`;
  - `channel_type`;
  - `role_id`;
  - `timestamp`;
  - `message_type`;
  - `text`;
  - `evidence_refs`;
  - `confidence`;
  - `lane`.

Message text must follow persona positioning and have stronger internet-native
rhythm than generic enterprise copy, while remaining evidence-bound.

### WB-005: Visual QA Checklist

Output:

```text
docs/workbuddy/office_chat_ui_checklist.md
```

Checklist must cover:

- whether it resembles real chat/collaboration software;
- whether it avoids dashboard-card styling;
- whether it avoids marketing-page layout;
- whether it avoids yellow, earthy, or cheap-looking palettes;
- iOS-style spacing, motion, and input feel;
- message density;
- avatar/role readability;
- evidence badge clarity;
- desktop layout;
- mobile layout;
- no text overflow;
- no incoherent overlap;
- no fake AI-dashboard visual language.

### WB-006: Defect Report Template

Output:

```text
docs/workbuddy/office_chat_qa_template.md
```

Template fields:

- issue id;
- screenshot reference if available;
- viewport;
- affected area;
- problem;
- why it does not feel like real chat software;
- reference product;
- expected fix;
- severity;
- retest notes.

### WB-007: Copy Style Pack

Output:

```text
docs/workbuddy/persona_copy_style_pack.md
```

Write reusable copy rules and message examples:

- group-chat examples by persona;
- private sentinel alerts;
- general-manager commands;
- evidence-citation microcopy;
- blocked-source microcopy;
- weak-lead warning microcopy;
- no-data-found microcopy;
- next-action microcopy.

Style requirements:

- role-accurate;
- concise;
- business-investigation context;
- modern Chinese internet feel where natural;
- no exaggerated meme language;
- no childish slang;
- no fake certainty;
- no generic "as an AI" style.

## 3. Completion Gate

WorkBuddy may stop only after all seven files exist and are non-empty.

Before stopping, WorkBuddy must output:

```text
WORKBUDDY_DONE:
FILES_CREATED:
FILES_NOT_TOUCHED:
KNOWN_LIMITATIONS:
READY_FOR_CODEX_UI_REVIEW:
```

If fewer than seven files are complete, continue to the next file.

## 4. Commit Discipline

WorkBuddy must not use `git add .`.

Allowed staged files:

- `docs/workbuddy/office_chat_references.md`
- `docs/workbuddy/office_chat_structure.md`
- `docs/workbuddy/persona_chat_roles.md`
- `docs/workbuddy/office_chat_fixture.json`
- `docs/workbuddy/office_chat_ui_checklist.md`
- `docs/workbuddy/office_chat_qa_template.md`
- `docs/workbuddy/persona_copy_style_pack.md`

Commit message:

```text
docs(WB-UI): add office chat support materials
```
