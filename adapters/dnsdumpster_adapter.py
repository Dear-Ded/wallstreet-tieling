"""DNSdumpster DNS 侦察适配器。数据边界: fully_public

DNSdumpster (dnsdumpster.com) is a free domain research tool that discovers
hosts related to a domain from the attacker's perspective. For due diligence
it exposes the DNS-visible attack surface and business-function signals:

- Subdomains (A records): hr.example.com / api.example.com / vpn.example.com
  reveal business units, tech stack entry points and sometimes staging/dev
  hosts that leak internal naming conventions.
- MX records: the mail infrastructure (self-hosted vs Google Workspace /
  Microsoft 365 / Tencent Exmail) — a company-size and outsourcing signal.
- NS records: DNS hosting (Cloudflare / Alibaba Cloud DNS / self-hosted).
- TXT records: SPF/DMARC records, domain-verification tokens (google-site-
  verification, zoom, docusign, ...) that corroborate which SaaS vendors
  the company actually uses.

Technical notes (verified 2026-10-21):
- The site moved to an HTMX form: GET / for the session, then POST
  https://dnsdumpster.com/htmld/ with form field target=<domain>
  (application/x-www-form-urlencoded), Referer/Origin headers set.
- No CSRF token, no login, no API key. Reserved domains (e.g. example.com)
  are rejected with an "Invalid domain" error page.
- Free tier: results capped at 50 hosts per domain ("Free users are limited
  to 50 results for a single domain").
- A-record table has id="a_rec_table": Host | IP (+reverse DNS) | ASN
  (number + prefix) | ASN Name | Open Services | RevIP count.
  MX/NS tables follow their section headings with the same column layout
  (MX first column is "priority host").
  TXT values appear as HTML-entity-quoted strings (&#34;...&#34;).
- robots.txt note: the site disallows /htmld/ for User-agent: *. The base
  robots checker validates the site root (allowed). The adapter is
  default-off, rate-limited (10s), and sends a browser-like UA; operators
  should keep usage modest and can switch the source off entirely.

Association value: subdomains/MX/NS/TXT are leads — an "hr." host suggests
an HR system exists; SPF "include:" chains name the mail providers; TXT
verification tokens name SaaS vendors. None of this proves ownership or
current use; it scopes where to look next (crt.sh, FOFA, analytics pivot).
"""
from adapters.safe_research_adapter import SafeResearchAdapter
from typing import Any
import html as _html
import re
import urllib.parse


class DNSdumpsterLookup(SafeResearchAdapter):
    """DNSdumpster 子域名/DNS 记录检索：按域名查 A/MX/NS/TXT。"""

    source_domain = "dnsdumpster.com"
    source_type = "dns_recon_public"
    data_boundary = "fully_public"
    requires_credentials = False
    requires_interaction = False
    min_request_interval = 10.0

    _ENDPOINT = "https://dnsdumpster.com/htmld/"
    _REQUEST_TIMEOUT_S = 60
    _FREE_TIER_LIMIT = 50

    # Subdomain labels that hint at business functions (关联业务信号).
    _INTERESTING_LABELS = {
        "mail", "mx", "smtp", "owa", "exchange", "webmail",
        "vpn", "remote", "citrix", "rdp",
        "hr", "erp", "crm", "oa", "jira", "confluence", "git",
        "api", "dev", "staging", "test", "beta", "demo",
        "admin", "portal", "dashboard", "console",
        "ftp", "sftp", "backup", "db", "sql",
        "pay", "billing", "shop", "store",
        "cdn", "static", "img", "assets",
    }

    _last_domain: str | None = None

    # ------------------------------------------------------------------
    # Transport
    # ------------------------------------------------------------------

    def _build_url(self, keyword: str, **params) -> str:
        domain = self._normalize_domain(keyword)
        self._last_domain = domain
        return self._ENDPOINT

    def _build_headers(self) -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Referer": "https://dnsdumpster.com/",
            "Origin": "https://dnsdumpster.com",
            "HX-Request": "true",
        }

    def _execute_query(self, url: str, headers: dict) -> tuple[int, Any, str]:
        if self._execute_query_override is not None:
            return self._execute_query_override(url, headers)
        domain = getattr(self, "_last_domain", "") or ""
        if not domain:
            return (0, None, "empty_domain_after_normalization")
        try:
            import urllib.request
            data = urllib.parse.urlencode({"target": domain}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=self._REQUEST_TIMEOUT_S) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                return (resp.status, body, "")
        except Exception as e:
            return (0, None, f"{type(e).__name__}: {e}")

    def _extract_public_fields(self, raw_data: Any) -> dict[str, Any]:
        if not raw_data:
            return {}
        return self.parse_result_html(raw_data)

    # ------------------------------------------------------------------
    # Parsing (pure; fully unit-testable)
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_domain(keyword: str) -> str:
        d = (keyword or "").strip().lower()
        d = re.sub(r"^https?://", "", d)
        d = d.split("/")[0].split("?")[0].split("#")[0].split(":")[0]
        if d.startswith("www."):
            d = d[4:]
        return d

    @staticmethod
    def _strip_tags(fragment: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        return _html.unescape(text)

    @classmethod
    def _parse_host_table(cls, table_html: str, with_priority: bool = False) -> list[dict[str, Any]]:
        """Parse an A/MX/NS host table (7 columns) into records."""
        records: list[dict[str, Any]] = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", table_html, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(tds) < 4:
                continue
            col0 = cls._strip_tags(tds[0]).strip()
            if not col0 or col0.lower() == "host":
                continue  # header row
            # column 1: "IP\nreverse.dns"
            ip_lines = [ln.strip() for ln in cls._strip_tags(tds[1]).split("\n") if ln.strip()]
            ip = ip_lines[0] if ip_lines else ""
            rev_dns = ip_lines[1] if len(ip_lines) > 1 else ""
            # column 2: "ASN:\n40528\n192.0.32.0/22"
            asn_lines = [ln.strip() for ln in cls._strip_tags(tds[2]).split("\n") if ln.strip()]
            asn_number = ""
            asn_prefix = ""
            for ln in asn_lines:
                low = ln.lower()
                if low.startswith("asn"):
                    # forms: "ASN:40528" or "ASN:" on its own line
                    tail = re.sub(r"\D", "", ln)
                    if tail:
                        asn_number = tail
                    continue
                if re.fullmatch(r"\d+", ln):
                    asn_number = ln
                elif "/" in ln:
                    asn_prefix = ln
            # column 3: ASN name
            asn_name = " ".join(
                ln.strip() for ln in cls._strip_tags(tds[3]).split("\n") if ln.strip()
            )
            # column 4: open services (free text)
            services = " ".join(
                ln.strip() for ln in cls._strip_tags(tds[4]).split("\n") if ln.strip()
            )
            # column 5: reverse-IP count
            revip_raw = cls._strip_tags(tds[5]).strip()
            revip_count = int(rev_ip) if (rev_ip := re.sub(r"\D", "", revip_raw)) else None
            record: dict[str, Any] = {
                "host": col0,
                "ip": ip,
                "reverse_dns": rev_dns,
                "asn_number": asn_number,
                "asn_prefix": asn_prefix,
                "asn_name": asn_name,
                "open_services": services,
                "revip_count": revip_count,
            }
            if with_priority:
                m = re.match(r"^(\d+)\s+(.+)$", col0)
                if m:
                    record["priority"] = int(m.group(1))
                    record["host"] = m.group(2).strip()
            records.append(record)
        return records

    @classmethod
    def _table_after_heading(cls, html: str, heading: str) -> str:
        i = html.find(heading)
        if i < 0:
            return ""
        m = re.search(r"<table[^>]*>(.*?)</table>", html[i:], re.S)
        return m.group(1) if m else ""

    @classmethod
    def parse_result_html(cls, html: str) -> dict[str, Any]:
        """Parse a DNSdumpster result page into structured DNS records."""
        if not html or not html.strip():
            return {}
        if "Invalid domain" in html:
            return {
                "query_rejected": "invalid_domain",
                "subdomain_count": 0,
                "a_records": [],
                "mx_records": [],
                "ns_records": [],
                "txt_records": [],
            }

        fields: dict[str, Any] = {}
        # The "limited to 50 results" banner is static marketing copy shown on
        # every page; real truncation is signaled by hitting the cap.
        fields["free_tier_limit_noticed"] = "limited to 50 results" in html

        # A records (subdomains)
        a_table = ""
        m = re.search(r'<table[^>]*id="a_rec_table"[^>]*>(.*?)</table>', html, re.S)
        if m:
            a_table = m.group(1)
        a_records = cls._parse_host_table(a_table) if a_table else []
        fields["a_records"] = a_records
        fields["subdomain_count"] = len(a_records)
        fields["subdomains"] = [r["host"] for r in a_records]

        # MX / NS
        mx_records = cls._parse_host_table(cls._table_after_heading(html, "MX Records"), with_priority=True)
        ns_records = cls._parse_host_table(cls._table_after_heading(html, "NS Records"))
        fields["mx_records"] = mx_records
        fields["ns_records"] = ns_records

        # TXT records: &#34;value&#34; entities inside the TXT table
        txt_table = cls._table_after_heading(html, "TXT Records")
        txt_values: list[str] = []
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", txt_table, re.S):
            text = _html.unescape(cls._strip_tags(row)).strip()
            text = text.strip('"').strip("'").strip()
            if text:
                txt_values.append(text)
        fields["txt_records"] = txt_values

        # Aggregations
        ips = sorted({r["ip"] for r in a_records + mx_records + ns_records if r.get("ip")})
        fields["distinct_ips"] = ips
        fields["ip_count"] = len(ips)
        asns = sorted({
            f"AS{r['asn_number']}"
            for r in a_records + mx_records + ns_records
            if r.get("asn_number")
        })
        fields["distinct_asns"] = asns
        fields["truncated"] = fields["subdomain_count"] >= cls._FREE_TIER_LIMIT

        # Interesting business-function subdomains
        interesting: list[dict[str, str]] = []
        for host in fields["subdomains"]:
            label = host.split(".")[0].lower()
            if label in cls._INTERESTING_LABELS:
                interesting.append({"host": host, "label": label})
        fields["interesting_subdomains"] = interesting

        return fields
