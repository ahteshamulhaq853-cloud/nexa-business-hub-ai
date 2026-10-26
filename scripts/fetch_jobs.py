import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup

SOURCES = [
    ("government", "National Jobs Portal", "https://www.njp.gov.pk/index.php/jobs/live"),
    ("mixed", "National Employment Exchange", "https://jobs.gov.pk/?pageid=602"),
]
HEADERS = {"User-Agent": "NEXA-Careers-JobIndexer/1.0 (public job listing links; contact site owner for concerns)"}
jobs = []
seen = set()

def clean(value):
    return re.sub(r"\s+ ", " ", value or "").strip()

def looks_like_job(title):
    title = clean(title)
    if len(title) < 4 or len(title) > 150:
        return False
    bad = {"view all", "view details", "apply now", "latest jobs", "government jobs",
           "private jobs", "featured opportunities", "browse all jobs", "jobs by location"}
    return title.lower() not in bad and not title.lower().startswith("jobs by ")

for source_type, source_name, page_url in SOURCES:
    try:
        response = requests.get(page_url, headers=HEADERS, timeout=25)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for heading in soup.find_all(["h2", "h3", "h4"]):
            title = clean(heading.get_text(" ", strip=True))
            if not looks_like_job(title):
                continue
            container = heading
            link = None
            for _ in range(5):
                if container.parent is None:
                    break
                container = container.parent
                candidates = container.find_all("a", href=True)
                for a in candidates:
                    href = urljoin(page_url, a["href"])
                    host = urlparse(href).netloc.lower()
                    label = clean(a.get_text(" ", strip=True)).lower()
                    if host and host in urlparse(page_url).netloc.lower() and (
                        "view details" in label or "apply" in label or "jobs/" in href.lower()
                        or "job" in href.lower()
                    ):
                        link = href
                        break
                if link:
                    break
            if not link:
                continue
            host = urlparse(link).netloc.lower()
            if host not in {"www.njp.gov.pk", "njp.gov.pk", "jobs.gov.pk", "www.jobs.gov.pk"}:
                continue
            context = clean(container.get_text(" ", strip=True))
            if len(context) > 1800:
                context = context[:1800]
            if link in seen:
                continue
            seen.add(link)
            employer = ""
            for line in container.find_all(["p", "li", "strong"]):
                txt = clean(line.get_text(" ", strip=True))
                if txt and txt.lower() != title.lower() and len(txt) < 140:
                    employer = txt
                    break
            kind = "Government" if source_type == "government" or "government" in context.lower() else "Government / Private"
            jobs.append({
                "title": title,
                "company": employer or source_name,
                "location": "",
                "category": kind,
                "employment_type": "",
                "description": context,
                "url": link,
                "source": source_name,
                "source_url": page_url,
                "fetched_at": datetime.now(timezone.utc).isoformat()
            })
    except Exception as exc:
        print(f"Source failed: {page_url}: {exc}")

output = {
    "updated_at": datetime.now(timezone.utc).isoformat(),
    "sources": [url for _, _, url in SOURCES],
    "jobs": jobs[:100]
}
with open("data/jobs.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
print(f"Wrote {len(output['jobs'])} job records")
