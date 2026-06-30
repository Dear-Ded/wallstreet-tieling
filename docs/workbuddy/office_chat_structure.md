# Office Chat Structure

Last updated: 2026-06-27
Purpose: concrete UI requirements for the persona office chat surface.

---

## 1. High-Level Layout (Desktop, ≥1280px)

```
┌──────────┬──────────────────────────────┬─────────────┐
│  Left    │  Center                      │  Right      │
│  Sidebar │  Chat Stream                 │  Evidence   │
│  280px   │  flex: 1                     │  Panel      │
│          │                              │  320px      │
│ Channel  │  ┌─ Top Bar (56px) ───────┐  │  (togglable)│
│ List     │  │ Channel Name + Actions  │  │             │
│          │  └─────────────────────────┘  │  Evidence   │
│ ──────── │                              │  Cards      │
│ # general│  ┌─ Message ───────────────┐  │             │
│ # finance│  │ Avatar Name  Time       │  │  Sources    │
│ # legal  │  │ Message body            │  │             │
│ # sentinel│ │ Evidence badges         │  │  Confidence │
│          │  └─────────────────────────┘  │             │
│ ──────── │                              │  ─────────── │
│ DM: 暗哨  │  ┌─ Message ───────────────┐  │  Evidence   │
│          │  │ ...                      │  │  Detail     │
│          │  └─────────────────────────┘  │             │
│          │                              │             │
│          │  ┌─ Composer (auto-h) ─────┐  │             │
│          │  │ Input + Send            │  │             │
│          │  └─────────────────────────┘  │             │
└──────────┴──────────────────────────────┴─────────────┘
```

### Left Sidebar (280px fixed)
- Channel search/filter at top (sticky).
- Channel list with unread indicators.
- Channel types: group channels (prefix `#`) and direct messages (prefix `@`).
- Active channel highlighted with accent background.
- Channel name, last message preview, timestamp.
- Direct message list below group channels, separated by a divider.
- Online/active persona indicators (small green dot on DM avatars).
- Minimum one DM channel: "暗哨" (Sentinel → General Manager private).

### Center — Top Bar (56px)
- Channel name (e.g., "# 尽调大厅" or "@ 暗哨").
- Channel description or topic on hover/second line (optional, 12px, gray).
- Right-aligned actions: search messages, pin panel toggle, channel info.
- For DM channels: show recipient name and online status.

### Center — Chat Stream (flex: 1, overflow-y: auto)
- Scrollable message area. Auto-scroll to bottom on new messages.
- Messages grouped by sender: consecutive messages from same persona share one avatar block.
- Group boundary: new avatar + name when sender changes or >5 minutes gap.
- Message types: text, evidence_card, system, action.
- Loading indicator for older messages at top (on scroll up).

### Center — Composer (auto-height, min 48px, max 200px)
- Text input with auto-expand.
- Send button (appears when text is non-empty).
- @mention support: type `@` to trigger persona picker.
- Enter to send, Shift+Enter for newline.
- Placeholder text: context-aware (e.g., "发消息到 #尽调大厅..." or "私信暗哨...").

### Right Panel (320px, togglable)
- Visible when a message with evidence_refs is selected or when toggled on.
- Shows evidence cards for the selected message.
- Evidence card contains: source name, source type, confidence badge, timestamp, summary, link to full evidence.
- If no message selected, shows channel info or "no evidence selected" empty state.
- On mobile: slides up as a bottom sheet.

---

## 2. Mobile Layout (<768px)

```
┌──────────────────┐
│  Top Bar (48px)  │
│  Channel Name    │
│  + Back / Panel  │
├──────────────────┤
│                  │
│  Chat Stream     │
│  (full width)    │
│                  │
│                  │
├──────────────────┤
│  Composer (48px) │
│  Input + Send    │
└──────────────────┘
```

### Mobile rules
- Single column always. No side-by-side panels.
- Left sidebar: hidden. Accessed via back button from chat view, or shown as a full-screen overlay from a hamburger/back navigation.
- Right evidence panel: hidden by default. Triggered by tapping an evidence badge. Opens as a bottom sheet covering 60% of the screen, with a drag handle.
- Top bar: shows channel name. Back arrow on the left returns to channel list. Evidence toggle on the right.
- Composer: fixed to bottom. Does not scroll with the chat stream.
- Message bubbles: max-width 80% of screen width. Text must wrap.
- No horizontal scroll anywhere.
- Avatar size: 28px (smaller than desktop 36px).
- Font size: 15px body (vs 14px desktop — mobile needs slightly larger touch targets).

---

## 3. Channel Types

### Group Channels

| Channel ID | Name | Purpose |
|------------|------|---------|
| `ch-general` | # 尽调大厅 | All personas. General investigation discussion. |
| `ch-finance` | # 财务线 | Finance, accounting, capital flow personas. |
| `ch-legal` | # 法务线 | Legal, compliance, risk personas. |
| `ch-industry` | # 行业线 | Industry, supply chain, market personas. |
| `ch-sources` | # 数据源状态 | Data source status, access issues, confidence updates. |

Group channel rules:
- All personas in the channel can read all messages.
- Personas outside the channel's lane cannot see its messages.
- Channel membership is determined by persona lane, not user choice.
- Each persona can be in 1-3 channels.

### Direct Messages

| DM ID | Participants | Purpose |
|-------|-------------|---------|
| `dm-sentinel-gm` | 暗哨 → 铁总 | Sentinel reports critical signals, blockers, and sensitive findings privately to the General Manager. |

DM rules:
- Only the two participants can see the messages.
- DM messages do not appear in group channels.
- DM notifications are higher priority than group notifications.

---

## 4. Message Types

### `text`
Standard chat message. Contains `text` field with optional `evidence_refs`.

```
┌──────────────────────────────────┐
│ [Avatar] 财务-周望              │
│          14:32                  │
│                                  │
│ 目标公司近三年经营性现金流持续   │
│ 为负，2025年净流出2.3亿。       │
│                                  │
│  [证据: 2025年报] [置信度: 高]   │
└──────────────────────────────────┘
```

### `evidence_card`
A rich card that summarizes an evidence item. Inline in the chat stream.

```
┌──────────────────────────────────┐
│ [Avatar] 数据源-天眼查          │
│          14:35                  │
│                                  │
│  ┌─ Evidence Card ────────────┐ │
│  │ 来源: 天眼查               │ │
│  │ 类型: 工商变更             │ │
│  │ 时间: 2026-03-15           │ │
│  │ 摘要: 法定代表人由张X变   │ │
│  │       更为李X              │ │
│  │ 置信度: 高 (官方公示)     │ │
│  │ [查看详情]                 │ │
│  └─────────────────────────────┘ │
└──────────────────────────────────┘
```

### `system`
System-generated status messages. Centered, gray, smaller font.

```
            ── 数据源 "天眼查" 已连接 ──
            ── 暗哨 加入了 #尽调大厅 ──
            ── 证据 E-042 置信度从 "中" 更新为 "高" ──
```

### `action`
A message that includes a suggested next action. Rendered with a subtle accent border on the left.

```
┌──────────────────────────────────┐
│ [Avatar] 铁总                    │
│          14:40                  │
│                                  │
│ ▎周望，把近三年现金流和同行业    │
│ ▎对比拉出来。一小时内。          │
│                                  │
│  [指向: @财务-周望]              │
└──────────────────────────────────┘
```

---

## 5. Evidence Badge System

Every message with `evidence_refs` shows inline badges below the message body.

### Badge format
```
[证据: {source_name}] [置信度: {high|medium|low|unverified}]
```

### Confidence levels

| Level | Badge Color | Meaning |
|-------|-------------|---------|
| `high` | Green | Official source, directly verified. |
| `medium` | Blue | Credible source, indirect or inferred. |
| `low` | Yellow/Amber | Weak signal, single source, or unverified claim. |
| `unverified` | Gray | Source not yet checked. |

### Source status chips (in the right panel)

| Status | Chip |
|--------|------|
| Connected | `● 在线` green |
| Rate-limited | `◐ 限流` amber |
| Blocked | `○ 不可用` red |
| Cached | `◉ 缓存` gray |
| Fixture | `◇ 演示数据` gray |

### Evidence interaction
- Click badge → opens evidence card in right panel.
- Click source name → opens source detail (access method, last check time, rate limits).
- Click confidence → shows confidence history if available.

---

## 6. Role Presence

### Online indicators
- Green dot (6px) on avatar: persona is active and can respond.
- Gray dot: persona is in standby (no active investigation).
- No dot: persona is offline (not in the current investigation session).

### Lane indicators
- Each persona has a lane tag shown next to their name: `[财务]` `[法务]` `[行业]` `[数据源]` `[暗哨]` `[总经理]`.
- Lane determines channel membership and message visibility.

### Persona name colors (borrowed from Discord pattern)
| Lane | Color | Hex |
|------|-------|-----|
| 总经理 | Crimson | `#DC2626` |
| 暗哨 | Purple | `#7C3AED` |
| 财务 | Blue | `#2563EB` |
| 法务/风险 | Amber | `#D97706` |
| 行业 | Teal | `#0D9488` |
| 数据源 | Slate | `#64748B` |

---

## 7. Message Search / Filter

### Search bar (in top bar or left sidebar)
- Full-text search across all messages in visible channels.
- Results shown in a dropdown or replace the chat stream temporarily.

### Lane filter (in chat stream header)
- Dropdown or tab bar to filter messages by lane: "全部" / "财务" / "法务" / "行业" / "数据源".
- Selecting a lane filters the chat stream to show only messages from personas in that lane.

### Evidence filter
- Toggle to show only messages with `evidence_refs`.
- Toggle to show only messages with `confidence: low` or `confidence: unverified`.

---

## 8. Notification Rules

### Unread badges
- Small red dot on channel in left sidebar.
- No count number (avoids anxiety-inducing notification counts).

### Priority levels
1. **Critical**: Sentinel DM, General Manager @mention. Red dot + subtle animation.
2. **Important**: @mention in group channel. Red dot.
3. **Normal**: New message in active channel. Gray dot.
4. **Low**: System messages, source status updates. No notification.

### Sound (optional, configurable)
- Short, subtle sound for critical notifications only.
- No sound for normal messages.
- User-configurable on/off.

---

## 9. Empty States

### No channel selected
- Center area shows a subtle illustration or text: "选择一个频道开始" / "Select a channel".

### No messages in channel
- Center area shows: "暂无消息" with channel description.

### No evidence selected
- Right panel shows: "选择一条消息查看证据" / "Select a message to view evidence".

### No search results
- Search dropdown shows: "未找到相关消息" with suggestion to broaden search.

---

## 10. Accessibility Requirements

- All interactive elements must be keyboard-navigable.
- Message text must have sufficient color contrast (WCAG AA minimum).
- Evidence badges must be distinguishable by shape and text, not just color.
- Screen reader: announce message sender, time, and content in order.
- Focus indicators must be visible on all interactive elements.
