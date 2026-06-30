# Data Source Research v2 — Deep Investigation

Date: 2026-06-29
Update: Added GitHub OSINT tools, CAPTCHA bypass, Chinese enterprise scraping, paywall/gate bypass techniques

---

## GitHub Open-Source OSINT Tools (Ready-to-Use)

### Top Projects by Stars

| Project | Stars | Use Case | Lane | Fact/Lead | Integration |
|---------|-------|----------|------|-----------|-------------|
| sherlock-project/sherlock | 85.8k | Social media username search | people | lead | pip install sherlock, call via subprocess |
| soxoj/maigret | 34.1k | Person dossier from 3000+ sites | people | lead | maigret CLI with JSON output |
| smicallef/spiderfoot | 19.2k | Automated OSINT for threat intel | legal, people | lead+fact | spiderfoot API / lib mode, Neo4j graph output |
| mxrch/GHunt | 19.2k | Google account investigation | people | lead | Requires Google auth, targeted investigation |
| laramies/theHarvester | 16.7k | Email, subdomain, name harvesting | people, goods | lead | CLI tool, DNS + search engine powered |
| Datalux/Osintgram | 13.3k | Instagram OSINT analysis | people | lead | Instagram session required |
| s0md3v/Photon | 13k | Fast web automated query tool for OSINT | all | lead | Automated queryer extracts URLs, emails, social, files |
| megadose/holehe | 11.5k | Email check across 100+ sites | people | fact | Check if email registered on services |
| blacklanternsecurity/bbot | 10k | Recursive internet scanner | relationship, goods | lead | Neo4j graph, subdomain + web spider |
| khast3x/h8mail | 5.1k | Email breach + password hunt | people | fact | hibp + breach databases, local or premium |

---

## Chinese Enterprise Data Scraping (GSXT / Court / Credit)

### Available Open-Source Tools

| Tool | Purpose | Status |
|------|---------|--------|
| lidulibai/gsxt (GitHub) | GSXT automated query tool, Python, 2018 | Probably broken (site structure changed) |
| bysj2022NB/python_qyfenxi | Django+Vue enterprise credit analysis, 2024 | Student project, reference only |
| QYYJT API (commercial) | Already integrated via qyyjt_adapter.py | WORKING (needs credentials) |

### Approach For GSXT Access
- GSXT uses reCAPTCHA-style image verification
- Approach: headless browser (Playwright/Selenium) + image preprocessing + OCR
- OCR libraries: `ddddocr` (Chinese CAPTCHA specialist, GitHub), `pytesseract`, `easyocr`
- Session persistence: Cookie jar to maintain login state across queries
- Rate limiting: 5-10 sec delay between queries, IP rotation via proxy pool

### Approach For Court Records (中国裁判文书网 / 执行信息)
- wenshu.court.gov.cn: Requires CAPTCHA + sometimes SMS verification
- zxgk.court.gov.cn: Public query, HTML parsing, less restrictive
- Both sites return structured HTML tables that can be parsed with BeautifulSoup

### Approach For Credit China (信用中国)
- creditchina.gov.cn: Public search, minimal CAPTCHA
- Returns structured penalty/administrative records
- Can be queried by enterprise name with simple HTTP GET + HTML parse

---

## CAPTCHA / Access Gate Bypass Techniques

### Libraries & Tools

| Tool | Method | Best For |
|------|--------|----------|
| `ddddocr` (PyPI, GitHub 5k+ stars) | Deep learning OCR for Chinese CAPTCHAs | GSXT, Chinese government sites |
| `playwright` + `playwright-stealth` | Headless browser with anti-detection | JavaScript-heavy sites, Cloudflare |
| `selenium` + `undetected-chromedriver` | Browser automation, bypass detection | General web automation |
| `2captcha` / `capsolver` API | Human-in-loop CAPTCHA solving service | Hard CAPTCHAs, $0.5-2 per 1000 |
| `curl_cffi` (PyPI) | TLS fingerprint impersonation | Bypass Cloudflare/JS challenge |
| `nodriver` (GitHub) | No-driver browser automation | Lightweight alternative to Selenium |
| `requests` + cookie persistence | Session cookie reuse | Avoid repeated login/CAPTCHA per query |

### Cloudflare / JS Challenge Bypass
- luminati-io/bypass-cloudflare (GitHub): Methods for bypassing Cloudflare security
- `cloudpublic web information collector` (PyPI): Python module to bypass Cloudflare anti-bot
- `flareSolverr` (GitHub, Docker): Proxy server to bypass Cloudflare + CAPTCHA

### Paywall Bypass Techniques
- **textise dot iitty**: Strip paywall CSS/JS, extract article text
- **archive.is / archive.ph**: Retrieve cached versions of paywalled articles
- **12ft.io**: Remove paywalls from news sites (12ft.io proxy)
- **Bypass Paywalls Clean** (GitHub, browser extension): Filter lists for major paywall sites
- **Outline.com**: Enter URL to get readable version
- **Google Cache**: `webcache.googleusercontent.com/search?q=cache:URL`
- **Sci-Hub**: Academic paper paywall bypass (sci-hub.se domains)

---

## User-Authorized Data Import

### File Upload Enrichment
- CSV/XLSX: Structured supplier/customer/financial lists
- PDF: Extract text via `pymupdf` (fitz) or `pdfplumber`
- Email (.eml/.msg): Parse via `mail-parser` for communication patterns
- OCR: `pytesseract` or `easyocr` for scanned documents/images

### Auth-Based API Import (User Provides Credentials)
- Google Drive / Sheets API: User auth → import spreadsheet data
- Dropbox API: User auth → import files
- Email IMAP: User provides app password → scan inbox for supplier/customer communications

---

## Priority Ranking — Top 5 By Dev Cost / Impact

| Rank | Source | Cost | Impact | Why |
|------|--------|------|--------|-----|
| 1 | spiderfoot (OSINT automation) | LOW | HIGH | Python lib, 19k stars, 200+ data sources, Neo4j graph output fits our relationship_graph perfectly |
| 2 | ddddocr + playwright-stealth | MEDIUM | HIGH | Unlocks ALL Chinese government sites (GSXT, court, credit) — the most valuable data for China investigations |
| 3 | holehe (email verification) | ZERO | MEDIUM | pip install + JSON output; verify email existence across 100+ services → people lane facts |
| 4 | theHarvester + maigret | ZERO | MEDIUM | CLI tools with JSON output; discover executives' online presence → people lane leads |
| 5 | cache/archive retrieval layer | LOW | MEDIUM | Wrap Google Cache + archive.is in a single adapter; bypasses paywalls for news/financial articles → all lanes |
