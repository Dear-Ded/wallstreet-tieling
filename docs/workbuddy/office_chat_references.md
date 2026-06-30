# Office Chat Interface References

Last updated: 2026-06-27
Purpose: layout and feel observations for persona office chat UI. No code, no screenshots.

---

## 1. Feishu / Lark

### Layout
- Three-column desktop: left sidebar (conversation list + search) → center chat stream → right detail/info panel.
- Mobile: single-column with bottom tab navigation. Chat list → tap into thread → back.

### Chat stream
- Compact message density: ~5-7 messages visible on a 13-inch screen.
- Avatar on the left of each message, 36px circular. Name + timestamp above message body.
- Group chat shows sender name; 1-on-1 hides it.
- Messages separated by 8-12px, not card-style.
- System messages (join/leave/pin) are centered, gray, smaller font.
- "Typing" indicator is a subtle animated dot at the bottom of the stream.

### Composer
- Rich toolbar above the input: emoji, @mention, file, image, video, code block, todo.
- Input area auto-expands to ~6 lines then scrolls.
- Send button on the right, or Enter to send (configurable).

### Right panel
- Context-sensitive: shows group info, pinned messages, shared files, or a specific message's thread.
- Not always visible — slides in from right on demand.

### What makes it feel real
- Message bubbles are not cards. No border-radius > 8px. No box-shadow on messages.
- Timestamps are relative ("3分钟前") not ISO.
- Unread badge: small red dot, not a pill with a number.
- @mentions highlight in blue, with a subtle background.
- Online presence: green dot on avatar. Not a separate status bar.

### What would make it feel fake
- Card-based message layout with shadows.
- Gradient backgrounds on messages.
- Excessive padding (20px+ between messages).
- Emoji reactions as the primary interaction.
- Dashboard-style widgets in the chat stream.

---

## 2. DingTalk (钉钉)

### Layout
- Three-column desktop similar to Feishu. Left sidebar is more compact.
- "Work" tab vs "Chat" tab at the bottom on mobile.
- Top bar shows current conversation name + quick actions (call, video, more).

### Chat stream
- Dense: more messages visible than Feishu. Smaller avatars (32px).
- Read receipts: "已读" with count. Very important for DingTalk's work culture.
- Message status: sent / delivered / read indicators on each message.
- File and image previews inline, not just links.
- "DING" function: urgent message that forces a notification.

### Composer
- Simpler than Feishu: text input + send. Additional features in a "+" menu.
- @mention with a dedicated shortcut (type @).
- Voice message button on mobile.

### Right panel
- Task list, calendar, or approval flow — not just chat info.
- Work-oriented: DingTalk integrates task management into the chat surface.

### What makes it feel real
- Work context baked into the chat: tasks, approvals, calendars appear inline.
- Read status is prominent — it signals urgency and accountability.
- Clean, almost utilitarian typography. No decorative elements.
- System notifications for "已读"/"未读" are functional, not decorative.

### What would make it feel fake
- Animated avatars or decorative status indicators.
- Marketing-style banners in the chat stream.
- Overly colorful message decorations.

---

## 3. WeChat (微信)

### Layout
- Desktop: two-column. Left conversation list, right chat area. No third panel by default.
- Mobile: single-column, conversation list → chat view.
- Top bar: contact/group name, no extra actions (minimalist).

### Chat stream
- Green bubbles for self, white/gray for others. No avatar on self-messages.
- Extremely compact on mobile: 8-10 messages visible.
- Timestamps only appear every ~5 minutes or on the first message of a session.
- No read receipts (unlike DingTalk).
- Image, video, file, voice message, location — all first-class message types.
- Voice messages: tap to play, hold to record. Very natural.

### Composer
- Minimal: text input + emoji + "+" for more.
- Voice message toggle (hold to talk).
- No rich text toolbar by default — simplicity first.

### What makes it feel real
- Personal, intimate feel. Not "enterprise software."
- Green bubble color is iconic and warm.
- Message density is high. No wasted space.
- System messages ("你已添加了xxx，现在可以开始聊天了") are friendly, not robotic.

### What would make it feel fake
- Card-based message layout.
- Gradient or shadow-heavy design.
- Enterprise-dashboard widgets mixed into the chat.

---

## 4. Slack

### Layout
- Three-column: workspace sidebar (far left, very narrow) → channel list → chat stream.
- Optional right panel for threads, search results, or app info.
- Dark sidebar, light main area. High contrast between navigation and content.

### Chat stream
- Message density similar to Feishu. Avatars on the left.
- Threads are a core feature: each message can spawn a side thread.
- Rich block formatting: code blocks, quotes, lists, all rendered inline.
- Emoji reactions below messages — 1-2 per message max in real usage.
- Bot messages are clearly marked with a "BOT" badge next to the name.
- Integration messages (GitHub, Jira, etc.) have a distinct attachment style.

### Composer
- Rich text with markdown support. `/` slash commands for actions.
- Formatting toolbar on hover.
- Send with Enter, newline with Shift+Enter.

### What makes it feel real
- Thread-based conversation model — prevents channel noise.
- Integration cards feel like native content, not ads.
- Typography is crisp: Inter or similar sans-serif, good line-height.
- Channel purpose/topic shown at the top — sets context.

### What would make it feel fake
- Over-stylized bot messages that try to look like human messages.
- Excessive emoji reactions (5+ per message).
- Missing thread UI when messages reference each other.

---

## 5. Linear

### Layout
- Two-column: left project/issue list, right issue detail.
- Chat-like "activity" feed inside each issue.
- Top bar: breadcrumb navigation, not a conversation header.

### Chat stream (activity feed)
- Compact timeline of comments, status changes, and system events.
- Comments are plain text with markdown. No bubbles, just left-aligned blocks.
- System events ("Changed status to In Progress") are small, gray, inline.
- No avatars in the activity feed itself — name only.

### What makes it feel real
- Activity feed is functional, not decorative.
- Comments are work-focused. No "chat" fluff.
- Status changes and assignments are part of the feed, not separate.

### What makes it feel fake
- Bubble-style chat in a project management tool.
- Animated transitions between status changes.

### Relevant for office chat
- The "activity feed" model is closer to an investigation timeline than a social chat.
- Consider mixing system events (source connected, evidence admitted) with persona messages.

---

## 6. Discord

### Layout
- Three-column: server list (far left, icon-only) → channel list → chat stream.
- Optional member list on the right.
- Dark theme by default. Very colorful server icons.

### Chat stream
- Compact, like Slack. Avatars on the left.
- Rich embeds: link previews, image previews, file attachments.
- Role colors: usernames are colored by role.
- Voice channel integration: see who's in voice while chatting in text.
- "@everyone" and "@role" pings.

### Composer
- Rich text with markdown. `/` commands. Sticker/GIF picker.
- Upload by drag-and-drop or paste.

### What makes it feel real
- Role-based name colors add hierarchy without extra UI.
- Voice presence indicator makes it feel alive.
- Compact message density — optimized for fast reading.

### What makes it feel fake
- Corporate over-styling of Discord's gamer aesthetic.
- Using Discord's exact color palette for a business product.

### Relevant for office chat
- Role-colored names are a good pattern for the persona office chat.
- The "member list" on the right could be adapted to show active personas.

---

## 7. iMessage (Apple Messages)

### Layout
- Two-column on macOS: conversation list + chat.
- Single-column on iOS.
- Top bar: contact name/photo + FaceTime/audio call buttons.

### Chat stream
- Blue bubbles (iMessage) vs green bubbles (SMS). Color signals protocol, not sender.
- Extremely clean typography: SF Pro, tight line-height.
- Message tails (the little point on the bubble) are subtle but important.
- Tapback (double-tap to react) is minimalist: small icons above the bubble.
- "Delivered" / "Read" below the last message.
- Typing indicator: animated "..." in a gray bubble.
- Images and links have rich previews inline.

### Composer
- Minimal: text input + camera + apps (iMessage apps).
- Auto-expanding input. Send button appears when text is entered.

### What makes it feel real
- Bubble tails. Small detail, huge impact on perceived authenticity.
- Delivered/Read status is unobtrusive but present.
- Typography and spacing feel native to the OS, not web-generic.
- Message grouping: consecutive messages from the same sender are visually grouped.

### What makes it feel fake
- Missing bubble tails.
- All messages from the same sender showing full avatar + name on every message.
- Over-stylized bubbles (gradients, heavy shadows, large border-radius).

### Relevant for office chat
- Bubble grouping: consecutive messages from the same persona should be visually grouped.
- Read/delivered status can be repurposed as "evidence verified" / "source connected" status.
- iOS-style input field with send button that appears on text entry.

---

## 8. Cross-Product Summary

### What signals "real collaboration software"

| Signal | Example |
|--------|---------|
| Compact message density | 5-8 messages visible, not 2-3 |
| Relative timestamps | "2分钟前" not "2026-06-27T14:03:00" |
| Avatar + name per message | But grouped for consecutive messages |
| Bubble tails or equivalent | Visual continuity between sender and message |
| Unread indicators | Small red dot, not a numbered badge |
| System messages | Centered, gray, smaller — for join/leave/pin/status |
| Typing indicator | Animated dots, not a text label |
| Read/delivered status | Subtle, below last message or per message |
| @mention highlighting | Blue or accent color background |
| Inline media | Images, files, links rendered in-stream |

### What signals "generic AI dashboard"

| Anti-pattern | Why it feels fake |
|--------------|-------------------|
| Card-based messages | Real chat apps don't use Material Design cards |
| Gradient backgrounds | No major chat app uses gradients on message bubbles |
| Box shadows on messages | Creates a "widget" feel, not a "message" feel |
| Large padding (20px+) between messages | Real chat is dense |
| No avatar grouping | Every message showing full sender info breaks flow |
| Decorative status indicators | "Online" shown as a text badge instead of a green dot |
| ISO timestamps | Real chat apps use relative time |
| Dashboard widgets in chat stream | Breaks the conversation metaphor |
| Excessive emoji reactions | 5+ reactions per message is not how people actually use chat |
| Marketing-page layout | Hero sections, feature cards, CTAs in a chat UI |

### Desktop vs Mobile

- **Desktop**: 2-3 columns. Left sidebar always visible. Right panel optional.
- **Mobile**: Single column. Navigation via back button or bottom tabs. Composer fixed to bottom.
- **Critical mobile rule**: No horizontal overflow. Message bubbles must wrap. Evidence panel must collapse into a bottom sheet or full-screen overlay.

---

## 9. Application to Persona Office Chat

### What to borrow

| Feature | From | Why |
|---------|------|-----|
| Three-column layout | Feishu, Slack | Fits the channel+stream+evidence model |
| Role-colored names | Discord | Personas are roles — color distinguishes them |
| Compact message density | WeChat, Discord | Investigation messages should be scannable |
| Bubble tails | iMessage | Makes messages feel like real chat |
| System messages for status | Slack, Linear | Source connected, evidence admitted, confidence changed |
| Relative timestamps | All | Real chat feel |
| Right panel for evidence | Feishu, Slack | Evidence detail belongs in a side panel |
| Thread support | Slack | Private sentinel-GM chat, deep-dive discussions |
| Mobile collapsed layout | WeChat | Single column, evidence as bottom sheet |

### What to avoid

- Material Design card shadows.
- Gradient backgrounds on any message.
- Dashboard widgets in the chat stream.
- Marketing-style CTAs or hero sections.
- Yellow/earthy/warm color palettes (not suitable for a business investigation product).
- Excessive padding that kills message density.
- ISO timestamps (use relative time).
- Generic AI assistant voice in any message text.
