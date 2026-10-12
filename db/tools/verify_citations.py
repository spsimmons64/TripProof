"""Check every compliancedocs citation against the law it points at.

For each row this fetches the cited CFR section or part (eCFR) or Florida statute (flsenate.gov) and
prints the heading the source actually carries, so a citation aimed at the wrong section shows up:
49 CFR 390.19, for instance, is motor carrier identification reports for certain Mexico-domiciled
carriers, not USDOT registration (that is 390.201). U.S. Code cites are listed for a person to read.

Run it after loading a jurisdiction; it reads the database through the running tp-api container:

    python3 db/tools/verify_citations.py
"""
import re, html, json, subprocess, urllib.request, gzip

def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    t = html.unescape(re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "ignore")))
    return re.sub(r"\s+", " ", t)

def cfr(title, sec):
    kind, num = ("part", sec.split()[-1]) if sec.lower().startswith("part") else ("section", sec)
    t = get(f"https://www.ecfr.gov/api/versioner/v1/full/2026-09-01/title-{title}.xml?{kind}={num}")
    m = re.search(rf"(§+\s*{re.escape(num)}|Part\s+{re.escape(num)})\s+([^.]{{0,110}}\.)", t)
    return (m.group(0) if m else t[:120]).strip()

def fs(sec):
    t = get(f"https://www.flsenate.gov/Laws/Statutes/2024/{sec}")
    m = re.search(rf"{re.escape(sec)}\s+([A-Z][^.]{{0,110}}\.)", t)
    return f"F.S. {sec} {m.group(1)}" if m else t[:120]

rows = json.loads(subprocess.run(["podman", "exec", "tp-api", "python", "-c",
    "import json;from sqlalchemy import text;from app.db import engine\n"
    "with engine.connect() as c:\n"
    "    print(json.dumps([dict(r._mapping) for r in c.execute(text("
    "'SELECT jurisdiction, code, legalcitation, sourceurl FROM compliancedocs ORDER BY jurisdiction DESC, sortorder'))], default=str))"],
    capture_output=True, text=True).stdout)

for r in rows:
    cite = r["legalcitation"] or ""
    for one in [c.strip() for c in cite.split(";") if c.strip()]:
        try:
            m = re.match(r"(\d+)\s+CFR\s+(part\s+[\d.]+|[\d.]+[A-Za-z]?)", one)
            u = re.match(r"(\d+)\s+U\.S\.C\.\s+([\w.]+)", one)
            f = re.match(r"F\.S\.\s+([\d.]+)", one)
            if m:   got = cfr(m.group(1), m.group(2))
            elif f: got = fs(f.group(1))
            elif u: got = "USC " + u.group(2) + " (checked separately)"
            else:   got = "NO PATTERN"
        except Exception as e:
            got = f"ERROR {e}"
        print(f"{r['jurisdiction']:3} {r['code'][:26]:27} {one[:34]:35} -> {got[:105]}")
