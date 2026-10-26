import json
import re
from datetime import datetime, timezone, date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SOURCES = [
    ("government", "National Jobs Portal", "https://www.njp.gov.pk/index.php/jobs/live"),
    ("mixed", "National Employment Exchange", "https://jobs.gov.pk/?pageid=602"),
    ("private", "ROZEE.PK", "https://www.rozee.pk/"),
    ("private", "Mustakbil", "https://www.mustakbil.com/"),
    ("private", "BrightSpyre", "https://auth.brightspyre.com/jobs"),
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NEXA-Careers-JobIndexer/2.0; public listings)"}
MISSING = "Not specified in advertisement"
session = requests.Session()
session.headers.update(HEADERS)
jobs, seen = [], set()
updated = datetime.now(timezone.utc).isoformat()

def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()

def host_matches(url, page_url):
    host = (urlparse(url).hostname or "").lower()
    source = (urlparse(page_url).hostname or "").lower()
    return bool(host and source and (host == source or host.endswith("." + source) or source.endswith("." + host)))

def valid_title(title):
    title = clean(title)
    bad = {"how to apply", "quick links", "categories", "view all", "view details", "apply now",
           "latest jobs", "government jobs", "private jobs", "featured opportunities",
           "browse all jobs", "land your dream job", "find your industry", "hire smarter with ai-powered recruiting"}
    return 4 <= len(title) <= 150 and title.lower() not in bad and not title.lower().startswith("jobs by ")

def parse_date(text):
    patterns = [
        r"(?:last date(?: to apply)?|closing date|deadline|apply before|available till|last date for submission)\s*:?\s*(\d{1,2}[ -][A-Za-z]{3,9}[ ,.-]*\d{4}|\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2})",
        r"(?:last date(?: to apply)?|closing date|deadline|apply before|available till)\s*:?\s*([A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            raw = clean(m.group(1)).replace(",", "")
            for fmt in ("%d %b %Y", "%d %B %Y", "%d-%b-%Y", "%d-%B-%Y",
                        "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d", "%b %d %Y", "%B %d %Y"):
                try:
                    return datetime.strptime(raw, fmt).date().isoformat()
                except ValueError:
                    pass
    return ""

def field_from_text(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return clean(match.group(1)).strip(" :-|")
    return MISSING

def extract_details(url, title, card_context, source_type, source_name):
    # Fetch the individual job page; never infer missing criteria from a portal title.
    response = session.get(url, timeout=25)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    page_text = clean(soup.get_text(" ", strip=True))
    combined = page_text[:30000]
    if re.search(r"\b(expired|position closed|applications? (?:are )?closed|no longer accepting applications)\b", combined, re.I):
        return None
    deadline = parse_date(combined)
    if deadline and date.fromisoformat(deadline) < datetime.now(timezone.utc).date():
        return None

    employer = field_from_text(combined, [
        r"(?:company|organization|organisation|employer)\s*:?\s*([^|]{2,100}?)(?=\s+(?:location|job type|employment type|qualification|education|experience|salary|apply|deadline)\b|[|]|$)"
    ])
    location = field_from_text(combined, [
        r"(?:job location|location|city)\s*:?\s*([^|]{2,100}?)(?=\s+(?:company|organization|job type|employment type|qualification|education|experience|salary|apply|deadline)\b|[|]|$)"
    ])
    education = field_from_text(combined, [
        r"(?:education required|required qualification|qualification|education)\s*:?\s*([^|]{2,220}?)(?=\s+(?:experience|skills|salary|age limit|location|apply|deadline)\b|[|]|$)"
    ])
    experience = field_from_text(combined, [
        r"(?:required|relevant|professional|post[- ]?qualification|work)?\s*experience\s*(?:in|with|of)\s+([^|]{2,220}?)(?=\s+(?:salary|age limit|location|qualification|education|skills|apply|deadline)\b|[|]|$)",
        r"(?:experience needed|required experience|experience)\s*:?\s*([^|]{2,220}?)(?=\s+(?:skills|salary|age limit|location|qualification|education|apply|deadline)\b|[|]|$)"
    ])
    # Capture the experience domain separately when the advertisement names one.
    experience_field = field_from_text(combined, [
        r"(?:experience|experienced)\s+(?:in|of|with)\s+([^|.]{2,180}?)(?=\s+(?:for|salary|age limit|location|qualification|education|skills|apply|deadline)\b|[|.]|$)",
        r"(?:relevant|professional|work)\s+experience\s+(?:in|of|with)\s+([^|.]{2,180}?)(?=\s+(?:for|salary|age limit|location|qualification|education|skills|apply|deadline)\b|[|.]|$)"
    ])
    skills = field_from_text(combined, [
        r"(?:skills needed|required skills|skills)\s*:?\s*([^|]{2,260}?)(?=\s+(?:salary|age limit|location|qualification|education|experience|apply|deadline)\b|[|]|$)"
    ])
    salary = field_from_text(combined, [
        r"(?:salary|pay package|monthly salary|compensation)\s*:?\s*([^|]{2,120}?)(?=\s+(?:age limit|location|qualification|education|experience|apply|deadline)\b|[|]|$)"
    ])
    age = field_from_text(combined, [
        r"(?:age limit|max(?:imum)? age|age)\s*:?\s*([^|]{2,100}?)(?=\s+(?:salary|location|qualification|education|experience|apply|deadline)\b|[|]|$)"
    ])
    # Keep original source page as the application/reference URL unless an actual ad PDF is linked.
    official_url = url
    pdf_links = []
    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        label = clean(a.get_text(" ", strip=True)).lower()
        if href.lower().split("?")[0].endswith(".pdf") and any(k in label for k in ("advert", "download", "job", "detail", "vacan", "notice")):
            pdf_links.append(href)
    if source_type in ("government", "mixed") and pdf_links:
        official_url = pdf_links[0]

    # For the official portal's own summary pages, retain explicitly published card text,
    # but do not promote portal snippets into education, skills, salary, or age fields.
    if employer == MISSING:
        byline = re.search(r"\bby\s+(.+?)(?:\s+(?:contract|regular|bps|pps|spps|experience|available till)\b|$)", clean(card_context), re.I)
        if byline:
            employer = clean(byline.group(1))
    return {
        "title": title,
        "company": employer,
        "location": location,
        "category": "Government" if source_type == "government" else ("Government / Private" if source_type == "mixed" else "Private"),
        "employment_type": field_from_text(combined, [r"(?:employment type|job type|type of employment)\s*:?\s*([^|]{2,100}?)(?=\s+(?:salary|location|qualification|education|experience|apply|deadline)\b|[|]|$)"]),
        "description": clean(card_context)[:1800],
        "education_required": education,
        "experience_needed": experience,
        "experience_field": experience_field,
        "skills_needed": skills,
        "salary": salary,
        "age_limit": age,
        "last_date_to_apply": deadline or MISSING,
        "availability": "Active" if not deadline or date.fromisoformat(deadline) >= datetime.now(timezone.utc).date() else "Expired",
        "official_url": official_url,
        "url": url,
        "source": source_name,
        "source_url": url,
        "verified_detail_page": True,
        "fetched_at": updated,
    }

for source_type, source_name, page_url in SOURCES:
    try:
        response = session.get(page_url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        for heading in soup.find_all(["h2", "h3", "h4"]):
            title = clean(heading.get_text(" ", strip=True))
            if not valid_title(title):
                continue
            container, link, best = heading, None, heading.parent or heading
            for _ in range(6):
                if container.parent is None:
                    break
                container = container.parent
                for anchor in container.find_all("a", href=True):
                    href = urljoin(page_url, anchor.get("href", "").strip())
                    label = clean(anchor.get_text(" ", strip=True)).lower()
                    path = urlparse(href).path.lower()
                    if host_matches(href, page_url) and (
                        any(word in path for word in ("/job", "/jobs", "/career", "/vacanc"))
                        or "apply" in label or "view job" in label or "view details" in label
                    ):
                        link, best = href, container
                        break
                if link:
                    break
            if not link or link.split("#")[0].rstrip("/") == page_url.split("?")[0].rstrip("/"):
                continue
            if link in seen:
                continue
            context = clean(best.get_text(" ", strip=True))
            if re.search(r"\bexpired\b|position\s+closed|applications?\s+closed", context, re.I):
                continue
            if re.search(r"overseas|saudi arabia|united arab emirates|qatar|kuwait|oman|riyadh|abroad", context, re.I):
                continue
            try:
                job = extract_details(link, title, context, source_type, source_name)
            except Exception as exc:
                print(f"Skipping unverified detail page {link}: {exc}")
                continue
            if not job:
                continue
            seen.add(link)
            jobs.append(job)
    except Exception as exc:
        print(f"Source failed: {page_url}: {exc}")

output = {"updated_at": updated, "sources": [url for _, _, url in SOURCES], "jobs": jobs[:300]}
with open("data/jobs.json", "w", encoding="utf-8") as file:
    json.dump(output, file, ensure_ascii=False, indent=2)
print(f"Wrote {len(output['jobs'])} individually fetched job records from {len(SOURCES)} sources")
