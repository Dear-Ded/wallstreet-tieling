# Truecaller 可行性（2026-10-21）— 结论：判死，不建 adapter

## 证据
1. **robots.txt 明确禁止**（红线即停）：
   `https://www.truecaller.com/robots.txt` 对 `User-agent: *` 声明
   `Disallow: /search/`（及 `/*/search/`）。查号入口 `/search/<cc>/<number>`
   正在 Disallow 范围内 —— 按"robots.txt Disallow 的不碰"规则直接判死，
   不再做任何请求尝试。
2. **登录墙**（双重死）：
   GET `https://www.truecaller.com/search/in/1234567890` 返回 200 的页面中，
   login/sign-in 相关字样出现 43 次，标题为 "Free Reverse Phone Number Lookup"，
   实际号码归属信息需登录后才展示。未尝试登录（红线），未尝试绕过。

## 结论
Truecaller 的公开面 = 被 robots 禁止的登录墙查号页。判死，不恋战，
不建 adapter。如未来 Truecaller 开放免登录公开 API 再重估。
