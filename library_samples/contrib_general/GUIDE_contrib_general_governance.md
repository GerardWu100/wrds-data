# Contrib General — Governance & Corporate Events

11 tables covering corporate governance structures, ownership, management
events, filing text analysis, and identifier crosswalks. These are
event-driven or flag-based datasets — each row records something that happened
to a firm (a CEO was fired, a board structure changed, an investor crossed 5%)
or classifies an entity.

See [GUIDE_contrib_general.md](GUIDE_contrib_general.md) for the full table
index.

---

## Part 1: Table Descriptions

### Corporate Governance Flags

**`classified_boards.csv` — Staggered board of directors**

A "classified board" (also called a staggered board) is one where directors
serve staggered 3-year terms — only one-third of the board faces election each
year. This makes hostile takeovers much harder: an acquirer cannot replace the
entire board in a single proxy vote. Whether a firm has a classified board is
one of the most studied governance variables in corporate finance.

| Column | Meaning |
|---|---|
| `gvkey` | Compustat firm identifier |
| `datadate` | Fiscal year-end date |
| `fyear` | Fiscal year |
| `cbi` | Classified board per IRRC/ISS Governance (1 = yes, 0 = no) |
| `cbv` | Classified board per alternative ISS source |
| `havemf` | Whether mutual fund ownership data is available for that year |

Example — firm 001004 has maintained a classified board continuously since 1991:

```
gvkey   datadate    fyear  cbi  cbv  havemf
001004  1992-05-31  1991    1    1     0
001004  1993-05-31  1992    1    1     0
001004  2024-05-31  2023    1    1    (still classified)
```

Firm 001009 shows `cbi=0, cbv=0` every year — it has never had a classified
board.

---

### Management Events

**`ceo_turnover.csv` — Forced CEO departures**

Each row is one confirmed *forced* CEO departure at a US public company. A
departure is "forced" when the CEO did not leave voluntarily — not a planned
retirement, not a normal succession. The dataset is commonly used in research
on board monitoring and managerial accountability.

| Column | Meaning |
|---|---|
| `gvkey` | Compustat firm identifier |
| `year` | Fiscal year the turnover occurred |
| `exec_lname`, `exec_fname` | CEO's last and first name |
| `forced` | Always 1 in this table (filtered to forced departures only) |
| `anndate` | Date the departure was publicly announced |
| `execid` | ExecuComp executive identifier |

Example rows:

```
gvkey   year  exec_lname   exec_fname  anndate
001164  2001  Ebbers       Bernard     2002-04-29   (WorldCom)
001690  1993  Sculley      John        1993-06-19   (Apple)
001690  1997  Amelio       Gilbert     1997-07-09   (Apple)
002285  2019  Muilenburg   Dennis      2019-12-23   (Boeing)
```

Note that `year` is the fiscal year when the firing occurred, while `anndate`
is the actual public announcement date — often a few months into the following
calendar year.

---

### Ownership

**`blocksv.csv` — Blockholders (investors owning 5% or more)**

Tracks every institutional investor or individual that crosses the 5%
ownership threshold at any US public company, extracted from SEC 13D/13G
filings. Any investor crossing 5% is required to file with the SEC within 10
days, which is what populates this dataset.

| Column | Meaning |
|---|---|
| `blockholder_cik` | SEC CIK of the large shareholder |
| `company_cik` | SEC CIK of the company being held |
| `position` | Ownership stake (%) |
| `files_13f` | 1 if the blockholder also files a quarterly 13F institutional ownership report |
| `blockholder_name` | Name of the blockholder |
| `company_name` | Name of the held company |
| `block_type` | institution / individual / other |
| `year` | Year of the observation |

Example — major shareholders in K-Tron International over time:

```
blockholder_name                  company_name          position  year
PRICE T ROWE ASSOCIATES INC /MD/  K TRON INTERNATIONAL    6.4%   1995
BABSON DAVID L & CO INC           K TRON INTERNATIONAL   10.7%   1997
DIMENSIONAL FUND ADVISORS INC     K TRON INTERNATIONAL    5.0%   1998
CLOUES EDWARD B II (individual)   K TRON INTERNATIONAL    9.3%   2001
```

**`common_own_firm.csv` — Common ownership between firm pairs**

Common ownership occurs when the same investor (e.g., BlackRock, Vanguard)
simultaneously holds significant stakes in two competing firms. Economists
argue this can dampen competitive incentives: if a single shareholder profits
from both Company A and Company B, it has weaker incentives to push them to
compete aggressively on price.

Each row measures the degree of common ownership between one specific pair of
firms in one year.

| Column | Meaning |
|---|---|
| `year` | Year |
| `gvkey_a`, `gvkey_b` | The two firms in the pair |
| `ggl_linear` | Linear common-ownership index (Azar et al. KHJV measure) |
| `ggl_full_attn`, `ggl_concave`, `ggl_convex`, `ggl_fitted` | Alternative functional forms of the same concept |

A value of 0.0 means the two firms share no common institutional owners.
Larger values indicate more overlap. Example:

```
year  gvkey_a  gvkey_b  ggl_linear   ggl_full_attn
1983  1001     1024     0.149        1868.9
1983  1001     1038     0.117        1465.0
1983  1001     1003     0.001        107.9
```

`ggl_full_attn` can be very large because it uses a full-attention weighting
function; `ggl_linear` and `ggl_fitted` are more interpretable for most uses.

**`common_own_industry.csv` — Common ownership at the industry level**

Same concept as `common_own_firm` but aggregated to the 3-digit SIC industry
level. Instead of a specific firm pair, each row captures average common
ownership pressure across all firm pairs within an industry-year.

| Column | Meaning |
|---|---|
| `three_digit_sic` | 3-digit SIC industry code |
| `ggl_linear` | Average linear common-ownership index across all firm pairs in the industry |
| Other `_ind` columns | Industry-level versions of the alternative measures |

Example: SIC 10 (Metal Mining) showed rising common ownership from 1991 to
2012 as passive index funds grew. SIC 20 (Food Products) shows more sporadic
levels, consistent with a less concentrated investor base.

---

### Text Analysis of SEC Filings

**`as_firm_risks.csv` — 10-K Risk Factor NLP Scores**

Each US public company's annual report (10-K) contains an "Item 1A: Risk
Factors" section listing the firm's material risks. This dataset applies
machine learning to measure how much of each firm's disclosed risks falls into
eight risk categories. The model was trained on hand-labeled filings, then
applied to the full universe of 10-K filers.

| Column | Meaning |
|---|---|
| `cik` | SEC CIK |
| `fyear` | Fiscal year |
| `filing_date` | Date the 10-K was filed with the SEC |
| `item_1a_word_count` | Total word count of the Risk Factors section |
| `[category]` | Word count attributed to that risk category |
| `[category]_probability` | Model's estimated probability the firm has elevated risk in that category |
| `[category]_classification` | Binary flag: 1 if the model classifies the firm as high-risk in that category |

The eight categories: `accounting`, `finance`, `international`, `legal`,
`management`, `marketing`, `operations`, `technology`.

Example — company 1750 from 2006 to 2008:

```
cik   fyear  item_1a_word_count  finance  finance_prob  international  int_prob
1750  2006       25,584           567       0.44            49          0.024
1750  2007       26,907           605       0.45            43          0.035
1750  2008       29,126           698       0.46            41          0.028
```

Finance risk dominates (probability ≈ 0.46). International risk is mentioned
but at low probability (≈ 0.03). The section grew 14% in word count over two
years as the 2008 financial crisis approached.

**`arc.csv` — XBRL Accounting Reporting Complexity**

All US public companies must file financial statements in XBRL format with the
SEC. XBRL is a tagging standard where each reported number gets a standardized
label. The ARC score measures how complex a filing is: how many data items,
monetary figures, and custom (non-standard) extensions the company used.
Companies with many custom tags have idiosyncratic accounting that is harder to
compare across firms and is associated with lower financial reporting quality.

| Column | Meaning |
|---|---|
| `adsh` | SEC accession number — the unique ID for each individual filing |
| `cik` | SEC CIK of the filer |
| `fiscal_period_end` | End date of the fiscal period reported |
| `arc` | Total ARC score (overall filing complexity) |
| `arc_all_nums` | Total number of numeric data points reported |
| `arc_all_monetary` | Number of monetary (dollar-denominated) values |
| `arc_face` | Complexity in the face of the financial statements |
| `arc_notes` | Complexity in the footnotes |
| `arc_pct_extended` | Fraction of tags that are custom extensions (not standard XBRL taxonomy) |

Example — company 1750 (AAR Corp) across several filings:

```
fiscal_period_end  form   arc   arc_all_nums  arc_notes  arc_pct_extended
2010-08-31         10-Q    99      232            0         14%
2012-05-31         10-K   392     1353          274         15%
2013-08-31         10-Q   151      355           49         12%
```

Annual 10-K filings are more complex than quarterly 10-Q filings (higher `arc`,
more footnote items). A higher `arc_pct_extended` means the firm uses more
non-standard accounting tags, making automated comparisons harder.

---

### Identifier Crosswalks

These three tables exist to connect one database's identifiers to another's.
They have no analytical content on their own but are essential for joining
governance or loan data to financial statement data.

**`cik_types.csv` — SEC filer classification**

Maps each SEC CIK to a two-level entity type. Useful for filtering out hedge
funds or index funds when you only want operating companies, or vice versa.

| Column | Meaning |
|---|---|
| `cik` | SEC CIK (zero-padded 10-digit string) |
| `name` | Company name as registered with the SEC |
| `type2` | `fin` = financial firm, `nonfin` = non-financial firm |
| `type4` | `inst` = institutional investor, `hf` = hedge fund, `indiv` = individual, `other` = other |

Example:

```
cik          name                          type2   type4
0000002110   ACORN INVESTMENT TRUST        fin     inst
0000002230   ADAMS EXPRESS CO              fin     hf
0000001800   ABBOTT LABORATORIES           nonfin  other
0000007711   ASHTON HARRIS J               nonfin  indiv
```

**`dealscan_link_bs.csv` — DealScan lender → Bankscope/Orbis**

DealScan is a loan-level database of corporate syndicated loans; Bankscope
(now Orbis Bank Focus) is a database of bank financial statements. This table
maps each DealScan lender (`lcoid`) to its Bankscope identifier (`bvdidnum`),
with date ranges to handle bank mergers and renamings.

| Column | Meaning |
|---|---|
| `lcoid` | DealScan's internal lender ID |
| `lender` | Lender name as it appears in DealScan |
| `ds_start`, `ds_end` | Date range during which this DealScan record is active |
| `bvdidnum` | Bankscope/Orbis Bureau van Dijk identifier |
| `bs_start`, `bs_end` | Date range during which this Bankscope record applies |
| `note` | Explanation of any merger or acquisition |

Example — Bank of Tokyo-Mitsubishi's merger with UFJ:

```
lcoid   lender                              bvdidnum  bs_start    note
79984   Bank of Tokyo-Mitsubishi Group      JP44131   1999-03-31
79984   Bank of Tokyo-Mitsubishi Group      JP18488   2005-04-01  merger with UFJ on 20060101
111070  Bank of Tokyo-Mitsubishi UFJ Ltd    JP18488   2006-08-08
```

After the 2006 merger, all loan originations by the successor entity map to
the new Bankscope ID (JP18488).

**`dealscan_link_comp.csv` — DealScan lender → Compustat**

Same idea but maps DealScan lender IDs to Compustat `gvkey` identifiers.

| Column | Meaning |
|---|---|
| `lcoid` | DealScan lender ID |
| `lender` | Lender name |
| `ds_start`, `ds_end` | Active range in DealScan |
| `comp_start`, `comp_end` | Date range for the matched Compustat entity |
| `gvkey` | Compustat firm identifier |
| `note` | Merger/acquisition context |

Example — Wells Fargo's merger with Norwest:

```
lcoid  lender       comp_start  comp_end    gvkey   note
6123   Wells Fargo  1962-03-31  1998-09-30  011359
6123   Wells Fargo  1998-10-01  2019-12-31  008007  merged with Norwest in 1998
```

Pre-1998 loans link to the old Wells Fargo gvkey; post-1998 they link to the
Norwest entity that took over the Wells Fargo name.

**`_states_.csv` — FIPS state code lookup**

A 59-row reference table mapping each US state's numeric FIPS code to its
name. Used to decode the first two digits of `fips_county` in geographic
datasets.

```
code  state
1     Alabama
6     California
36    New York
48    Texas
72    Puerto Rico
```

---

## Part 2: Folder Tree and File Map

```
contrib_general/
├── GUIDE_contrib_general_governance.md  -- This guide.
│
├── --- Governance flags ---
├── classified_boards.csv         -- Whether a firm has a staggered board, per year.
│
├── --- Management events ---
├── ceo_turnover.csv              -- Forced CEO departures (US public firms, 1990s–present).
│
├── --- Ownership ---
├── blocksv.csv                   -- Investors holding ≥5% of a firm's shares, per year.
├── common_own_firm.csv           -- Common-ownership index for each firm pair.
├── common_own_industry.csv       -- Common-ownership index aggregated to 3-digit SIC.
│
├── --- Text analysis of SEC filings ---
├── as_firm_risks.csv             -- NLP risk category scores from 10-K Item 1A.
├── arc.csv                       -- XBRL filing complexity scores, per SEC filing.
│
└── --- Identifier crosswalks ---
    ├── cik_types.csv             -- Classifies each SEC CIK as fin/nonfin and sub-type.
    ├── dealscan_link_bs.csv      -- DealScan lender ID → Bankscope/Orbis ID.
    ├── dealscan_link_comp.csv    -- DealScan lender ID → Compustat gvkey.
    └── _states_.csv              -- FIPS numeric code → US state name.
```

---

## Part 3: Code Reference

**Generated by:** `uv run python -m library_samples.export_small_samples`

**Key identifiers in this group:**

| Identifier | What it is | Tables |
|---|---|---|
| `gvkey` | Compustat firm ID (6-digit string) | classified_boards, ceo_turnover, common_own_firm, common_own_industry, dealscan_link_comp |
| `cik` | SEC Central Index Key | arc, as_firm_risks, blocksv, cik_types |
| `lcoid` | DealScan internal lender ID | dealscan_link_bs, dealscan_link_comp |
