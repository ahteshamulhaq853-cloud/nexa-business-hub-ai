#!/usr/bin/env python3
"""Refresh the public jobs feed from configured job-board listing pages.

This scraper is deliberately conservative: it only adds links that look like
individual vacancy pages, preserves the last known feed if sources are blocked,
and never invents deadlines or job details.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.request import Request, urlopen
import json
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "data" / "jobs.json"
SOURCES = [
    ("https://www.njp.gov.pk/index.php/jobs/live", "National Jobs Portal", "Government"),
    ("https://jobs.gov.pk/?pageid=602", "National Employment Exchange", "Government"),
    ("https://www.rozee.pk/EN/jobs-in-pakistan/", "Rozee.pk", "Private"),
    ("https://www.mustakbil.com/", "Mustakbil", "Private"),
    ("https://auth.brightspyre.com/jobs", "BrightSpyre", "Private"),
    ("https://etea.online/", "ETEA", "Government"),
]
GENERIC = {
    "home", "home page", "login", "log in", "sign in", "register", "sign up",
    "view all", "see all", "read more", "apply now", "apply", "search",
    "search jobs", "jobs", "latest jobs", "government jobs", "private jobs",
    "career", "careers", "about us", "contact us", "privacy policy",
    "terms and conditions", "next", "previous", "more", "details",
    "how to apply", "quick links", "lahore", "karachi", "islamabad",
    "rawalpindi", "remote", "hr & recruiting", "web & e-commerce"
}
JOB_WORDS = re.compile(
    r"\b(job|vacanc|career|position|officer|director|manager|assistant|engineer|teacher|lecturer|intern|analyst|clerk|consultant|specialist|coordinator|supervisor|technician|professor|staff|driver|accountant|nurse|developer|designer|operator|inspector|scientist|secretary|executive|expert|administrator|account|finance|legal|procurement|statistician|monitoring|chairman|chief|lawyer|advisor|adviser|deputy|senior|junior|tax|technical|chemist|pharmacist|psychologist|social worker|economist|environmental|policy|sales|marketing|human resource|hr|data entry|support|lead|architect|hacker|representative|customer service|operations|implementation|creator|auditor|trainer|researcher|economist|doctor|medical|laboratory|security|planning|management)\b", re.I
)

def valid_title(label):
    label = re.sub(r"\s+", " ", str(label or "")).strip()
    if not label or len(label) < 7 or len(label) > 180:
        return False
    if label.lower().strip(" -|:") in GENERIC:
        return False
    if not re.search(r"[A-Za-z]{3}", label) or not JOB_WORDS.search(label):
        return False
    return True

class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None
    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            attrs = dict(attrs)
            self.current = {"href": attrs.get("href", ""), "title": attrs.get("title", ""), "text": ""}
    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += " " + data
    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            self.links.append(self.current)
            self.current = None

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def read_feed():
    try:
        data = json.loads(FEED.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("jobs"), list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"updated_at": None, "sources": [s[0] for s in SOURCES], "jobs": []}

def canonical(url):
    url, _ = urldefrag(url)
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    return url.rstrip("/")

def looks_like_job(url, text, source_url):
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    path = p.path.lower()
    label = re.sub(r"\s+", " ", text).strip()
    if host == "etea.online":
        return path.startswith("/advertisement/") and len(label) >= 5 and bool(re.search(r"[A-Za-z]{3}", label))
    if not valid_title(label):
        return False
    if host == "njp.gov.pk":
        return bool(re.fullmatch(r"/index\.php/jobs/\d+", path))
    if host == "jobs.gov.pk":
        return (
            "/jobseeker/viewjobdetails/" in path
            or bool(re.fullmatch(r"/(job|jobs|vacancy|vacancies)/\d+/?", path))
            or bool(re.search(r"[?&](jobid|job_id|vacancyid|vacancy_id)=", url, re.I))
        )
    if host == "rozee.pk":
        # Rozee search URLs can contain job IDs in their slugs; exclude them.
        if "/jsearch/" in path or path.startswith("/EN/search/"):
            return False
        # Accept legacy individual vacancy slugs across Rozee's URL sections.
        return (
            bool(re.search(r"jobs-\d{4,}(?:[./]|$)", path))
            or bool(re.search(r"/job/(?:detail/)?\d{4,}/?$", path))
            or bool(re.search(r"[?&](jid|jobid|job_id|id)=\d+", url, re.I))
        )
    if host == "mustakbil.com":
        return bool(re.fullmatch(r"/jobs/job/\d+/?", path))
    if host == "auth.brightspyre.com":
        return bool(re.fullmatch(r"/jobs/[a-z0-9_-]+/?", path)) and path.rstrip("/") != "/jobs"
    return False


class EteaRows(HTMLParser):
    """Extract project rows and their linked advertisement images from ETEA."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.row = None
        self.cell = None
        self.anchor = None
    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag == "tr":
            self.row = []
        elif self.row is not None and tag in ("td", "th"):
            self.cell = {"text": "", "links": []}
        elif self.cell is not None and tag == "a":
            self.anchor = {"href": attrs.get("href", ""), "text": ""}
    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"] += " " + data
        if self.anchor is not None:
            self.anchor["text"] += " " + data
    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a" and self.anchor is not None:
            if self.cell is not None:
                self.cell["links"].append(self.anchor)
            self.anchor = None
        elif tag in ("td", "th") and self.cell is not None:
            self.cell["text"] = re.sub(r"\s+", " ", self.cell["text"]).strip()
            self.row.append(self.cell)
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None

def fetch_etea_source(source_url, source_name, category):
    req = Request(source_url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; NexaJobsFeed/1.0)",
        "Accept": "text/html,application/xhtml+xml"
    })
    with urlopen(req, timeout=25) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"HTTP {response.status}")
        raw = response.read(5_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
    parser = EteaRows()
    parser.feed(raw.decode(charset, errors="replace"))
    found = []
    seen = set()
    for row in parser.rows:
        if len(row) < 5:
            continue
        title = row[1]["text"]
        code = row[2]["text"] if len(row) > 2 else ""
        last_date = row[3]["text"] if len(row) > 3 else ""
        if not title or re.search(r"\b(?:B-1|A-1)\s+Examination\b|\bRetotaling\b", title, re.I):
            continue
        ad_links = row[4]["links"] if len(row) > 4 else []
        ad_url = next((canonical(urljoin(source_url, link.get("href", "")))
                       for link in ad_links
                       if link.get("href") and "/advertisement/" in urlparse(urljoin(source_url, link["href"])).path.lower()), "")
        if not ad_url or ad_url in seen:
            continue
        seen.add(ad_url)
        normalized_date = ""
        for fmt in ("%d-%B-%Y", "%d-%b-%Y", "%d %B %Y", "%d %b %Y"):
            try:
                normalized_date = datetime.strptime(last_date.strip(), fmt).date().isoformat()
                break
            except ValueError:
                pass
        description = f"ETEA recruitment project {code}. Last date shown on ETEA portal: {last_date or 'Check official advertisement'}. Open the official advertisement for eligibility, vacancies, and application instructions."
        found.append({
            "title": title[:180],
            "company": "ETEA / " + title,
            "location": "Khyber Pakhtunkhwa",
            "category": category,
            "employment_type": "Government Recruitment",
            "description": description,
            "education_required": "See official advertisement",
            "experience_needed": "See official advertisement",
            "experience_field": "",
            "skills_needed": "See official advertisement",
            "salary": "See official advertisement",
            "age_limit": "See official advertisement",
            "last_date_to_apply": normalized_date or last_date,
            "availability": "Active",
            "official_url": ad_url,
            "url": ad_url,
            "source": source_name,
            "source_url": source_url,
            "project_code": code,
            "fetched_at": now_iso()
        })
    return found


def fetch_source(source_url, source_name, category):
    if urlparse(source_url).netloc.lower().removeprefix("www.") == "etea.online":
        return fetch_etea_source(source_url, source_name, category)
    req = Request(source_url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; NexaJobsFeed/1.0; +https://github.com/ahteshamulhaq853-cloud/nexa-business-hub-ai)",
        "Accept": "text/html,application/xhtml+xml"
    })
    with urlopen(req, timeout=25) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"HTTP {response.status}")
        raw = response.read(5_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
    html = raw.decode(charset, errors="replace")
    parser = Links()
    parser.feed(html)
    found = []
    seen = set()
    for item in parser.links:
        label = re.sub(r"\s+", " ", (item.get("text", "") + " " + item.get("title", ""))).strip()
        url = canonical(urljoin(source_url, item.get("href", "")))
        if not url or url in seen or not looks_like_job(url, label, source_url):
            continue
        seen.add(url)
        title = re.sub(r"\s+", " ", item.get("text", "")).strip() or item.get("title", "").strip()
        title = re.sub(r"\s*[-|:]\s*(view details|apply now|read more)$", "", title, flags=re.I).strip()
        if not valid_title(title):
            continue
        found.append({
            "title": title[:180],
            "company": "",
            "location": "",
            "category": category,
            "employment_type": "",
            "description": "Vacancy listing imported from " + source_name + ". Open the official listing for full requirements and application instructions.",
            "url": url,
            "source": source_name,
            "source_url": source_url,
            "fetched_at": now_iso()
        })
    return found

def fetch_job_location(job_url):
    """Best-effort location extraction from an individual official job page."""
    try:
        req = Request(job_url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; NexaJobsFeed/1.0)",
            "Accept": "text/html,application/xhtml+xml"
        })
        with urlopen(req, timeout=12) as response:
            raw = response.read(1_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
        html = raw.decode(charset, errors="replace")

        # Prefer structured JobPosting/JSON-LD location data when present.
        for block in re.findall(r"""<script[^>]*type=["']application/ld\+json["'][^>]*>(.*?)</script>""", html, re.I | re.S):
            try:
                data = json.loads(unescape(block).strip())
            except (json.JSONDecodeError, TypeError):
                continue
            candidates = data if isinstance(data, list) else [data]
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                if item.get("@graph") and isinstance(item["@graph"], list):
                    candidates.extend(x for x in item["@graph"] if isinstance(x, dict))
                loc = item.get("jobLocation", [])
                if isinstance(loc, dict):
                    loc = [loc]
                for place in loc if isinstance(loc, list) else []:
                    if not isinstance(place, dict):
                        continue
                    address = place.get("address", {})
                    if isinstance(address, str):
                        value = address.strip()
                    elif isinstance(address, dict):
                        value = ", ".join(str(address.get(k, "")).strip() for k in ("addressLocality", "addressRegion", "addressCountry") if address.get(k))
                    else:
                        value = ""
                    if value and len(value) <= 120:
                        return value

        # Fall back to visible label/value patterns in the official page.
        plain = unescape(re.sub(r"<[^>]+>", " ", html))
        plain = re.sub(r"\s+", " ", plain)
        patterns = [
            r"\b(?:job\s+)?location\s*[:：]\s*([^|;]{2,100}?)(?=\s{2,}|\b(?:job type|employment type|salary|deadline|apply|description)\b|$)",
            r"\\bcity\\s*[:：]\\s*([A-Z][A-Za-z .,'()-]{1,70}?)(?=\\s{2,}|\\b(?:state|country|salary|deadline|apply)\\b|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, plain, re.I)
            if match:
                value = re.sub(r"\s+", " ", match.group(1)).strip(" -,:;|")
                if value and not re.search(r"^(?:not specified|unknown|n/?a|view job|details)$", value, re.I):
                    return value[:120]
    except Exception:
        pass
    return ""


def main():
    feed = read_feed()
    existing = feed.get("jobs", [])
    if not isinstance(existing, list):
        existing = []
    # Keep known records first so existing structured details are not overwritten
    # by shorter listing-page link text.
    by_url = {}
    for job in existing:
        if not isinstance(job, dict) or not job.get("url"):
            continue
        job_url = canonical(str(job["url"]))
        title = str(job.get("title", "")).strip()
        # Remove previously imported navigation/category links as well.
        if job_url and looks_like_job(job_url, title, str(job.get("source_url", ""))):
            by_url[job_url] = job

    successes = 0
    newly_found = 0
    errors = []
    for url, name, category in SOURCES:
        try:
            jobs = fetch_source(url, name, category)
            successes += 1
            for job in jobs:
                key = canonical(job["url"])
                if key and key not in by_url:
                    by_url[key] = job
                    newly_found += 1
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
            print(f"WARNING: failed to fetch {name}: {exc}", file=sys.stderr)

    if successes == 0:
        print("ERROR: every job source failed; leaving jobs.json unchanged.", file=sys.stderr)
        return 1

    # Gradually enrich older records with real locations from official detail pages.
    # Limit requests per run so hourly refreshes stay lightweight; never guess a location.
    missing_locations = [job for job in by_url.values() if not str(job.get("location", "")).strip()]
    enriched = 0
    for job in missing_locations[:12]:
        location = fetch_job_location(str(job.get("url", "")))
        if location:
            job["location"] = location
            enriched += 1
    print(f"Location enrichment: {enriched} locations found from {min(len(missing_locations), 12)} official detail pages checked.")

    # Refresh timestamp only after at least one source responded. Existing jobs
    # remain available when a source blocks automated requests.
    output = {
        "updated_at": now_iso(),
        "sources": [s[0] for s in SOURCES],
        "jobs": list(by_url.values())
    }
    FEED.parent.mkdir(parents=True, exist_ok=True)
    FEED.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Feed refreshed: {successes}/{len(SOURCES)} sources responded; {newly_found} new individual listings; {len(output['jobs'])} total records.")
    if errors:
        print("Some sources may block automated access; retained the existing records.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
