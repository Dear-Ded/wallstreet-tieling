# Telegram 群组/频道成员交叉可行性（2026-10-21）— 结论：成员列表走不通，已落关联 handle 信号

## 实测
- `t.me/s/<handle>` 公开预览：只有频道标题/简介/订阅数/~20 条帖子，
  **无成员列表、无管理员列表**（已在 telegram_channel_adapter docstring 记录）。
- `tgstat.com/channel/@durov`（200，服务端渲染，robots 允许）：
  全页搜索 admin/moderator/creator → 0 命中；"member"/"owner"/"team" 的命中
  全部来自内嵌的频道帖子正文（如 "members of the Telegram team won medals"），
  **不是成员/管理员信息面**。无公开成员列表、管理员名单。
- tgstat 全部搜索入口此前已证实登录墙（见 telegram-tgstat-reverse-20261021.md），
  未尝试登录（红线）。

## 结论
成员列表这条路如实判死：Telegram 不公开成员，tgstat 公开面也没有。
不丢人，证据在此。

## 已落地的交叉信号（本次补齐）
- tgstat 频道页 `<h1>` 下的 `@xxx` 按钮 = 频道主的其他公开频道
  （实测 @durov → feed, lean, paul, rove, snow）。这是"同人多频道归一"的强信号。
- `TelegramChannelLookup.enrich_with_tgstat(handle)`（opt-in, enrich=True，
  独立 5s 限速 + 独立审计）早已存在；本次补上 `_extract` 接线：
  `related_handles` → `username_profile` 实体（context 标注 owner_handle、
  subscribers_exact、tgstat_related_handle），供 `_resolve_person_identity`
  与图谱 username 匹配消费。测试见 test_entity_extract_telegram.py。
