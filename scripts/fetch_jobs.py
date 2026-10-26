import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Public listing pages only. Some portals may block automated access or change markup.
SOURCES = [
    ("government", "National Jobs Portal", "https://www.njp.gov.pk/index.php/jobs/live"),
    ("mixed", "National Employment Exchange", "https://jobs.gov.pk/?pageid=602"),
    ("private", "ROZEE.PK", "https://www.rozee.pk/"),
    ("private", "Mustakbil", "https://www.mustakbil.com/"),
    ("private", "BrightSpyre", "https://auth.brightspyre.com/jobs"),
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NEXA-Careers-JobIndexer/1.0; public listing links)"
}
jobs = []
seen = set()
updated = datetime.now(timezone.utc).isoformat()

def clean(value):
    return re.sub(r"\\s+", " ", value or "").strip()

def looks_like_job(title):
    title = clean(title)
    if len(title) < 4 or len(title) > 150:
        return False
    bad = {
        "view all", "view details", "apply now", "latest jobs", "government jobs",
        "private jobs", "featured opportunities", "browse all jobs", "jobs by location",
        "view all jobs", "latest job openings", "land your dream job"
    }
    return title.lower() not in bad and not title.lower().startswith("jobs by ")

def same_source_host(link, page_url):
    host = (urlparse(link).hostname or "").lower()
    source_host = (urlparse(page_url).hostname or "").lower()
    if not host or not source_host:
        return False
    # BrightSpyre uses subdomains for individual organizations.
    return host == source_host or host.endswith("." + source_host) or source_host.endswith("." + host)

for source_type, source_name, page_url in SOURCES:
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        # Job cards commonly use h2/h3/h4 headings. Search nearby containers for
        # the original listing link rather than copying job descriptions wholesale.
        for heading in soup.find_all(["h2", "h3", "h4"]):
            title = clean(heading.get_text(" ", strip=True))
            if not looks_like_job(title):
                continue

            container = heading
            link = None
            best_container = heading.parent or heading
            for _ in range(6):
                if container.parent is None:
                    break
                container = container.parent
                candidates = container.find_all("a", href=True)
                for anchor in candidates:
                    href = urljoin(page_url, anchor.get("href", "").strip())
                    label = clean(anchor.get_text(" ", strip=True)).lower()
                    path = urlparse(href).path.lower()
                    if same_source_host(href, page_url) and (
                        any(word in path for word in ("/job", "/jobs", "/career", "/vacanc"))
                        or "apply" in label or "view job" in label or "view details" in label
                    ):
                        link = href
                        best_container = container
                        break
                if link:
                    break

            if not link or link.split("#")[0].rstrip("/") == page_url.split("?")[0].rstrip("/"):
                continue
            if link in seen:
                continue

            context = clean(best_container.get_text(" ", strip=True))
            if re.search(r"\\bexpired\\b|position\\s+closed|applications?\\s+closed", context, re.I):
                continue
            if re.search(r"overseas|saudi arabia|united arab emirates|qatar|kuwait|oman|riyadh|abroad", context, re.I):
                continue

            seen.add(link)
            employer = ""
            for element in best_container.find_all(["p", "li", "strong", "span"]):
                candidate = clean(element.get_text(" ", strip=True))
                if candidate and candidate.lower() != title.lower() and len(candidate) < 120:
                    if candidate.lower() not in {"featured", "new", "view job", "apply now"}:
                        employer = candidate
                        break

            if source_type == "government":
                category = "Government"
            elif source_type == "mixed":
                category = "Government / Private"
            else:
                category = "Private"

            jobs.append({
                "title": title,
                "company": employer or source_name,
                "location": "",
                "category": category,
                "employment_type": "",
                "description": context[:1800],
                "url": link,
                "source": source_name,
                "source_url": page_url,
                "fetched_at": updated
            })
    except Exception as exc:
        print(f"Source failed: {page_url}: {exc}")

# Keep a generous limit to avoid publishing an unbounded or malformed feed.
output = {
    "updated_at": updated,
    "sources": [url for _, _, url in SOURCES],
    "jobs": jobs[:500]
}
with open("data/jobs.json", "w", encoding="utf-8") as file:
    json.dump(output, file, ensure_ascii=False, indent=2)
print(f"Wrote {len(output['jobs'])} job records from {len(SOURCES)} configured sources")
