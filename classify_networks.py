"""Phân loại 384 dự án từ master_import.csv theo affiliate network.

Output: skills/network_classification.md
"""
import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlparse

CSV = Path(__file__).parent / "data" / "master_import.csv"
OUT = Path(__file__).parent / "skills" / "network_classification.md"

# Mapping domain pattern → (network name, status)
# Network nào white-label theo brand: pattern là {brand}.{domain}
NETWORKS = [
    # White-label (mỗi brand 1 subdomain) — pattern là *.{domain}
    (r"\.getrewardful\.com$",      "Rewardful",       True,  "✅ DONE"),
    (r"\.firstpromoter\.com$",     "FirstPromoter",   True,  "❌ TODO"),
    (r"\.tolt\.io$",               "Tolt",            True,  "❌ TODO"),
    (r"\.promotekit\.com$",        "PromoteKit",      True,  "❌ TODO"),
    (r"\.goaffpro\.com$",          "GoAffPro",        True,  "❌ TODO"),
    (r"\.trackdesk\.com$",         "Trackdesk",       True,  "❌ TODO"),

    # Single-domain (tất cả tài khoản chung 1 host) — pattern khớp đầy đủ
    (r"^dash\.partnerstack\.com$", "PartnerStack",    False, "❌ TODO (multi-account / cookie conflict)"),
    (r"^partners\.dub\.co$",       "Dub.co Partners", False, "❌ TODO (multi-account)"),
    (r"^app\.impact\.com$",        "Impact",          False, "❌ TODO (multi-account)"),
    (r"^af\.uppromote\.com$",      "UpPromote",       False, "❌ TODO (multi-account)"),
    (r"^app\.getreditus\.com$",    "Reditus",         False, "❌ TODO (multi-account)"),
    (r"\.refersion\.com$",         "Refersion",       True,  "❌ TODO"),

    # Per-brand custom hostnames
    (r"\.affiliately\.com$",       "Affiliatly",      True,  "❌ TODO"),
    (r"\.tapfiliate\.com$",        "Tapfiliate",      True,  "❌ TODO"),
    (r"\.tapaffiliate\.com$",      "Tapfiliate",      True,  "❌ TODO"),

    # Smaller / less common platforms found in master
    (r"\.affonso\.io$",            "Affonso",         True,  "❌ TODO"),
    (r"\.affise\.com$",            "Affise",          True,  "❌ TODO"),
    (r"\.postaffiliatepro\.com$",  "PostAffiliatePro",True,  "❌ TODO"),
]


def classify_domain(host: str) -> tuple[str, bool, str]:
    """Trả về (network_name, is_white_label, status). 'Khác' nếu chưa match."""
    h = host.lower()
    for pattern, name, white_label, status in NETWORKS:
        if re.search(pattern, h):
            return name, white_label, status
    return "Khác / chưa phân loại", False, "❓ Unknown"


def main():
    rows = []
    with open(CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            url = (r.get("Affiliate Login") or "").strip()
            project = (r.get("Project") or "").strip()
            email = (r.get("Email") or "").strip()
            owner = (r.get("Account Reg") or "").strip()
            if not url or not project:
                continue
            host = urlparse(url).netloc.lower()
            net, wl, status = classify_domain(host)
            rows.append({
                "project": project,
                "host": host,
                "url": url,
                "email": email,
                "owner": owner,
                "network": net,
                "status": status,
            })

    # Tổng hợp
    by_net = defaultdict(list)
    for r in rows:
        by_net[r["network"]].append(r)

    # Output markdown
    lines = []
    lines.append("# Phân loại 384 dự án theo Affiliate Network\n")
    lines.append(f"Phân tích từ `data/master_import.csv` — tổng **{len(rows)}** dự án.\n")

    # Bảng tổng quan
    lines.append("## Tổng quan\n")
    lines.append("| Network | Số dự án | Status | Loại |")
    lines.append("|---|---|---|---|")
    sorted_nets = sorted(by_net.items(), key=lambda x: (-len(x[1]), x[0]))
    for net, items in sorted_nets:
        status = items[0]["status"]
        # Mỗi network có thể có brand riêng (white-label) hoặc chung 1 host
        unique_hosts = len(set(i["host"] for i in items))
        if unique_hosts > 1:
            kind = f"White-label ({unique_hosts} brands)"
        else:
            kind = f"Single-host ({items[0]['host']})"
        lines.append(f"| **{net}** | {len(items)} | {status} | {kind} |")
    lines.append("")

    # Chi tiết từng network
    lines.append("## Chi tiết\n")
    for net, items in sorted_nets:
        status = items[0]["status"]
        lines.append(f"### {net} — {len(items)} dự án {status}\n")
        # Group by host trong network để liệt kê brands
        by_host = defaultdict(list)
        for r in items:
            by_host[r["host"]].append(r)
        if len(by_host) > 1:
            lines.append(f"<details><summary>{len(by_host)} brands</summary>\n")
            lines.append("| Project | Host | Owner | Email |")
            lines.append("|---|---|---|---|")
            for r in sorted(items, key=lambda x: x["project"]):
                lines.append(f"| {r['project']} | {r['host']} | {r['owner']} | `{r['email']}` |")
            lines.append("\n</details>\n")
        else:
            host = list(by_host.keys())[0]
            lines.append(f"Host: `{host}` ({len(items)} accounts)\n")
            lines.append("| Project | Owner | Email |")
            lines.append("|---|---|---|")
            for r in sorted(items, key=lambda x: x["project"]):
                lines.append(f"| {r['project']} | {r['owner']} | `{r['email']}` |")
            lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    # Console summary
    print("\n=== Summary ===")
    for net, items in sorted_nets:
        print(f"  {len(items):4d}  {net:30s}  {items[0]['status']}")


if __name__ == "__main__":
    main()
