# Office Chat QA Defect Report Template

Last updated: 2026-06-27
Purpose: standardized defect report format for office chat UI QA.

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
| **Component** | {e.g., message bubble, avatar, evidence badge, channel list item} |
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
| **Critical** | Blocks core UX. Product cannot ship. | Messages not rendering, layout broken at standard viewports, horizontal overflow on mobile, evidence badges not clickable |
| **Major** | Significantly degrades real-chat feel. Must fix before release. | Message density <3 visible, card shadows on messages, wrong color palette, missing timestamps, avatar grouping broken |
| **Minor** | Noticeable but doesn't break core experience. Fix in next iteration. | Typo in system message, slightly off spacing, transition animation missing, placeholder text could be better |
| **Cosmetic** | Visual polish only. Nice to have. | Pixel-level alignment, hover state refinement, scrollbar styling |

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

---

## Example Defect Report

### Issue #WB-UI-001: Message bubbles have Material Design card shadows

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-001 |
| **Reported by** | WorkBuddy QA |
| **Date** | 2026-06-27 |
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

## Issue #WB-UI-002: Placeholder — Yellow/warm color palette

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-002 |
| **Reported by** | WorkBuddy QA |
| **Date** | 2026-06-27 |
| **Severity** | Major |
| **Status** | open |

#### Problem

The UI uses a warm beige background (#FFF8F0) and amber accent colors (#F59E0B), which makes the product look like a budget dashboard or marketing page rather than a premium enterprise investigation tool.

#### Why It Does Not Feel Like Real Chat Software

No major chat application (WeChat, Feishu, Slack, Discord, iMessage) uses warm/earthy color palettes. They all use cool neutrals: white, light gray, dark gray, with blue or purple accents. Warm colors in a chat UI signal "cheap template" or "marketing page."

| Aspect | Current | Expected |
|--------|---------|----------|
| Background | #FFF8F0 (warm beige) | #FFFFFF or #F9FAFB (cool white/gray) |
| Accent | #F59E0B (amber) | #2563EB (blue) or #7C3AED (purple) |

#### Expected Fix

Replace all warm/earthy colors with cool neutrals. Use the approved palette from `office_chat_structure.md` section 6. Background: #FFFFFF. Accent: #2563EB. No amber, orange, yellow, or beige anywhere in the UI.

---

## Issue #WB-UI-003: Placeholder — Message density too low

| Field | Value |
|-------|-------|
| **Issue ID** | WB-UI-003 |
| **Reported by** | WorkBuddy QA |
| **Date** | 2026-06-27 |
| **Severity** | Major |
| **Status** | open |

#### Problem

Only 2-3 messages are visible on a 13-inch laptop screen at 100% zoom. Real chat apps show 5-8 messages. The excessive padding between messages (20px+) makes the chat feel sparse and non-functional.

#### Why It Does Not Feel Like Real Chat Software

Chat apps are designed for scanning conversations quickly. Low message density forces excessive scrolling and breaks the "live conversation" feel. It's the #1 signal of a template-built UI rather than a purpose-built chat interface.

#### Expected Fix

Reduce inter-message padding from 20px to 8-12px. Reduce avatar size from 48px to 36px. Reduce name+timestamp line height. Group consecutive messages from the same sender with 4px gap instead of full spacing.
