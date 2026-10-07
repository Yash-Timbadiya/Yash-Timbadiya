"""
Scrape real daily contribution counts from GitHub's public, unauthenticated
contributions endpoint (the same fragment the profile page uses) and write
data/contributions.json with the raw days plus derived stats.

No token, no auth, no GraphQL. Run daily by .github/workflows/update-profile-art.yml.
"""
import datetime
import json
import os
import re
import sys

import requests
from bs4 import BeautifulSoup

USERNAME = os.environ.get("GH_USER", "Yash-Timbadiya")
URL = f"https://github.com/users/{USERNAME}/contributions"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "contributions.json")


def fetch_days():
    resp = requests.get(URL, headers={"User-Agent": "profile-readme-bot/1.0"}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    tips = {t["for"]: t.get_text(strip=True) for t in soup.select("tool-tip[for]")}
    cells = soup.select("td.ContributionCalendar-day[data-date]")
    if not cells:
        sys.exit("no calendar cells found -- github markup may have changed")

    days = []
    for td in cells:
        text = tips.get(td.get("id"), "")
        m = re.match(r"(\d+)", text)
        days.append({
            "date": td["data-date"],
            "count": int(m.group(1)) if m else 0,
            "level": int(td.get("data-level") or 0),
        })
    days.sort(key=lambda d: d["date"])
    return days


def current_streak(days):
    idx = len(days) - 1
    if days[idx]["count"] == 0:
        idx -= 1  # today isn't over yet -- don't break the streak on it
    end_idx = idx
    while idx >= 0 and days[idx]["count"] > 0:
        idx -= 1
    length = end_idx - idx
    if not length:
        return {"length": 0, "start": None, "end": None}
    return {"length": length, "start": days[idx + 1]["date"], "end": days[end_idx]["date"]}


def longest_streak(days):
    best = {"length": 0, "start": None, "end": None}
    run_start = None
    for i, d in enumerate(days):
        if d["count"] > 0:
            run_start = i if run_start is None else run_start
            if i - run_start + 1 > best["length"]:
                best = {"length": i - run_start + 1, "start": days[run_start]["date"], "end": d["date"]}
        else:
            run_start = None
    return best


def build_data(days):
    total = sum(d["count"] for d in days)
    active = sum(1 for d in days if d["count"] > 0)
    best = max(days, key=lambda d: d["count"])
    monthly = {}
    for d in days:
        monthly[d["date"][:7]] = monthly.get(d["date"][:7], 0) + d["count"]
    return {
        "username": USERNAME,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "range": {"start": days[0]["date"], "end": days[-1]["date"]},
        "total_contributions": total,
        "active_days": active,
        "avg_per_active_day": round(total / active, 1) if active else 0,
        "current_streak": current_streak(days),
        "longest_streak": longest_streak(days),
        "best_day": {"date": best["date"], "count": best["count"]},
        "monthly": [{"month": k, "total": v} for k, v in sorted(monthly.items())],
        "days": days,
    }


if __name__ == "__main__":
    data = build_data(fetch_days())
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"wrote data/contributions.json: {data['total_contributions']} contributions, "
          f"current streak {data['current_streak']['length']}, "
          f"longest streak {data['longest_streak']['length']}")
