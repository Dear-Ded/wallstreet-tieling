# 快手用户画像：服务端 autonomous 路径判死（2026-10-21）

## 结论

快手用户主页 **无法**通过纯服务端 HTTP 拿到用户资料（判死）。按用户名搜
用户、按 userId 拉用户主页这两条路都走不通。唯一可行路线是
browser-assisted（已有 `public_kuaishou_video_lookup` 经分享链接拿视频页
author card 的路线保持不变）。

## 实测证据（境外出口，US datacenter）

1. `GET https://www.kuaishou.com/profile/3`（UA 为桌面 Chrome）→ HTTP 200，
   329,660 字节，但 **全是 SPA 通用壳**：
   - `<title>` 通用 "快手"，`og:url` 为 `https://www.kuaishou.com/profile/`
     （无 id），`og:description` 为 App 通用介绍；
   - 无 `__INITIAL__`、无 `initialState`，25 个 `<script>` 全是框架代码；
   - `"userName"` 字符串出现 1 次——经核查在 JS 样板上下文中，非用户数据；
     `"userId"` 出现 1 次同样为样板；无 `photoId`；
   - 即：服务端 HTML 不含任何用户资料，用户数据靠 JS 二次渲染。
2. robots.txt（`www.kuaishou.com/robots.txt`）：仅列 Baiduspider /
   Googlebot / Sogou 等允许规则，无针对 profile 路径的 Disallow——robots
   不是拦路虎，拦路的是 JS 渲染。
3. `public_kuaishou_video_lookup` 现状：`query_by_share_url()` 解析视频分享页
   HTML 可拿到 `userName` / `userId` / counts / location（POI）——这是目前
   快手侧唯一的服务端用户线索来源（author card 级别，非完整主页）。

## 判死的路（不再投入）

- 按用户名服务端搜索：快手 Web 搜索需要 JS 渲染 + 签名，纯服务端不稳定
  （与 douyin_adapter 的搜索签名链问题同类），且用户主页本身 JS 墙。
- 用 HTML 解析用户主页：壳页面无数据，判死。
- 任何需要登录态的接口（粉丝列表、私信等）：红线，不碰。

## 可走的路（现状已覆盖，无需新造）

- 用户给一条该用户的**视频分享链接** → `query_by_share_url()` → author
  card（昵称/快手号/粉丝量级/定位）→ entity_association 生成 person 实体。
- 用户名 → 浏览器辅助：与 douyin/xiaohongshu 同一 browser-assisted 骨架，
  操作员在浏览器找到用户后复制分享链接回来。本轮不新增连接器，避免重复造。
