# WorkBuddy Office Chat UI Review - 2026-06-26

Reviewer: Codex
Scope: dirty `index.html` office-chat UI changes.

## Verdict

Rejected for product direction mismatch.

The current surface renders and has no obvious horizontal overflow in the
checked viewports, but it is still a report-tab widget with static demo
messages. It does not meet the requested "DingTalk / Feishu / WeChat-like
real-time office chat" product target.

## Checked

- Local URL: `http://127.0.0.1:8787/index.html#office`
- Desktop screenshot: `office-workbuddy-desktop.png`
- Mobile screenshot: `office-workbuddy-mobile.png`
- Desktop DOM:
  - active view: `office`
  - `.office-msg` count: 13
  - horizontal overflow: 0
  - console/page errors observed through Playwright MCP: none
- Mobile DOM:
  - active view: `office`
  - horizontal overflow: 0
  - office tab remains embedded mid-page, not a mobile chat app surface

## Blocking Issues

1. It is not a real chat workbench.
   - No composer/input area.
   - No send action.
   - No conversation/channel list.
   - No unread/online/team presence model.
   - No pinned/case context column comparable to Feishu/DingTalk work surfaces.

2. It is still a static report tab.
   - The office is buried inside the existing workbench page.
   - It does not become the primary app shell when the office tab is active.
   - Mobile renders the office area in the middle of the long page rather than
     feeling like a mobile messaging app.

3. Persona integration is shallow.
   - Role names appear, but role behavior is not expressed through interaction.
   - The general manager and sentinel channel exists as a tab, but it does not
     feel like a private conversation surface.
   - Messages are static demo content rather than generated from the packet as
     an operational conversation.

4. Evidence badges are noisy.
   - Some evidence labels duplicate as both badges and refs.
   - The badge system consumes space without creating a readable message rhythm.

5. Visual direction is not close enough to DingTalk/Feishu/WeChat.
   - Missing app-level chat shell.
   - Missing left workspace/channel rail on desktop.
   - Missing sticky chat header and bottom composer.
   - Missing mobile-first full-screen chat behavior.

## Required Rework Direction

WorkBuddy must redesign the office chat as a dedicated chat product surface:

Desktop:

- left rail: office/workspace identity, channel list, unread counts;
- center pane: active conversation with sticky header, scrollable messages,
  bottom composer, evidence attach/actions;
- right pane: active role roster, investigation context, sentinel status,
  evidence filters;
- private channel must feel visually distinct from group channel.

Mobile:

- one-screen chat app behavior;
- top nav/header;
- channel drawer or segmented switch;
- full-height message list;
- sticky bottom composer;
- no hidden filter row overflow as the main navigation pattern.

Must include:

- group channel;
- `qian-shou-zheng` / `an-shao` private channel;
- role avatars/presence;
- unread/status badges;
- composer/input mock interaction;
- evidence/profile/report attach badges;
- empty/loading/error states;
- desktop and mobile QA notes.

## External References To Study

- Mattermost: https://github.com/mattermost/mattermost
- Rocket.Chat: https://github.com/RocketChat/Rocket.Chat
- assistant-ui: https://github.com/assistant-ui/assistant-ui
- NextChat: https://github.com/ChatGPTNextWeb/NextChat

Borrow layout and interaction patterns only. Do not copy unlicensed assets.

## Handoff Instruction

Do not patch the current tab with small cosmetic edits. Replace the office-chat
surface with a real messaging app shell. Keep all changes inside WorkBuddy's
allowed files and return with:

```text
HANDOFF_TO_CODEX: office_chat_ui_review
COMMIT:
FILES:
REFERENCE STUDY:
PRODUCT SHELL:
DESKTOP QA:
MOBILE QA:
CONSOLE ERRORS:
OVERFLOW CHECK:
KNOWN LIMITATIONS:
DATA CONTRACT ASSUMPTIONS:
LICENSE/ASSET CONFIRMATION:
```

