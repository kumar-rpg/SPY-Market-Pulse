"""Deploy a single self-contained HTML file to Vercel via the REST API.

No Vercel MCP connector is available inside cloud routine sessions, so this
talks to Vercel's deployments API directly with a bearer token from the
environment. First-ever deploy auto-creates the project.
"""

import os
import sys
import time

import requests

API = "https://api.vercel.com"
PROJECT_NAME = "spy-market-pulse"
TEAM_ID = "team_Uwme7PiLetDLe2RBEtegvViu"


def _headers():
    token = os.environ.get("VERCEL_TOKEN")
    if not token:
        sys.exit("Set VERCEL_TOKEN in your environment first.")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def deploy_html(html_source, filename="index.html"):
    body = {
        "name": PROJECT_NAME,
        "target": "production",
        "files": [{"file": filename, "data": html_source}],
        "projectSettings": {"framework": None},
    }
    r = requests.post(f"{API}/v13/deployments?teamId={TEAM_ID}", headers=_headers(), json=body, timeout=60)
    if r.status_code not in (200, 201):
        sys.exit(f"[{r.status_code}] Vercel deploy failed: {r.text[:400]}")
    dep = r.json()
    dep_id = dep["id"]
    url = dep.get("url")

    for _ in range(30):
        s = requests.get(f"{API}/v13/deployments/{dep_id}?teamId={TEAM_ID}", headers=_headers(), timeout=30)
        state = s.json().get("readyState")
        if state == "READY":
            return f"https://{url}"
        if state in ("ERROR", "CANCELED"):
            sys.exit(f"Vercel deployment {state}: {s.text[:400]}")
        time.sleep(5)
    sys.exit("Vercel deployment did not become READY in time.")
