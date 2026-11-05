"""Check the pinned Python packages against the OSV vulnerability database.

OSV (https://osv.dev) collects known vulnerabilities of open-source packages
per version. This script sends the name and version of every package in
``constraints.txt`` (nothing else) and lists those with known advisories,
with the versions that fix them and the latest release on PyPI.

Run it now and then: a version that is clean today can get an advisory
tomorrow. It needs internet access and uses only the standard library, so
any Python 3.9+ works, inside Docker or not.

Usage:
    python3 scripts/check_vulns.py                  # constraints.txt
    python3 scripts/check_vulns.py --file other.txt # another name==version list
    python3 scripts/check_vulns.py --details 20     # show more advisories per package

Exit code: 0 when nothing is found, 1 when some package has advisories,
2 when the database could not be reached.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

OSV_BATCH_URL = "https://api.osv.dev/v1/querybatch"
OSV_VULN_URL = "https://api.osv.dev/v1/vulns/{}"
PYPI_URL = "https://pypi.org/pypi/{}/json"
TIMEOUT = 30


def read_pins(path: str) -> list[tuple[str, str]]:
    """Read ``name==version`` lines, skipping comments, blanks and extras.

    Args:
        path: A requirements or constraints file.

    Returns:
        ``(name, version)`` pairs in file order.
    """
    pins = []
    with open(path, encoding="utf-8") as handle:
        for raw in handle:
            line = raw.split("#", 1)[0].strip()
            if "==" not in line:
                continue
            name, version = line.split("==", 1)
            pins.append((name.split("[", 1)[0].strip(), version.strip()))
    return pins


def _get_json(url: str, body: dict | None = None) -> dict:
    """GET (or POST ``body`` as JSON to) ``url`` and decode the JSON answer."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read())


def advisory_ids(pins: list[tuple[str, str]]) -> dict[tuple[str, str], list[str]]:
    """Ask OSV which of the pinned versions have known advisories.

    Args:
        pins: ``(name, version)`` pairs.

    Returns:
        Advisory ids per affected pin (pins without advisories are left out).
    """
    queries = [{"package": {"name": n, "ecosystem": "PyPI"}, "version": v} for n, v in pins]
    results = _get_json(OSV_BATCH_URL, {"queries": queries})["results"]
    return {pin: [v["id"] for v in res.get("vulns", [])] for pin, res in zip(pins, results) if res.get("vulns")}


def _normalize(name: str) -> str:
    """Return a package name in PyPI's normalized form (lower case, '-' separators)."""
    return name.lower().replace("_", "-").replace(".", "-")


def advisory_summary(vuln_id: str, package: str) -> tuple[str, list[str]]:
    """Return an advisory's one-line summary and the versions that fix it for ``package``."""
    data = _get_json(OSV_VULN_URL.format(vuln_id))
    summary = (data.get("summary") or data.get("details") or "").strip().splitlines()[0][:110] if (
        data.get("summary") or data.get("details")) else ""
    fixed = sorted({
        event["fixed"]
        for affected in data.get("affected", [])
        if _normalize(affected.get("package", {}).get("name", "")) == _normalize(package)
        for rng in affected.get("ranges", [])
        for event in rng.get("events", [])
        if "fixed" in event
    })
    return summary, fixed


def latest_release(package: str) -> str:
    """Return the newest version of ``package`` on PyPI, or "?" when unknown."""
    try:
        return _get_json(PYPI_URL.format(package))["info"]["version"]
    except (urllib.error.URLError, KeyError, ValueError):
        return "?"


def main() -> int:
    """Check the pins and print the affected packages.

    Returns:
        The process exit code (see the module docstring).
    """
    parser = argparse.ArgumentParser(description="Check pinned packages against OSV (https://osv.dev).")
    parser.add_argument("--file", default="constraints.txt", help="name==version list (default: constraints.txt)")
    parser.add_argument("--details", type=int, default=5, help="advisories to describe per package (default 5)")
    args = parser.parse_args()

    pins = read_pins(args.file)
    try:
        found = advisory_ids(pins)
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
        print(f"OSV 에 연결하지 못했습니다: {exc}", file=sys.stderr)
        return 2

    print(f"{len(pins)}개 패키지 확인 — 알려진 취약점이 있는 패키지 {len(found)}개")
    for (name, version), ids in found.items():
        print(f"\n== {name} {version}: 권고 {len(ids)}건 (PyPI 최신: {latest_release(name)})")
        for vuln_id in ids[: max(args.details, 0)]:
            try:
                summary, fixed = advisory_summary(vuln_id, name)
            except (urllib.error.URLError, TimeoutError, ValueError):
                summary, fixed = "(세부 정보를 받지 못함)", []
            print(f"  {vuln_id}: {summary} | 고친 버전: {', '.join(fixed) or '-'}")
        if len(ids) > args.details:
            print(f"  … 외 {len(ids) - args.details}건 (--details 로 더 보기)")
    if found:
        print("\n고친 버전 이상으로 requirements.txt 를 올리고, 이미지를 빌드·테스트한 뒤 constraints.txt 를 다시 뽑으세요.")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
