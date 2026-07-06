# Office Chat QA Defect Report Template

Last updated: 2026-06-28
Purpose: standardized defect report format for office chat UI QA.
Aligned with: `docs/workbuddy/office_chat_fixture.json` and `core/roles.py`.

---

## Template

```markdown
### Issue #{issue_id}: {short_title}

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-{NNN} |
| **Reported by** | {name} |
| **Date** | {YYYY-MM-DD} |
| **Severity** | {critical / major / minor / cosmetic} |
| **Status** | {open / in_progress / fixed / wont_fix} |

#### Environment

| Field | Value |
|-------|-------|
| **Viewport** | {e.g., 1440x900 desktop, 375x812 mobile} |
| **Browser** | {e.g., Chrome 126, Safari 17, Edge 126} |
| **OS** | {e.g., Windows 11, macOS 14, iOS 17} |
| **Zoom** | {100% / 125% / etc.} |

#### Location

| Field | Value |
|-------|-------|
| **Affected area** | {e.g., left sidebar, chat stream, right evidence panel, composer, mobile bottom sheet} |
| **Component** | {e.g., message bubble, avatar, evidence badge, channel list item, tag chip} |
| **Screenshot reference** | {file path or description if no screenshot} |

#### Problem

{Describe what is wrong. Be specific.}

#### Why It Does Not Feel Like Real Chat Software

{Explain the gap between current appearance and real chat app expectations. Reference specific products.}

| Aspect | Current | Expected |
|--------|---------|----------|
| {e.g., message spacing} | {what you see} | {what real chat apps do} |

#### Reference Product

| Product | Feature/Pattern | Why It's Relevant |
|---------|-----------------|-------------------|
| {e.g., Feishu} | {e.g., message grouping} | {e.g., consecutive same-sender messages share one avatar} |

#### Expected Fix

{Describe what the fix should look like. Include specific values (px, colors, fonts) where applicable.}

#### Retest Notes

| Check | Pass? |
|-------|-------|
| Original issue resolved | {yes/no} |
| No regression in related areas | {yes/no} |
| Desktop viewport verified | {yes/no} |
| Mobile viewport verified | {yes/no} |
| No new console errors | {yes/no} |

#### Retest History

| Date | Tester | Result | Notes |
|------|--------|--------|-------|
| {YYYY-MM-DD} | {name} | {pass/fail} | {notes} |
```

---

## Severity Definitions

| Severity | Definition | Examples |
|----------|-----------|----------|
| **Critical** | Blocks core UX. Product cannot ship. | Messages not rendering, layout broken at standard viewports, horizontal overflow on mobile, evidence badges not clickable, fixture JSON parse failure |
| **Major** | Significantly degrades real-chat feel. Must fix before release. | Message density <3 visible, card shadows on messages, wrong color palette, missing timestamps, avatar grouping broken, tags not rendering, evidence panel hidden |
| **Minor** | Noticeable but doesn't break core experience. Fix in next iteration. | Typo in system message, slightly off spacing, transition animation missing, placeholder text could be better, tag color not matching severity |
| **Cosmetic** | Visual polish only. Nice to have. | Pixel-level alignment, hover state refinement, scrollbar styling, tag chip border-radius |

---

## Issue ID Convention

```
WB-UI-{NNN}
```

- `WB-UI`: WorkBuddy UI issue
- `NNN`: sequential 3-digit number, starting from 001

Examples:
- `WB-UI-001`: Message bubbles have card shadows
- `WB-UI-002`: Mobile right panel overflows horizontally
- `WB-UI-003`: Confidence badge colors indistinguishable
- `WB-UI-004`: Message tags not rendered
- `WB-UI-005`: Evidence panel does not open on badge click

---

## Example Defect Report #1

### Issue #WB-UI-001: Message bubbles have Material Design card shadows

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-001 |
| **Reported by** | WorkBuddy QA |
| **Date** | 2026-06-28 |
| **Severity** | Major |
| **Status** | open |

#### Environment

| Field | Value |
|-------|-------|
| **Viewport** | 1440x900 desktop |
| **Browser** | Chrome 126 |
| **OS** | Windows 11 |
| **Zoom** | 100% |

#### Location

| Field | Value |
|-------|-------|
| **Affected area** | Chat stream |
| **Component** | Message bubble |
| **Screenshot reference** | (screenshot of message with visible box-shadow) |

#### Problem

Each message bubble has `box-shadow: 0 2px 8px rgba(0,0,0,0.1)` and `border-radius: 12px`, giving it a Material Design card appearance. Real chat applications do not use card shadows on individual messages.

#### Why It Does Not Feel Like Real Chat Software

Card shadows create visual separation between messages that shouldn't exist. In real chat apps (WeChat, Feishu, Slack, iMessage), messages flow as a continuous conversation. Shadows make each message feel like an isolated widget.

| Aspect | Current | Expected |
|--------|---------|----------|
| Message shadow | `box-shadow: 0 2px 8px rgba(0,0,0,0.1)` | No shadow |
| Border radius | 12px | 6-8px |
| Visual feel | Card grid | Conversation stream |

#### Reference Product

| Product | Feature/Pattern | Why It's Relevant |
|---------|-----------------|-------------------|
| WeChat | Bubble style | No shadow, 4px border-radius, continuous flow |
| iMessage | Bubble grouping | Messages flow together, only separated by sender change |
| Feishu | Message density | No shadows, tight spacing, conversation feel |

#### Expected Fix

Remove `box-shadow` from `.message-bubble`. Reduce `border-radius` from 12px to 6-8px. Ensure consecutive messages from the same sender have reduced top margin (4px instead of 12px).

#### Retest Notes

| Check | Pass? |
|-------|-------|
| Original issue resolved | |
| No regression in related areas | |
| Desktop viewport verified | |
| Mobile viewport verified | |
| No new console errors | |

#### Retest History

| Date | Tester | Result | Notes |
|------|--------|--------|-------|
| | | | |

---

## Example Defect Report #2

### Issue #WB-UI-002: Warm/beige color palette looks like a marketing page

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-002 |
| **Reported by** | WorkBuddy QA |
| **Date** | 2026-06-28 |
| **Severity** | Major |
| **Status** | open |

#### Problem

The UI uses a warm beige background (`#FFF8F0`) and amber accent colors (`#F59E0B`), which makes the product look like a budget dashboard or marketing page rather than a premium enterprise investigation tool.

#### Why It Does Not Feel Like Real Chat Software

No major chat application (WeChat, Feishu, Slack, Discord, iMessage) uses warm/earthy color palettes. They all use cool neutrals: white, light gray, dark gray, with blue or purple accents. Warm colors in a chat UI signal "cheap template" or "marketing page."

| Aspect | Current | Expected |
|--------|---------|----------|
| Background | `#FFF8F0` (warm beige) | `#FFFFFF` or `#F9FAFB` (cool white/gray) |
| Accent | `#F59E0B` (amber) | `#2563EB` (blue) or `#7C3AED` (purple) |

#### Expected Fix

Replace all warm/earthy colors with cool neutrals. Use the approved palette from `office_chat_structure.md` section 6. Background: `#FFFFFF`. Accent: `#2563EB`. No amber, orange, yellow, or beige anywhere in the UI.

#### Retest Notes

| Check | Pass? |
|-------|-------|
| Original issue resolved | |
| No regression in related areas | |
| Desktop viewport verified | |
| Mobile viewport verified | |
| No new console errors | |

---

## Example Defect Report #3

### Issue #WB-UI-003: Message density too low — only 2-3 messages visible at 13-inch

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-003 |
| **Reported by** | WorkBuddy QA |
| **Date** | 2026-06-28 |
| **Severity** | Major |
| **Status** | open |

#### Problem

Only 2-3 messages are visible on a 13-inch laptop screen at 100% zoom. Real chat apps show 5-8 messages. The excessive padding between messages (20px+) makes the chat feel sparse and non-functional.

#### Why It Does Not Feel Like Real Chat Software

Chat apps are designed for scanning conversations quickly. Low message density forces excessive scrolling and breaks the "live conversation" feel. It's the #1 signal of a template-built UI rather than a purpose-built chat interface.

#### Expected Fix

Reduce inter-message padding from 20px to 8-12px. Reduce avatar size from 48px to 36px. Reduce name+timestamp line height. Group consecutive messages from the same sender with 4px gap instead of full spacing.

#### Retest Notes

| Check | Pass? |
|-------|-------|
| Original issue resolved | |
| No regression in related areas | |
| Desktop viewport verified | |
| Mobile viewport verified | |
| No new console errors | |

---

## Example Defect Report #4

### Issue #WB-UI-004: Message tags (evidence-linked / assignment-linked / system-state) not rendered

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-004 |
| **Reported by** | WorkBuddy QA |
| **Date** | 2026-06-28 |
| **Severity** | Major |
| **Status** | open |

#### Environment

| Field | Value |
|-------|-------|
| **Viewport** | 1440x900 desktop |
| **Browser** | Chrome 126 |
| **OS** | Windows 11 |
| **Zoom** | 100% |

#### Location

| Field | Value |
|-------|-------|
| **Affected area** | Chat stream — each message bubble |
| **Component** | Message tag chip |
| **Screenshot reference** | (screenshot showing messages without any tag chips) |

#### Problem

Fixture messages carry `tags` field with values `evidence-linked`, `assignment-linked`, and/or `system-state`. The UI is not rendering any visual indicator for these tags. The right evidence panel does not filter by tag. The user cannot distinguish an evidence-linked message from a routine system message at a glance.

#### Why It Does Not Feel Like Real Chat Software

Purpose-built investigation tools (e.g., Linear, Notion) and professional chat apps (Feishu) use inline metadata chips to annotate messages. Without tag rendering, the chat surface is indistinguishable from generic chat; the investigation context is lost.

| Aspect | Current | Expected |
|--------|---------|----------|
| Tag chips | Not rendered | Small pill chips on message: 🔗 证据 / 📌 任务 / 🔧 系统 |
| Evidence panel link | None | Clicking 🔗 chip opens evidence panel filtered to that message's `evidence_refs` |

#### Reference Product

| Product | Feature/Pattern | Why It's Relevant |
|---------|-----------------|-------------------|
| Linear | Issue type chips | Inline metadata visible without opening details |
| Feishu | Message reactions + info bar | Metadata attached to messages without cluttering flow |

#### Expected Fix

Render tag chips as small pill labels below the message text. Use muted colors:
- `evidence-linked` → blue chip, icon 🔗, label "证据"
- `assignment-linked` → orange chip, icon 📌, label "任务"
- `system-state` → gray chip, icon ⚙, label "系统"

Chip height: 18px. Font size: 11px. Padding: 2px 6px. Border-radius: 9px. Do not use full-width banners.

---

## Example Defect Report #5

### Issue #WB-UI-005: Evidence panel does not open when clicking evidence badge

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-005 |
| **Reported by** | WorkBuddy QA |
| **Date** | 2026-06-28 |
| **Severity** | Critical |
| **Status** | open |

#### Location

| Field | Value |
|-------|-------|
| **Affected area** | Chat stream → right evidence panel |
| **Component** | Evidence badge / `evidence-linked` tag chip |
| **Screenshot reference** | (screenshot of badge that is not clickable) |

#### Problem

Messages with `evidence_refs` in the fixture have evidence badges visible, but clicking them does not open or populate the right-side evidence panel. The `access_status`, `confidence`, and `source` fields in `evidence_refs` are not surfaced anywhere in the UI.

#### Why It Does Not Feel Like Real Chat Software

The investigation workflow depends on evidence traceability. A user who sees "天眼查" in a message must be able to click through to the actual source record. Without this, the UI is a presentation layer with no depth — closer to a mockup than a working tool.

| Aspect | Current | Expected |
|--------|---------|----------|
| Evidence badge click | No response | Opens right panel, loads evidence item with source/confidence/access_status |
| Right panel default | Empty | Shows evidence items linked to currently selected message |

#### Expected Fix

Wire evidence badge click to open right panel. Map `evidence_refs[].evidence_id` to the evidence panel's item renderer. Display: source name, `access_status` chip (live / fixture / cached), confidence badge (high/medium/low), identifier string.

---

## Example Defect Report #6

### Issue #WB-UI-006: Fixture data not labeled — live and demo data visually identical

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-006 |
| **Reported by** | WorkBuddy QA |
| **Date** | 2026-06-28 |
| **Severity** | Minor |
| **Status** | open |

#### Problem

Some `evidence_refs` in the fixture have `access_status: "fixture"`. The UI renders these identically to `access_status: "live"` sources. Users cannot distinguish demo data from real investigation data.

#### Expected Fix

When `access_status === "fixture"`, render a `◇ 演示数据` chip next to the source name. Add a banner in the right panel header: "当前使用演示数据，非实时调查结果。" Use muted styling (gray, not blue) for fixture evidence items.

---

## QA Notes for Fixture-Driven Review

When conducting QA with `office_chat_fixture.json` loaded:

1. **Role display names** must match `docs/workbuddy/persona_copy_style_pack.md` Section 0 table. `zhang-tie-zhu` must display as "张铁柱", not "li-you-cheng" or any old alias.

2. **Tag chips** must appear on messages where `tags` array is non-empty. Check: `evidence-linked`, `assignment-linked`, `system-state`.

3. **DM channel** (`dm-sentinel-gm`): only `an-shao` and `qian-shou-zheng` messages should appear. No other roles.

4. **GM instructions**: messages with `message_type: "action"` from `qian-shou-zheng` should have a distinct visual treatment (e.g., left border accent or bold sender name).

5. **Confidence field**: messages with `confidence: "low"` should render a muted confidence badge. `confidence: null` should render no badge (not "null" text).

6. **Lane field**: messages with `lane: 1` or `lane: 2` should be filterable. `lane: null` means cross-lane or GM-level.
