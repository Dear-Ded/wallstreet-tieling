# Data Source Research — wallstreet-tieling Deep Due Diligence

Date: 2026-06-28
Target: docs/data_source_research_20260628.md

## Current System Sources

- public_web_search (DuckDuckGo/Bing)
- sec_edgar_public_api (US SEC companyfacts)
- gleif_lei_public_api (Global LEI entity lookup)
- wikidata_public_entity_graph (SPARQL)
- ofac_consolidated_sanctions_xml (not yet activated)
- un_sc_consolidated_sanctions_xml (not yet activated)
- qyyjt_api (China enterprise risk, needs credentials)
- telegram_bot_public_service

---

## 1. Money Lane

### 1.1 SEC EDGAR Full-Text (10-K, 10-Q, 8-K)
- Fields: revenue, net_income, assets, liabilities, cash_flow, debt, risk_factors, legal_proceedings
- Access: HTTPS + XBRL/HTML parser, public, no key
- Lane: money (fact), legal (lead)
- MVP: Extend existing sec_edgar to download filing text, parse financial tables via section regex
- Cost: LOW (within existing framework)

### 1.2 中国 企业信用信息公示系统 (GSXT)
- Fields: 注册资本, 实缴资本, 股东出资, 股权变更, 动产抵押, 行政处罚, 经营异常
- Access: gsxt.gov.cn HTTP GET, public, CAPTCHA gate
- Lane: money (fact), people (fact), legal (fact)
- MVP: adapters/gsxt_tool.py — headless browser + OCR for CAPTCHA
- Cost: MEDIUM (CAPTCHA handling)

### 1.3 ChinaBond / Shanghai Clearing House
- Fields: bond_issuer, issue_amount, maturity, coupon, credit_rating, default_history
- Access: chinabond.com.cn public query, free
- Lane: money (fact), legal (lead)
- MVP: adapters/chinabond_tool.py — HTTP GET + HTML table parser
- Cost: LOW

### 1.4 OpenCorporates API
- Fields: company_financials, filing_history, officers, subsidiaries, industry_codes
- Access: api.opencorporates.com REST, free tier 500 req/month, API key
- Lane: money (fact), people (fact), registry (fact)
- MVP: adapters/opencorp_tool.py — REST client with API key config
- Cost: LOW

### 1.5 FRED (Federal Reserve Economic Data)
- Fields: interest_rates, GDP, inflation, employment, industry_production
- Access: api.stlouisfed.org/fred REST, free API key
- Lane: money (fact — macro context only)
- MVP: adapters/fred_tool.py — REST client for key indicators
- Cost: LOW

---

## 2. Goods Lane

### 2.1 USITC HTS Trade Data
- Fields: product_category, hts_code, tariff_rate, trade_volume, country, importer
- Access: dataweb.usitc.gov API, free registration
- Lane: goods (fact), money (lead)
- MVP: adapters/usitc_tool.py
- Cost: LOW

### 2.2 Panjiva Shipment Records (Public Snippets)
- Fields: consignee, shipper, product_desc, hs_code, shipment_date, ports
- Access: site:panjiva.com via public_web_search, public snippets only
- Lane: goods (lead), relationship (lead)
- MVP: site-directed search template, no new adapter needed
- Cost: ZERO (config only)

### 2.3 中国 采购与招标 (Procurement & Bidding)
- Fields: project_name, procuring_entity, bidding_company, bid_amount
- Access: chinabidding.com.cn, ccgp.gov.cn, public
- Lane: goods (fact for awarded), relationship (lead)
- MVP: site:chinabidding.com.cn via public_web_search
- Cost: ZERO (config only)

### 2.4 CNIPA Patent/Trademark Search
- Fields: patent_number, applicant, inventor, filing_date, ipc_class, trademark_class
- Access: pss-system.cponline.cnipa.gov.cn, public, CAPTCHA
- Lane: goods (fact — IP assets), people (lead — inventors)
- MVP: adapters/cnipa_tool.py
- Cost: MEDIUM (CAPTCHA)

---

## 3. People Lane

### 3.1 SEC EDGAR Insider Transactions (Form 3,4,5)
- Fields: reporting_person, relationship, transaction_date, security, shares, price
- Access: SEC EDGAR ownership filings, public
- Lane: people (fact), money (lead)
- MVP: Extend sec_edgar to query /cgi-bin/browse-edgar?action=getowner
- Cost: LOW

### 3.2 OFAC/UN/EU Sanctions Lists
- Fields: sanctioned_name, aliases, DOB, nationality, passport, address, sanction_program
- Access: OFAC SDN XML, UN XML, EU CSV — all public
- Lane: people (fact), legal (fact)
- MVP: Activate existing official source connectors (already listed)
- Cost: ZERO (activate existing)

### 3.3 中国 失信被执行人/限制高消费
- Fields: subject_name, case_number, court, filing_date, amount, status
- Access: zxgk.court.gov.cn, public, CAPTCHA
- Lane: people (fact), legal (fact)
- MVP: site:zxgk.court.gov.cn via public_web_search
- Cost: ZERO (config only)

### 3.4 Open Ownership Register
- Fields: beneficial_owner_name, ownership_pct, ownership_type, declared_date, PEP status
- Access: register.openownership.org REST, free registration
- Lane: people (fact), relationship (fact)
- MVP: adapters/openownership_tool.py
- Cost: LOW

---

## 4. Legal Lane

### 4.1 中国 裁判文书网 (China Judgments)
- Fields: case_number, court, judgment_date, type, plaintiff, defendant, result
- Access: wenshu.court.gov.cn, public, CAPTCHA
- Lane: legal (fact), people (lead)
- MVP: site:wenshu.court.gov.cn via public_web_search
- Cost: ZERO (config only)

### 4.2 中国 行政处罚 (Administrative Penalties)
- Fields: recipient, authority, date, type, amount, violation_desc
- Access: creditchina.gov.cn, public
- Lane: legal (fact), money (lead)
- MVP: site:creditchina.gov.cn via public_web_search
- Cost: ZERO (config only)

### 4.3 US PACER (Federal Court Records)
- Fields: case_number, court, filing_date, parties, case_type, docket
- Access: pacer.uscourts.gov API, public, per-page fee ($0.10)
- Lane: legal (fact), people (lead)
- MVP: adapters/pacer_tool.py — pacer-tools library
- Cost: MEDIUM (fee-based)

### 4.4 EU EUR-Lex
- Fields: directive, celex_number, transposition_country, compliance_status
- Access: eur-lex.europa.eu REST + SPARQL, free
- Lane: legal (fact)
- MVP: adapters/eurlex_tool.py
- Cost: LOW

---

## 5. News/Media Lane

### 5.1 Google/Bing News RSS
- Fields: headline, date, source, snippet, url
- Access: RSS feeds or Bing News API (free tier 1000/mo)
- Lane: news (lead), legal (lead), goods (lead)
- MVP: Add source=news mode to public_web_search_tool
- Cost: LOW

### 5.2 QYYJT News/Opinion (Already Integrated)
- Already available via qyyjt_adapter.py
- Requires QYYJT credentials

### 5.3 Wayback Machine CDX API
- Fields: historical_snapshots, url, timestamp, status, digest
- Access: web.archive.org/cdx/search/cdx, free
- Lane: people (lead), goods (lead), legal (lead)
- MVP: adapters/wayback_tool.py
- Cost: LOW

---

## 6. Registry/Identity Lane

### 6.1 GLEIF LEI (Already Listed — activate)
- Fields: lei, legal_name, address, status, parent_lei
- Access: api.gleif.org v2, free
- Lane: registry (fact), relationship (fact)
- Cost: ZERO

### 6.2 Wikidata (Already Listed — activate)
- Fields: labels, descriptions, industry, HQ, parent, founded, employees, revenue
- Access: query.wikidata.org SPARQL, free
- Lane: registry (lead), goods (lead), people (lead)
- Cost: ZERO

### 6.3 中国 USCC Database
- Fields: uscc, entity_name, legal_rep, address, established, business_scope
- Access: codata.org.cn, public, CAPTCHA
- Lane: registry (fact)
- MVP: adapters/uscc_tool.py
- Cost: MEDIUM

---

## 7. Relationship Lane

### 7.1 GLEIF LEI Relationship Endpoint
- Fields: direct_parent_lei, ultimate_parent_lei, relationship_type, dates
- Access: GLEIF API v2 relationship endpoint, free
- Lane: relationship (fact)
- Cost: ZERO (extend existing)

### 7.2 QYYJT Group Network Edge (Partially Integrated)
- Fields: investing_entity, target_entity, ratio, amount, position
- Access: QYYJT API, authorized
- Lane: relationship (fact), people (lead)
- Cost: ZERO (activate module)

### 7.3 Open Ownership (See 3.4 above)

---

## 8. User Upload / Import

### 8.1 CSV/XLSX/PDF Upload
- Fields: user-defined columns mapped to evidence fields
- Access: File upload API or local path
- Lane: all lanes (user-attested)
- MVP: adapters/user_upload_tool.py — CSV/XLSX parser with column mapping
- Cost: MEDIUM

---

## 9. Public Web Site-Directed Search Enhancement
- Add site-specific query templates to public_web_search_tool:
  - site:gsxt.gov.cn (enterprise registry)
  - site:zxgk.court.gov.cn (enforcement/dishonesty)
  - site:creditchina.gov.cn (administrative penalties)
  - site:chinabidding.com.cn (procurement/bidding)
  - site:panjiva.com (trade/shipments)
  - site:wenshu.court.gov.cn (court judgments)
- Cost: ZERO (configuration change, no new adapter needed)

---

## 10. GitHub Code Repository Intelligence
- Fields: repo_activity, tech_stack, contributors, dependencies, org_membership
- Access: api.github.com REST, free tier 60/hr (5000/hr with token)
- Lane: goods (lead), people (lead)
- MVP: adapters/github_intel_tool.py
- Cost: LOW

---

## Priority Ranking — 建议先接入的 5 个

| Rank | Source | Dev Cost | Report Impact | Testability | Reason |
|------|--------|----------|---------------|-------------|--------|
| 1 | SEC EDGAR Full-Text | LOW | HIGH | HIGH | Already in framework; full filings add risk_factors, debt, legal_proceedings |
| 2 | OFAC/UN Sanctions Activation | ZERO | HIGH | HIGH | Already listed in DEFAULT_OFFICIAL_SOURCE_NAMES; just needs connector activation |
| 3 | GLEIF LEI Relationship | LOW | HIGH | HIGH | Free API; parent/subsidiary edges = fact-level relationship_graph |
| 4 | Site-Directed Search Templates | ZERO | MEDIUM | HIGH | Config change only; covers 6 Chinese legal/registry/procurement sites |
| 5 | 中国 Court/Enforcement site-search | ZERO | HIGH | MEDIUM | Direct zxgk+wenshu search via existing public_web_search; fact-grade legal records for Chinese entities |
