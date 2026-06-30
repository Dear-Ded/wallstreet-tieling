# Office Chat Visual QA Checklist

Last updated: 2026-06-27
Purpose: structured checklist for verifying the office chat UI meets real-chat-software quality standards.

---

## 1. Authenticity Check: Does It Look Like Real Chat Software?

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 1.1 | Message density | 5-8 messages visible on 13-inch laptop viewport at 100% zoom | Only 2-3 messages visible due to excessive padding |
| 1.2 | Bubble style | Flat or minimal border-radius (<=8px). No box-shadow on messages. | Card-style with shadows, gradient backgrounds, or border-radius >12px |
| 1.3 | Bubble tails | Messages have visual continuity with sender (tail, caret, or grouping) | All messages are isolated rounded rectangles with no sender connection |
| 1.4 | Avatar grouping | Consecutive messages from same sender share one avatar. Avatar reappears only after 5+ min gap or sender change. | Every message shows full avatar + name |
| 1.5 | Timestamps | Relative: "2分钟前", "14:32". Absolute timestamps only on hover or in details. | ISO 8601 timestamps ("2026-06-27T14:03:00") as primary display |
| 1.6 | System messages | Centered, gray (#9CA3AF), smaller font (12px), with subtle dividers | System messages styled like user messages with avatars |
| 1.7 | Typing indicator | Animated dots or subtle pulse, not a text label | "正在输入..." as a text string |
| 1.8 | Unread indicator | Small red dot (6-8px). No number count. | Numbered badge ("3") on channels |
| 1.9 | @mention | Highlighted with accent background color, not just colored text | @mention indistinguishable from normal text |
| 1.10 | Link previews | Inline rich preview or plain URL. No broken placeholder cards. | Empty gray boxes for unfetched links |

---

## 2. Anti-Dashboard Check: Does It Avoid AI Dashboard Styling?

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 2.1 | No card layout | Messages are not wrapped in Material Design cards | Each message is a white card with border and shadow |
| 2.2 | No hero section | No large banner, illustration, or CTA above the chat | "Welcome to the Investigation Hub" hero with gradient |
| 2.3 | No dashboard widgets | Chat stream is only messages. No side widgets for "stats" or "progress" in the main stream. | KPIs, pie charts, or progress bars embedded in the chat area |
| 2.4 | No marketing language | No "Powered by AI", "Revolutionary", "Next-gen" in the UI | Marketing copy in headers, footers, or empty states |
| 2.5 | No decorative gradients | Background is solid or very subtle. No gradient blobs or glowing orbs. | Purple-to-blue gradient background behind messages |
| 2.6 | No animated avatars | Avatars are static circles with initials or solid colors. | Bouncing, pulsing, or rotating avatar animations |

---

## 3. Color Palette Check: Does It Avoid Yellow/Earthy/Cheap Palettes?

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 3.1 | Primary background | White (#FFFFFF) or near-white (#F9FAFB) for light mode. Dark (#1A1A2E or #0D1117) for dark mode. | Beige, cream, warm yellow, or "parchment" backgrounds |
| 3.2 | Accent colors | Cool/professional: blue (#2563EB), slate (#64748B), teal (#0D9488). No warm yellows or oranges as primary. | Orange (#F59E0B) or amber (#D97706) as the dominant UI color |
| 3.3 | Role colors | Distinct, professional. See `office_chat_structure.md` section 6 for approved palette. | Pastel or neon role colors |
| 3.4 | Message bubbles | Self: blue or dark. Others: white or light gray. WeChat green is acceptable if executed well. | Yellow, orange, or brown bubbles |
| 3.5 | Evidence badges | Green (high), blue (medium), amber (low), gray (unverified). Subtle, not neon. | Bright saturated badge colors that distract from message text |
| 3.6 | Overall feel | "Enterprise workspace" or "premium chat app" | "Budget SaaS dashboard" or "startup landing page" |

---

## 4. iOS-Style Polish Check

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 4.1 | Typography | System font stack. SF Pro on macOS/iOS, Segoe UI on Windows, Roboto on Android. Consistent weight hierarchy. | Mixed fonts, decorative fonts, or incorrect font weights |
| 4.2 | Spacing | 8px grid system. Consistent padding: 12-16px in chat, 8-12px between messages. | Random spacing values (7px, 13px, 19px) |
| 4.3 | Border radius | Consistent: 6-8px for bubbles, 4px for badges, 8px for input. | Mixed border-radius values across elements |
| 4.4 | Transitions | Subtle: 150-200ms ease-out for panel open/close, message appear. No spring or bounce animations. | 500ms+ animations or bouncy easing |
| 4.5 | Input field | Rounded (20-24px border-radius). Placeholder text in gray (#9CA3AF). Auto-expand smooth. | Square input with sharp corners |
| 4.6 | Send button | Appears when text is non-empty. Smooth opacity/scale transition. | Send button always visible but disabled (gray) |
| 4.7 | Scroll behavior | Smooth scroll to bottom on new message. "Scroll to bottom" floating button when scrolled up. | Abrupt jump to bottom on every new message |
| 4.8 | Back navigation (mobile) | Standard iOS-style back chevron (<) with slide transition. | Custom back button that breaks platform convention |

---

## 5. Desktop Layout Check (>=1280px)

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 5.1 | Three columns | Left sidebar (280px), center chat (flex), right panel (320px, togglable) | Two-column only or single-column on desktop |
| 5.2 | Left sidebar | Sticky. Scrollable channel list. Search/filter at top. Active channel highlighted. | Sidebar scrolls with chat, or missing active state |
| 5.3 | Top bar | 56px height. Channel name left. Actions right. Sticky. | Top bar missing or too tall (>64px) |
| 5.4 | Composer | Fixed to bottom. Auto-height 48-200px. Send button right-aligned. | Composer scrolls with messages |
| 5.5 | Right panel | Slides in from right. 320px width. Closable. Shows evidence for selected message. | Right panel always visible and empty |
| 5.6 | No horizontal scroll | All columns fit within viewport. No horizontal scrollbar at any width >=1280px. | Horizontal scrollbar appears |
| 5.7 | Resize stability | Layout adjusts gracefully when browser width changes. Right panel collapses first, then left sidebar. | Layout breaks or elements overlap on resize |

---

## 6. Mobile Layout Check (<768px)

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 6.1 | Single column | Only one panel visible at a time. No side-by-side panels. | Two panels squeezed into mobile width |
| 6.2 | No horizontal overflow | All content wraps within viewport. No horizontal scroll. | Text, badges, or evidence cards overflow horizontally |
| 6.3 | Left sidebar | Full-screen overlay or slide-in from left. Dismissed on channel select or back tap. | Sidebar permanently visible, eating 40% of screen |
| 6.4 | Right panel | Bottom sheet (60% height) with drag handle. Triggered by evidence badge tap. | Right panel as a narrow sidebar on mobile |
| 6.5 | Top bar | 48px. Back arrow + channel name. Sticky. | Top bar missing back navigation |
| 6.6 | Composer | Fixed to bottom. 48px min height. Does not scroll. | Composer hidden behind keyboard or scrolls away |
| 6.7 | Touch targets | Minimum 44x44px for all interactive elements (buttons, badges, channel items). | Tiny tap targets (<40px) |
| 6.8 | Message bubbles | Max-width 80% of screen. Text wraps. No truncated messages. | Bubbles fixed-width and overflowing |
| 6.9 | Avatar size | 28-32px. Smaller than desktop (36px). | 36px+ avatars on mobile wasting space |
| 6.10 | Font size | 15px body text (slightly larger than desktop 14px for readability). | 12px body text on mobile |

---

## 7. Evidence Badge Clarity

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 7.1 | Badge visibility | Clearly distinguishable from message text. Subtle background + border. | Badges blend into message text |
| 7.2 | Confidence levels | Four visually distinct levels: high (green), medium (blue), low (amber), unverified (gray). | All confidence badges look the same |
| 7.3 | Source chips | Source status clearly shown: online (green dot), rate-limited (amber), blocked (red), cached (gray). | Source status missing or ambiguous |
| 7.4 | Badge interaction | Clickable. Opens evidence detail in right panel or bottom sheet. | Badges are static, non-interactive text |
| 7.5 | Badge density | Max 3 badges per message. If more, show "+N more" expander. | 5+ badges stacking vertically and breaking message layout |

---

## 8. Avatar and Role Readability

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 8.1 | Avatar distinction | Each persona has a unique color + initial. Colors follow the approved lane palette. | Two personas share the same color |
| 8.2 | Name readability | Role name + lane tag visible. Font 13-14px, medium weight. | Names too small (<12px) or missing |
| 8.3 | Lane tag | Small tag next to name: "[财务]", "[法务]", etc. Consistent styling. | Lane tags missing or inconsistent |
| 8.4 | Online indicator | Green dot (6px) on avatar for active personas. Gray for standby. No dot for offline. | Online status shown as text badge or missing entirely |
| 8.5 | DM distinction | DM channels show recipient avatar + name. Distinct from group channels in sidebar. | DM and group channels visually identical |

---

## 9. Content Integrity

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 9.1 | No fake certainty | "确信" / "肯定" only when confidence=high. "疑似" / "线索" / "待核实" for lower confidence. | Low-confidence messages using definitive language |
| 9.2 | Evidence grounding | Every factual claim in a message references an evidence_ref or is marked as system_instruction. | Claims without any source reference |
| 9.3 | No AI voice | No "作为一个人工智能", "根据我的分析", "I recommend". Messages read as human professional chat. | Generic AI assistant language patterns |
| 9.4 | No secret exposure | No API keys, tokens, cookies, file paths, or internal URLs in message text. | Debug info or credentials in chat |
| 9.5 | Role-appropriate tone | Each message matches its persona's defined tone (see `persona_chat_roles.md`). | A data source role giving financial advice, or sentinel making suggestions |

---

## 10. Empty States and Edge Cases

| # | Check | Pass Criteria | Fail Signal |
|---|-------|--------------|-------------|
| 10.1 | No channel selected | Center area shows subtle guidance: "选择一个频道开始" | Blank white space or broken layout |
| 10.2 | Empty channel | Shows channel name + description + "暂无消息" | Blank or error state |
| 10.3 | No evidence selected | Right panel: "选择一条消息查看证据" | Empty panel with no guidance |
| 10.4 | Long message | Text wraps correctly. No overflow. Bubble expands vertically. | Text truncated with "..." or overflowing |
| 10.5 | Very long single word | Breaks with word-break: break-word. No overflow. | Long unbroken string (URL, hash) causes horizontal scroll |
| 10.6 | Many rapid messages | Stream remains readable. Auto-scroll keeps up. No layout shift. | Messages overlap or layout jumps |
| 10.7 | All sources offline | Source status channel shows all red. Chat remains functional. | UI breaks or shows error when sources are down |

---

## Quick Reference: Top 5 Deal-Breakers

These must pass before any review:

1. **No card shadows on messages.** If messages look like Material Design cards, stop and fix.
2. **No yellow/warm/earthy palette.** If the background is beige or the accent is orange, stop and fix.
3. **Message density >= 5 visible.** If only 2-3 messages fit on screen, stop and fix.
4. **Relative timestamps.** If messages show ISO timestamps, stop and fix.
5. **No horizontal overflow on mobile.** If anything scrolls sideways at 375px width, stop and fix.
