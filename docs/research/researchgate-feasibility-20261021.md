# ResearchGate 可行性调查 — 判死 (2026-10-21)

调查对象：ResearchGate 学者主页（论文、单位、合作者）。

## 实测

1. **robots.txt 不挡路**：`GET https://www.researchgate.net/robots.txt` → `User-agent: * / Allow: /`
   （仅屏蔽 /cdn-cgi/、/connector/ 等私有端点）。抓取政策层面可爬。

2. **登录墙一票否决**（单次实测）：
   `GET https://www.researchgate.net/profile/Geoffrey-Hinton` →
   HTTP 200 但 `final_url=https://www.researchgate.net/directory/profiles`，
   即 301/JS 跳转到**登录/目录页**，响应体中 login 标记遍布，学者主页内容对匿名访客不可见。
   ResearchGate 自 2020 年起对匿名访客全面启用登录墙（profile、publication、co-authors 均需登录）。

## 结论：判死

robots 允许但**内容在登录墙之后**。红线："不绕登录/付费墙"，不尝试登录、不伪造会话。
学术线统一走 Semantic Scholar（公开 API、免 key，见 `semanticscholar-feasibility-20261021.md`）。
