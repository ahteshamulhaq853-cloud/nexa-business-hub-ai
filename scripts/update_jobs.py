#!/usr/bin/env python3
"""Refresh the public jobs feed from configured job-board listing pages.

This scraper is deliberately conservative: it only adds links that look like
individual vacancy pages, preserves the last known feed if sources are blocked,
and never invents deadlines or job details.
"""
from datetime import datetime, timezone
from html.parser import HTMLParser
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
    ("https://www.rozee.pk/", "Rozee.pk", "Private"),
    ("https://www.mustakbil.com/", "Mustakbil", "Private"),
    ("https://auth.brightspyre.com/jobs", "BrightSpyre", "Private"),
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
    r"\\b(job|vacanc|career|position|officer|director|manager|assistant|engineer|teacher|lecturer|intern|analyst|clerk|consultant|specialist|coordinator|supervisor|technician|professor|staff|driver|accountant|nurse|developer|designer|operator|inspector|scientist|secretary|executive|expert|administrator|account|finance|legal|procurement|statistician|monitoring|chairman|chief|lawyer|advisor|adviser|deputy|senior|junior|tax|technical|chemist|pharmacist|psychologist|social worker|economist|environmental|policy|sales|marketing|human resource|hr|data entry|support|lead|architect|hacker|representative|customer service|operations|implementation|creator|auditor|trainer|researcher|economist|doctor|medical|laboratory|security|planning|management)\\b", re.I
)

def valid_title(label):
    label = re.sub(r"\\s+", " ", str(label or "")).strip()
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
    label = re.sub(r"\\s+", " ", text).strip()
    if not valid_title(label):
        return False
    if host == "njp.gov.pk":
        return bool(re.fullmatch(r"/index\\.php/jobs/\\d+", path))
    if host == "jobs.gov.pk":
        return (
            "/jobseeker/viewjobdetails/" in path
            or bool(re.fullmatch(r"/(job|jobs|vacancy|vacancies)/\\d+/?", path))
            or bool(re.search(r"[?&](jobid|job_id|vacancyid|vacancy_id)=", url, re.I))
        )
    if host == "rozee.pk":
        return "/job/" in path and bool(re.search(r"/(jid/)?[a-z0-9-]*\\d+[a-z0-9-]*$", path))
    if host == "mustakbil.com":
        return bool(re.fullmatch(r"/jobs/job/\\d+/?", path))
    if host == "auth.brightspyre.com":
        return bool(re.fullmatch(r"/jobs/[a-z0-9_-]+/?", path)) and path.rstrip("/") != "/jobs"
    return False

def fetch_source(source_url, source_name, category):
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
