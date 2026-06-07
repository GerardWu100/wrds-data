"""Download and flatten public SEC Form 13F sample filings.

This script fetches the latest public Form 13F holdings report for a small
fixed list of sample filers, saves the raw XML filing documents, and writes a
flattened CSV of the public holdings rows.

The goal is to show what public 13F data actually looks like, without relying
on WRDS or FactSet-only tables.
"""

from __future__ import annotations

import csv
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "outputs"

# SEC asks automated users to identify themselves. Replace the default with your
# own contact string when you reuse this script more broadly.
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "wrds-data-public-13f-samples/0.1 your-email@example.com",
)

SAMPLE_FILERS = [
    {
        "slug": "berkshire_hathaway",
        "display_name": "Berkshire Hathaway Inc",
        "cik": "1067983",
    }
]

FILING_TYPES = ("13F-HR", "13F-HR/A")
PREVIEW_ROW_COUNT = 25
REQUEST_PAUSE_SECONDS = 0.75


@dataclass(frozen=True)
class FilingReference:
    """Pointer to one SEC filing directory."""

    cik: str
    filing_type: str
    accession_number: str
    primary_document: str
    filing_date: str
    filing_directory_url: str


def sec_request(url: str) -> Request:
    """Build a SEC-compliant HTTP request."""

    return Request(url, headers={"User-Agent": SEC_USER_AGENT})


def fetch_json(url: str) -> dict[str, Any]:
    """Fetch and decode a JSON payload from SEC."""

    time.sleep(REQUEST_PAUSE_SECONDS)
    with urlopen(sec_request(url), timeout=30) as response:
        return json.load(response)


def fetch_text(url: str) -> str:
    """Fetch and decode a text payload from SEC."""

    time.sleep(REQUEST_PAUSE_SECONDS)
    with urlopen(sec_request(url), timeout=30) as response:
        text = response.read().decode("utf-8")

    if text.lstrip().lower().startswith("<!doctype html"):
        raise ValueError(f"SEC returned HTML instead of the expected document for {url}")

    return text


def local_name(tag: str) -> str:
    """Drop XML namespace prefixes so tag matching is simpler."""

    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def first_child_text(parent: ET.Element, child_name: str) -> str:
    """Return the text of the first direct child with the requested local name."""

    for child in parent:
        if local_name(child.tag) == child_name:
            return (child.text or "").strip()
    return ""


def element_text(element: ET.Element | None) -> str:
    """Return stripped text for an optional XML element."""

    if element is None or element.text is None:
        return ""
    return element.text.strip()


def padded_cik(cik: str) -> str:
    """Return the SEC zero-padded CIK string."""

    return f"{int(cik):010d}"


def latest_13f_filing(cik: str) -> FilingReference:
    """Find the latest public 13F holdings report for a filer."""

    submissions_url = f"https://data.sec.gov/submissions/CIK{padded_cik(cik)}.json"
    submissions = fetch_json(submissions_url)

    recent_filings = submissions["filings"]["recent"]
    for form, accession, primary_document, filing_date in zip(
        recent_filings["form"],
        recent_filings["accessionNumber"],
        recent_filings["primaryDocument"],
        recent_filings["filingDate"],
        strict=True,
    ):
        if form in FILING_TYPES:
            accession_nodash = accession.replace("-", "")
            filing_directory_url = (
                f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}"
            )
            return FilingReference(
                cik=cik,
                filing_type=form,
                accession_number=accession,
                primary_document=primary_document,
                filing_date=filing_date,
                filing_directory_url=filing_directory_url,
            )

    raise ValueError(f"No public 13F filing found for CIK {cik}")


def information_table_filename(filing_reference: FilingReference) -> str:
    """Identify the XML file that contains the public 13F holdings table."""

    index_url = f"{filing_reference.filing_directory_url}/index.json"
    directory_index = fetch_json(index_url)

    xml_candidates = [
        item["name"]
        for item in directory_index["directory"]["item"]
        if item["name"].lower().endswith(".xml")
        and item["name"] != filing_reference.primary_document
    ]

    if len(xml_candidates) == 1:
        return xml_candidates[0]

    for filename in xml_candidates:
        xml_url = f"{filing_reference.filing_directory_url}/{filename}"
        root = ET.fromstring(fetch_text(xml_url))
        if local_name(root.tag) == "informationTable":
            return filename

    raise ValueError(
        f"Could not locate information-table XML in {filing_reference.filing_directory_url}"
    )


def parse_information_table(xml_text: str) -> list[dict[str, str]]:
    """Flatten the SEC information-table XML into one row per holding."""

    root = ET.fromstring(xml_text)
    holdings: list[dict[str, str]] = []

    for info_table in root:
        if local_name(info_table.tag) != "infoTable":
            continue

        shares_or_principal = next(
            (child for child in info_table if local_name(child.tag) == "shrsOrPrnAmt"),
            None,
        )
        voting_authority = next(
            (child for child in info_table if local_name(child.tag) == "votingAuthority"),
            None,
        )

        shares_parent = shares_or_principal if shares_or_principal is not None else info_table
        voting_parent = voting_authority if voting_authority is not None else info_table

        holdings.append(
            {
                "name_of_issuer": first_child_text(info_table, "nameOfIssuer"),
                "title_of_class": first_child_text(info_table, "titleOfClass"),
                "cusip": first_child_text(info_table, "cusip"),
                "value": first_child_text(info_table, "value"),
                "ssh_prnamt": first_child_text(shares_parent, "sshPrnamt"),
                "ssh_prnamt_type": first_child_text(shares_parent, "sshPrnamtType"),
                "put_call": first_child_text(info_table, "putCall"),
                "investment_discretion": first_child_text(
                    info_table, "investmentDiscretion"
                ),
                "other_manager": first_child_text(info_table, "otherManager"),
                "voting_authority_sole": first_child_text(voting_parent, "Sole"),
                "voting_authority_shared": first_child_text(voting_parent, "Shared"),
                "voting_authority_none": first_child_text(voting_parent, "None"),
            }
        )

    return holdings


def sort_holdings_by_value(holdings: list[dict[str, str]]) -> list[dict[str, str]]:
    """Sort holdings from largest to smallest reported value."""

    def parse_value(row: dict[str, str]) -> int:
        value_text = row["value"].replace(",", "")
        if not value_text:
            return -1
        return int(value_text)

    return sorted(holdings, key=parse_value, reverse=True)


def write_json(path: Path, payload: Any) -> None:
    """Write formatted JSON to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    """Write CSV rows to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"No rows to write for {path}")

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def export_sample_filer(sample_filer: dict[str, str]) -> None:
    """Download one latest 13F filing and save raw plus flattened artifacts."""

    filing_reference = latest_13f_filing(sample_filer["cik"])
    information_table_file = information_table_filename(filing_reference)
    information_table_url = (
        f"{filing_reference.filing_directory_url}/{information_table_file}"
    )
    information_table_text = fetch_text(information_table_url)

    holdings = parse_information_table(information_table_text)
    sorted_holdings = sort_holdings_by_value(holdings)

    output_dir = OUTPUT_ROOT / sample_filer["slug"]
    metadata = {
        "display_name": sample_filer["display_name"],
        "cik": sample_filer["cik"],
        "filing_type": filing_reference.filing_type,
        "accession_number": filing_reference.accession_number,
        "filing_date": filing_reference.filing_date,
        "filing_directory_url": filing_reference.filing_directory_url,
        "primary_document_name": filing_reference.primary_document,
        "primary_document_url": (
            f"{filing_reference.filing_directory_url}/{filing_reference.primary_document}"
        ),
        "information_table_url": information_table_url,
        "holding_count": len(holdings),
        "filing_manager_name": sample_filer["display_name"],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "filing_metadata.json", metadata)
    (output_dir / "information_table.xml").write_text(
        information_table_text, encoding="utf-8"
    )
    write_csv(output_dir / "holdings_full.csv", sorted_holdings)
    write_csv(
        output_dir / "holdings_preview.csv",
        sorted_holdings[:PREVIEW_ROW_COUNT],
    )


def main() -> None:
    """Download sample 13F filings for all configured filers."""

    for sample_filer in SAMPLE_FILERS:
        export_sample_filer(sample_filer)


if __name__ == "__main__":
    main()
