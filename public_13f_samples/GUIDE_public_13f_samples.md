# Public 13F Samples Guide

## Part 1: Conceptual Explanation

This folder is a public-data companion to the WRDS workspace. Its job is to
show what a real SEC Form 13F filing looks like when fetched directly from
EDGAR, without any WRDS or FactSet enrichment.

The workflow is intentionally narrow:

1. `download_public_13f_samples.py` calls the SEC `submissions` JSON endpoint
   for a fixed list of sample filers.
2. It finds the latest public `13F-HR` or `13F-HR/A` filing for each sample
   filer.
3. It downloads the filing's primary XML document plus the separate holdings
   XML information table URL, then fetches the holdings XML itself.
4. It flattens the public holdings XML into one row per reported holding.
5. It writes raw XML plus parsed CSV files under `outputs/<sample_filer>/`.

This folder exists to answer a different question from the WRDS sample folders:
"What does the real public SEC 13F feed look like before vendor normalization?"

The script keeps the SEC row grain intact. One parsed row in
`holdings_full.csv` is one public 13F holding line, with issuer name, class,
CUSIP, reported value, share/principal amount, investment discretion, optional
other-manager reference, and the three voting-authority columns.

## Part 2: Folder Tree And File Map

```text
public_13f_samples/
├── GUIDE_public_13f_samples.md   -- This folder guide.
├── download_public_13f_samples.py -- Downloads and flattens real SEC 13F filings.
└── outputs/
    └── <sample_filer>/
        ├── filing_metadata.json  -- Filing-level metadata and source URLs.
        ├── information_table.xml -- SEC holdings XML.
        ├── holdings_full.csv     -- Flattened full public holdings table.
        └── holdings_preview.csv  -- Largest reported holdings preview.
```

## Part 3: Code Reference

`download_public_13f_samples.py`

- `SEC_USER_AGENT`: SEC-compliant user-agent string. Can be overridden with the
  `SEC_USER_AGENT` environment variable.
- `SAMPLE_FILERS`: fixed sample filer list.
- `latest_13f_filing()`: finds the most recent public holdings report for a
  filer from the SEC submissions feed.
- `information_table_filename()`: locates the XML file that contains the public
  holdings rows.
- `parse_primary_document()`: extracts filing-level metadata such as report
  period and manager name.
- `parse_information_table()`: flattens one SEC information-table XML into one
  row per holding.
- `sort_holdings_by_value()`: sorts holdings from largest to smallest reported
  value for easier inspection.
- `export_sample_filer()`: writes metadata, raw XML, and flattened CSV outputs
  for one sample filer.
- `main()`: refreshes all configured sample filers in one run.

Run:

```bash
uv run python public_13f_samples/download_public_13f_samples.py
```
