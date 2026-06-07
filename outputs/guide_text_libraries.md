# WRDS People, Governance, Ownership & News Libraries Guide

These libraries are about people, companies, events, and relationships — not
price series. Every row describes a person holding a role, a fund owning a
stock, a news story mentioning a company, or an identifier connecting two
databases.

See `guide_numeric_libraries.md` for prices, spreads, returns, and other
quantitative panels.

---

## How the libraries group together

```
PEOPLE & GOVERNANCE
  boardex_na          who sits on which board, career history, social network
  ciq_pplintel        what executives get paid, component by component
  wrdsapps_plink_...  crosswalk that joins the above two on the same person

INSTITUTIONAL OWNERSHIP  (pick one stack)
  factset_own         quarterly 13F filings — who owns which stocks (easier)
  factset_common      translation dictionary: FactSet IDs → CUSIP/ISIN
    -- or --
  tr_ownership        same 13F filings, broader global coverage (harder)
  tr_common           translation dictionary: TR internal codes → CUSIP/ISIN

NEWS & SENTIMENT
  ravenpack_dj        news articles converted to sentiment scores and event tags

CONTRIBUTED RESEARCH DATASETS
  contrib_general     unrelated one-off academic datasets — pick by topic
```

---

## Quick Triage

**People & Governance**

| Library | Size | What it answers | Start here |
| --- | ---: | --- | --- |
| `boardex_na` | 630 GB | Who sat on which board, when? Who knows whom? | `na_wrds_dir_profile_all`, `na_wrds_individual_networks` |
| `ciq_pplintel` | 37 GB | What was the CEO paid, broken down by component? | `wrds_professional`, `wrds_compensation` |
| `wrdsapps_plink_boardex_ciq` | 0.5 GB | Join BoardEx and Capital IQ records for the same person | `boardex_ciq` |

**Institutional Ownership**

| Library | Size | What it answers | Start here |
| --- | ---: | --- | --- |
| `factset_own` | 299 GB | Which funds owned which stocks each quarter? (US, easier) | `wrds_own_13f` |
| `factset_common` | 49 GB | Translate FactSet IDs to CUSIP/ISIN | `wrds_securities_v3`, `sym_cusip_hist` |
| `tr_ownership` | 466 GB | Same, broader global coverage, harder to use | `ownholddet` |
| `tr_common` | 225 GB | Translate TR internal codes to CUSIP/ISIN | `gsecmapx`, `permcusipdata` |

**News & Sentiment**

| Library | Size | What it answers | Start here |
| --- | ---: | --- | --- |
| `ravenpack_dj` | 296 GB | What was the news sentiment for this company on this date? | `rpa_djpr_equities_YYYY` |

**Contributed Research**

| Library | Size | What it answers | Start here |
| --- | ---: | --- | --- |
| `contrib_general` | 171 GB | Varies — pick by research question | see section below |

---

## People & Governance

### `boardex_na` and `ciq_pplintel` — how they relate

These two libraries cover overlapping people but answer different questions.

| | `boardex_na` | `ciq_pplintel` |
|---|---|---|
| Strongest at | Board directors, governance | C-suite executives, compensation |
| Unique feature | Social network — who has worked with whom | Pay breakdown — salary, bonus, stock awards, options |
| Coverage | Directors, committee members, nonprofit/education affiliations | Top executives and key decision makers |
| Compensation | Basic director remuneration only | Full executive comp by component |
| Network data | Yes — overlapping board seats, shared employers, schools | No |

**They overlap for executives who also sit on the board** — the CEO is almost
always a board member, and some CFOs and other senior executives have board
seats too. For those people you have their pay in Capital IQ and their board
seat and network in BoardEx. `wrdsapps_plink_boardex_ciq` is the table that
joins them together on the same person.

Example research question that needs both: *"Do CEOs with larger professional
networks get paid more?"* — network size is in BoardEx, pay is in Capital IQ,
you need the crosswalk to combine them.

---

### `boardex_na`

**What is this?** The most comprehensive structured database of corporate
governance in North America. It tracks who sat on which board, held which
executive role, when, and at which company — and it models the social network
of professional connections between people. Each time two people overlapped
at the same company, board, school, or nonprofit, that is recorded as a
network edge.

Think of it as a graph: companies and people are nodes; board seats, committee
memberships, employment history, education, and nonprofit affiliations are
edges.

**Main tables:**

**`na_wrds_dir_profile_all`** (4.4 GB) — person master

One row = one person–role at one company. A person with multiple roles has
multiple rows.

Key columns:
- `directorid` — BoardEx unique person ID
- `directorname` — full name (e.g., `David Shaw`)
- `dob` — date of birth
- `gender` — `M` / `F`
- `nationality` — country of citizenship
- `networksize` — number of people in their professional network
- `companyname` — company for this row
- `datestartrole`, `dateendrole` — when this role started and ended
- `rolename` — text role title (e.g., `Senior Advisor`, `CFO/Secretary`)
- `ned` — Non-Executive Director flag (`Yes`/`No`)
- `leadershipteam` — senior leadership team flag
- `companyid` — BoardEx company ID

Example: David Shaw (born 1951, American) was Senior Advisor at New Mountain
Capital from 2004-02-01 to 2007-12-28, and Advisor at Polaris Partners from
2016-01-01 to 2022-12-28.

---

**`na_wrds_company_profile`** (201 MB) — company master

One row = one company.

Key columns:
- `boardid` — BoardEx company ID
- `boardname` — full company name
- `sector` — sector label
- `orgtype` — `Quoted` (public) or `Private`
- `ticker`, `isin` — standard identifiers
- `countryofquote` — country of primary listing
- `mktcapitalisation`, `noemployees`, `revenue`

---

**`na_wrds_individual_networks`** (371 GB) — person-to-person network edges

One row = one connection between two people who overlapped at the same
organization.

Key columns:
- `directorname` — the focal person
- `associationtype` — where they overlapped (e.g., `Listed Org`, `Education`)
- `companyname` — the organization
- `overlapyearstart`, `overlapyearend` — years of overlap
- `roleboardposition` — whether the focal person was on the board (`Brd`) or not
- `associatedroletitle` — the other person's role title

Example: Paul Davis and Ron Henriksen were both directors at PREMD INC during
2008. Paul Davis and Niral Merchant overlapped at Hanfeng Evergreen in 2011
(one was Independent Director, the other CFO/Secretary).

---

**`na_dir_*_assoc` and `na_board_*_assoc` families** (~243 GB combined)

Raw affiliation edge tables linking people to listed companies, unlisted
companies, nonprofits, and educational institutions. These are what
`na_wrds_individual_networks` is built from.

**Compensation tables:** `na_ltip_compensation`, `na_options_compensation`,
`na_dir_standard_remun` — director cash pay, option awards, and long-term
incentive pay. `na_ltip_wealth` and `na_options_wealth` track the estimated
cumulative value of unvested awards and option holdings.

**`na_wrds_company_networks`** (1.65 GB) — company-to-company overlap network

One row = one company-pair overlap derived from shared directors, managers,
and affiliations. Use for board-interlock and network-centrality studies at
the company (not person) level.

**`na_wrds_org_composition`** and **`na_wrds_org_summary`** — board composition
and governance summary tables. Each gives aggregated statistics per company
(board size, gender diversity, independence, average tenure, etc.).

**Profile sub-tables** (under `na_dir_profile_*`): `na_dir_profile_details`,
`na_dir_profile_emp` (employment history per person), `na_dir_profile_education`,
`na_dir_profile_achievements`, `na_dir_profile_other_activ` — richer person
attributes than `na_wrds_dir_profile_all`, but less convenient because each
aspect is a separate table keyed by `directorid`.

**Director announcement table:** `na_board_dir_announcements` — event-level
table of announced director appointments, removals, and retirements.

**Committee membership:** `na_board_dir_committees` — which directors sit on
which committees (audit, compensation, nominating, etc.).

**Helper tables:** `na_wrds_company_names`, `na_wrds_company_dir_names`,
`na_wrds_company_region`, `na_wrds_dir_profile_emp` (WRDS-flattened employment
summary), `na_dir_characteristics`, `na_board_characteristics`

---

### `ciq_pplintel`

**What is this?** Capital IQ People Intelligence: professional roles and
executive compensation linked to companies. The focus is the top-executive
layer — CEOs, CFOs, board members — with detailed pay breakdowns showing
exactly how much of total compensation came from salary vs bonus vs stock
awards vs option grants. The WRDS-flattened tables are the clean starting point.

**Main tables:**

**`wrds_professional`** (8.5 GB) — person-role panel

One row = one person's role at one company at one point in time.

Key columns:
- `companyid` — Capital IQ company ID
- `personid` — Capital IQ person ID
- `companyname`, `personname` — labels
- `profunctionname` — role title (e.g., `Senior Key Executive`, `Member of Advisory Board`)
- `title` — specific title text
- `startyear`, `endyear` — role tenure
- `boardflag` — 1 if this person is a board member
- `keyexecflag`, `topkeyexecflag` — 1 if this is a key/top executive
- `currentflag` — 1 if currently in this role

Example: Kevin Wakefield is Principal at DC Venture Partners. Steve Walker is
an Advisory Board member at the same firm.

---

**`wrds_compensation`** (3.1 GB) — annual compensation panel

One row = one person × one company × one fiscal year.

Key columns:
- `companyid`, `gvkey` — company IDs (gvkey links to Compustat)
- `personid` — person ID
- `companyname`, `personname` — labels
- `year` — fiscal year
- `currencyid` — reporting currency
- `ctype*` columns — each populated `ctype` column is one compensation
  component (salary, bonus, stock awards, option awards, perks, etc.).
  The sampled WRDS table includes `ctype1` through `ctype88`, with some
  numbers skipped. Join `ciqcompensationtype` to decode the column numbers
  to names.

Example: a UK company row in fiscal year 1997 shows many `ctype*` columns,
with the exact component meanings supplied by `ciqcompensationtype`.

---

**`wrds_compensationdetails`** (1.6 GB) — more granular subtype breakdown

Same structure but with `csub` columns for finer-grained compensation
categories within each type.

**Raw tables (use if you need Capital IQ's native schema):**

**`ciqprofessional`** (3.33 GB) — raw professional-role records before the
WRDS flattening layer. Keyed by `proid` (role record ID). Use when you need
fields that WRDS excluded from `wrds_professional`.

**`ciqperson`** (695 MB) — raw person master table with Capital IQ person
attributes (name, gender, date of birth, and active/inactive status).

**`ciqcompensation`** (9.95 GB) — raw compensation facts at the report/event
level, larger and less analysis-friendly than `wrds_compensation`. Contains
one row per compensation report filing rather than one row per person-year.

**`ciqcompensationdetail`** (2.6 GB) — raw compensation component detail with
subtype sequences and filing metadata. More granular than
`wrds_compensationdetails`.

**Helper tables:** `ciqprofunction` (role type decode), `ciqprotoprofunction`,
`ciqcompensationtype` (pay component decode), `ciqcompensationsubtype`,
`ciqcompensationadjustmenttype` (adjustment type), `ciqprofessionalcoverage`,
`compensation_length` (subtype metadata), `ciqpersonbiography` (text
biographies — not a panel)

---

### `wrdsapps_plink_boardex_ciq`

**What is this?** A matching table that lets you join BoardEx and Capital IQ
records for the same person. The problem: BoardEx calls Tim Cook
`directorid=12345`. Capital IQ calls the same person `personid=67890`. Neither
database knows about the other's ID. This table says they are the same person.

**You only need this if you are using both `boardex_na` and `ciq_pplintel`
together.** If you're only using one of them, skip it.

**`boardex_ciq`** (411 MB) — full person-company bridge

One row = one matched person–company link.

Key columns:
- `directorid` — BoardEx person ID
- `personid` — Capital IQ person ID
- `boardid` — BoardEx company ID
- `companyid` — Capital IQ company ID
- `directorname`, `firstname`, `lastname` — name fields from each database
- `isin`, `cikcode` — company identifiers used in the match
- `score` — match confidence (1.0 = high confidence)
- `matchstyle` — how the match was made (e.g., `fullname+isin`)

Example: Satish Pai (BoardEx `directorid=203921`) matched to Capital IQ
`personid=8218581` at ABB Ltd, via full name + ISIN match with score=1.0.

**`boardex_ciq_link`** (89 MB) — person-only bridge (no company context)

Use when you only need to map person IDs and don't need the full company
context.

---

## Institutional Ownership

### What institutional ownership data is

Large fund managers — BlackRock, Vanguard, hedge funds, mutual funds — are
legally required to file a report with the SEC every quarter listing every US
stock they hold and how many shares. This is called a **13F filing**. It is
public — anyone can look it up on the SEC website for free. What you are
paying for at WRDS is 30+ years of those filings, already cleaned,
standardized, and queryable.

**What a row looks like:**
> Fidelity owned 5,000,000 shares of Apple as of March 31 2020, up 200,000
> from the prior quarter.

**Why quant researchers use this:**
- Ownership momentum — do stocks with rising institutional ownership outperform?
- Price pressure — when large funds are forced to sell, does it move the price?
- Corporate governance — do companies with more institutional shareholders behave differently?
- Common ownership — BlackRock owns both United and Delta; does that reduce airline competition?

**The important caveat — data is 45 days stale:**
13F filings are due 45 days after the quarter ends. So by the time you see
that BlackRock bought Apple in Q1, it is already mid-May and the stock has
already moved. This makes ownership data a **slow-moving factor** (useful
over months) not a trading trigger.

**What you should not assume from the sampled 13F-style rows:**
- Positions below the SEC reporting thresholds are not visible
- Short positions are not visible
- The core holdings rows shown here are equity-oriented snapshots, not a full
  picture of every asset class a manager may hold
- Managers below the SEC filing threshold are not included

---

### Pick one stack: FactSet or Thomson Reuters

Both cover the same underlying 13F filings. FactSet is easier to start with
for US research. TR has broader global coverage.

| | `factset_own` | `tr_ownership` |
|---|---|---|
| US 13F coverage | Good | Good |
| Non-US filings | Good | Better — more jurisdictions |
| Names/CUSIPs in main table | Yes — already decoded | No — need `tr_common` to translate |
| Raw panel size | 57 GB (fund detail) | 116 GB (`ownholddet`) |
| Ease of use | Easier | Harder |

---

### `factset_own` + `factset_common`

**`wrds_own_13f`** (29.8 GB) — WRDS-curated 13F holdings

One row = one fund manager × one stock × one quarter-end date.

Key columns:
- `entity_proper_name` — institution name already in plain English (e.g., `Advance Capital Management, Inc.`)
- `entity_type`, `entity_sub_type` — institution type (e.g., `IA` = investment adviser, `MF` = mutual fund)
- `iso_country` — country the institution is based in
- `cusip` — 9-digit CUSIP of the stock (already decoded — no translation needed)
- `proper_name` — stock name in plain English (e.g., `Fiserv, Inc.`)
- `fsym_id` — FactSet internal security ID (needed only if joining to other FactSet tables)
- `report_date` — quarter-end date
- `adj_holding` — shares held, adjusted for splits
- `adj_mv` — market value in USD
- `style` — manager's investment style (e.g., `Generalist`, `Value`, `Growth`)

Example: Advance Capital Management held 53,200 split-adjusted shares of
Fiserv worth \$534,527 as of Q4 2004.

---

**`wrds_own_fund`** (185 GB) — WRDS-curated fund holdings rollup

Same basic structure as `wrds_own_13f` but at the individual fund level with
holder descriptors pre-attached. This is one of the largest tables in the
library. One row = one fund × one security × one report date, with adjusted
holdings, adjusted market value, and a full set of security and fund metadata
already joined in (including exchange, security type, and cap group).

Key columns: `factset_fund_id`, `entity_proper_name`, `iso_country`,
`entity_type`, `fsym_id`, `cusip`, `isin`, `security_name`, `cap_group`,
`mic_exchange_code`, `report_date`, `adj_holding`, `adj_mv`,
`adj_shares_outstanding`, `adj_price`.

---

**`own_fund_detail_eq`** (57.2 GB) — fund-level holdings detail (lean version)

Same fund × security × date structure as `wrds_own_fund` but without the
pre-joined metadata — only `factset_fund_id`, `fsym_id`, `report_date`,
`adj_holding`, `adj_mv`, `reported_holding`, `reported_mv`. Use when you
don't need the descriptor columns and want the smallest possible download.

Example: Fund `000FK2-E` held 6,000 shares of security `GHND41-S` worth
\$207,660 in June 2024.

---

**`own_inst_13f_detail_eq`** (11.7 GB) — Institutional 13F holdings detail

One row = one institution × one security × one report date, sourced from
SEC 13F filings. Leaner than `wrds_own_13f` — only `factset_entity_id`,
`fsym_id`, `report_date`, `adj_holding`, `adj_mv`, `reported_holding`.
Use when you want the raw 13F detail without the pre-joined metadata.

---

**`own_inst_stakes_detail_eq`** (1.12 GB) and **`own_stakes_detail_eq`**
(2.11 GB) — stakes-based holdings detail

Ownership positions reported through channels other than the standard 13F
(e.g., Schedule 13D/G blockholding reports, non-US statutory filings).
Use when you need to capture large-block positions not visible in the 13F.

**`own_uksr_detail_eq`** (2.47 GB) and **`own_uksr_cust_detail_eq`**
(82 MB) — UK shareholder register and custodial holder detail tables

Holdings derived from UK statutory shareholder registers and custodian
reports. Relevant for UK equity ownership research.

**`own_insider_trans_eq`** (3.77 GB) — insider and stakeholder transactions

One row = one insider trade event for an equity security. Covers executives,
directors, and major shareholders buying or selling their own company's
shares. Not the same as fund holdings — this is the FactSet equivalent of
SEC Forms 4 and 144.

**`wrds_holdings_by_firm_msci`** and **`wrds_holdings_by_security_msci`** —
MSCI-universe holdings views

WRDS-curated holdings tables pre-filtered to the MSCI index universe. Use
these when your research universe is MSCI-defined and you want to skip the
filtering step.

---

**`factset_common`** — translation dictionary (only needed beyond basic US work)

For basic US 13F research `wrds_own_13f` already includes CUSIP and institution
names, so you may not need `factset_common` at all. Download individual tables
only when you need to join on `fsym_id` to other FactSet products or need
historically accurate identifier changes.

**`wrds_securities_v3`** (2.1 GB) — best first choice

Pre-joined table with `fsym_id`, ticker, CUSIP, ISIN, SEDOL, country, exchange,
and security type in one place. Saves assembling from multiple raw tables.

Example: the sampled row for `fsym_id=B00011-S` is a BNP Paribas warrant with
CUSIP `N142AN806` and no ISIN populated in that row.

**`sym_cusip_hist`** (2.3 GB) — `fsym_id` → CUSIP with validity date range

One row = one (fsym_id, CUSIP) pair valid from `start_date` to `end_date`.
Use when you need historically accurate CUSIP matching (e.g., a security had
a different CUSIP before a corporate action).

Example: `fsym_id=B00004-S` mapped to CUSIP `D999DA144` from 2024-02-07
to 2024-05-04.

**`sym_isin_hist`** (37 MB) — `fsym_id` → ISIN with validity date range

Example: `fsym_id=B00121-S` → ISIN `US31847L2043` valid 1998-07-16 to 2003-06-26.

**`sym_ticker_exchange_hist`** (2.8 GB) — `fsym_id` → exchange ticker with date range

Example: `fsym_id=B00001-L` → ticker `DE000TT91W34-MUNC` on Munich exchange
from 2022-08-18.

**`sym_sec_entity`** — `fsym_id` → `factset_entity_id`

Tiny table linking each security to its parent entity (company). Use to go
from a security holding up to the company level for name lookups.

Example: security `B00011-S` belongs to entity `06JN4Y-E`.

**`sym_entity`** (1.9 GB) — entity name master

One row = one entity. Columns: `factset_entity_id`, `entity_proper_name`,
`iso_country`, `entity_type` (e.g., `SUB` = subsidiary, `EXT` = external).
Download when you need institution name and country that isn't already in
`wrds_own_13f`.

**`sym_coverage`** (12 GB) — full security universe master. Download only if
you need to filter by security type, listing flags, or build a custom coverage
set. Not needed for most holdings research.

---

### `tr_ownership` + `tr_common`

**`ownholddet`** (116 GB) — the core holdings table

One row = one institution × one stock × one quarter-end date.

Key columns:
- `ownercode` — TR's internal institution ID (opaque integer — meaningless until you join to `tr_common`)
- `securitycode` — TR's internal stock ID (same — meaningless until translated to CUSIP via `tr_common`)
- `reportdate` — quarter-end date
- `sharesheld` — shares held
- `valueheld` — reported position value
- `shareschg` — change in shares vs prior report (positive = bought, negative = sold)
- `newposition` — 1 if brand-new position this quarter
- `pctshareoutstanding` — this position as a fraction of total shares outstanding
- `priorreportdate` — date of the institution's previous filing

Example: Owner `2200` held 11,500 shares of security `20055` at 1998-12-31,
with `valueheld=682813` in the sampled row. The matching `tr_common`
translation row is not present in the tiny snapshot, so decoding that
`securitycode` requires the full reference tables.

---

**`ownholdcf`** (93 GB) — carry-forward companion

Same structure as `ownholddet` but adds `nextreportdate`. Use when building
a monthly panel — filings are quarterly, so you carry each position forward
until the next filing to know what the institution held in between.

**`ownsecdata`** (23.85 GB) — numeric security-level history

One row = one security × one date. Key columns: `securitycode`, `pricedate`,
`shareprice`, `shareout` (shares outstanding), `tradctrcode`, `exchcode`,
`marketcap`, `feedtype`. Use as an alternative to `ownsecfdata` when you need
a longer history or different set of pricing fields.

**`ownsecfdata`** (5.3 GB) — historical pricing and shares-outstanding table

One row = one stock × one date. Use to convert `sharesheld` to a dollar value
when `valueheld` is missing or in a foreign currency.

**`wrds_ownholddet_type1`** (61.7 GB), **`wrds_ownholddet_type2`**
(55.2 GB), and **`wrds_ownholddet_type3`** (94.9 GB) — WRDS-curated
holdings splits

Same schema as `ownholddet` (including CUSIP, SEDOL, and owner name already
attached) but split by `hldgtype` (holding type code). Type 1, 2, and 3
correspond to different reporting channels or ownership subtypes. Use these
when you only care about one holding-type subgroup — they are smaller and
faster to query than filtering the full `ownholddet`.

**`wrds_ownsecfdata`** (11.8 GB) — WRDS-enriched security data

Full security master with pricing enrichment already joined: `securitycode`,
CUSIP, SEDOL, ISIN, ticker, security name, sector, exchange, stop date,
issuer code, active flag, plus date-specific price and shares outstanding.
More convenient than rebuilding the same enrichment from the raw `ownsecfdata`
and `ownsecinfo` tables separately.

**`owninsdata`** (854 MB) — insider transactions (global)

One row = one insider trade (CEO, director, etc. buying or selling their own
company's stock). This is not institutional fund holdings — it is the
executives themselves trading their own company's shares.

**`owninsasiadata`** (567 MB) — insider transactions, Asia-Pacific

Same structure as `owninsdata` but specifically for Asia-Pacific insider
activity.

---

**`tr_common`** — translation dictionary (always needed with `tr_ownership`)

Unlike FactSet, TR's holdings table stores only opaque internal codes.
You always need `tr_common` to decode them.

```
ownholddet
securitycode = 20055
      ↓
  tr_common
  20055 → CUSIP 337738108
      ↓
  Compustat / CRSP / broker
  "that's Fiserv Inc, ticker FISV"
```

**`gsecmapx`** — `seccode` → CUSIP or SEDOL with date range

One row = one (TR seccode, vendor type, vendor code) mapping.
`ventype=1` is CUSIP, `ventype=2` is SEDOL. This is the fastest path when
you already have a `seccode` from `ownholddet`.

Example: `seccode=2` maps to CUSIP via ventype=1 starting 1960-01-01, and
to SEDOL=3401 via ventype=2 starting 1987-01-15.

**`permcusipdata`** — `instrpermid` → CUSIP with validity date range

One row = one (TR instrument ID, CUSIP) pair valid from `startdate` to `enddate`.

Example: `instrpermid=281281` maps to CUSIP `92837G100` from 2017-04-01
onward, and previously to `989834106` from 1994-08-27 to 2012-06-26. Use
the date range to avoid attaching the wrong CUSIP to a historical holding.

**`permisindata`** — same structure, maps `instrpermid` → ISIN

Example: `instrpermid=281281` → ISIN `US92837G1004` from 2017.

**`permricdata`** — `quotepermid` → Reuters Instrument Code (RIC)

Example: `quotepermid=36808` → RIC `US30DCP11=PYNY`. Use when joining to
data sourced from Bloomberg or Refinitiv terminals that use RIC codes.

**`permsecmapx`** — maps `seccode` to Reuters permanent IDs (`entpermid`)
by `enttype`, with date ranges. Use when you need to move from a TR
security code into the Reuters permanent-ID family.

**Bigger reference tables (rarely needed directly):**
- `permquoteinfo` (38 GB) — one row per TR quote-level permanent ID with
  asset-class and listing metadata. Only needed to filter or describe the
  security universe.
- `perminstrinfo` (26 GB), `permorginfo` (4.3 GB) — same for instrument and
  organization levels.

---

## News & Sentiment

### `ravenpack_dj`

**What is this?** RavenPack reads news articles — Dow Jones Newswires, Wall
Street Journal, press releases — and turns them into structured database rows.
For every story, it identifies which companies are mentioned, scores how
central each company is to the story, classifies what type of event it is,
and assigns a sentiment score.

The result is that instead of reading thousands of articles yourself, you
query a table: *"what was the news sentiment for Apple on this date?"*

**How RavenPack turns text into numbers:**

Step 1 — Entity recognition: they match company names, aliases, and tickers
to a master entity database. "Apple", "AAPL", "Apple Inc." all resolve to
the same entity ID. The `relevance` score (0–100) measures how central the
company is to the story — 100 means the whole story is about that company,
20 means it was mentioned once in passing.

Step 2 — Event classification and sentiment: RavenPack uses thousands of
hand-crafted rules that pattern-match against the text. "beats estimates" →
event type: Earnings Above Expectations, sentiment: positive. "files for
bankruptcy" → event type: Bankruptcy Filing, sentiment: negative. The
sentiment score is **tied to the specific event type**, not just the tone of
the words — an earnings beat gets a positive score because earnings beats
are historically associated with positive price reactions. This is the key
distinction from a simple positive/negative word count.

**Source coverage:** The `source_name` column in each row tells you which
outlet the story came from. The full article text is not in the database —
only the headline and the structured output.

**Can you build this yourself?** Yes, if you have a live news feed. The
pipeline is: entity recognition (spaCy + ticker database) → sentiment scoring
(FinBERT, a finance-specific BERT model, is free and open source) → event
classification (fine-tuned LLM or rule-based). The main thing you lose is
history — RavenPack goes back to 2000, your pipeline only starts from when
you build it. WRDS RavenPack is most useful for **backtesting** a news
sentiment signal before deploying it live.

**Main tables:**

**`rpa_djpr_equities_YYYY`** (~116 GB across 27 annual tables)

One row = one entity mention in one news story.

Key columns:
- `timestamp_utc` — exact UTC timestamp of the story
- `rp_story_id` — unique story ID (one story can produce multiple rows if multiple companies are mentioned)
- `rp_entity_id` — RavenPack entity ID
- `entity_name` — company name (e.g., `Jain Irrigation Systems Ltd.`)
- `country_code` — 2-letter country code
- `relevance` — how central this company is to the story (0–100). Filter to 90+ for stories where the company is the main subject.
- `event_sentiment_score` — sentiment score for this specific event
- `css` — composite sentiment score across all events in the story
- `topic`, `group`, `type`, `sub_type` — event classification hierarchy (e.g., Earnings → Results → Earnings Above Expectations)
- `event_text` — short plain-text event description
- `headline` — full headline text
- `source_name` — news source (e.g., `Dow Jones Newswires`, `BSE News`)

Example: the sampled 2024 row is a Dow Jones Newswires press release about
Jain Irrigation Systems published at 2024-01-01 08:36:16 UTC, with
`relevance=90` and `css=-0.06`. The row's `rp_story_event_count=2` says the
story carries two tagged events.

Note: one news story with 10 company mentions creates 10 rows — one per
entity. Always filter by `relevance >= 90` to keep only stories where the
company is the main subject, not just mentioned in passing.

---

**`rpa_djpr_global_macro_YYYY`** (~180 GB across 27 annual tables)

Same structure as the equities table but for macro entities — countries,
central banks, commodities, macro indicators. Use for country-level sentiment,
macro event studies, and risk event modeling.

---

## Contributed Research Datasets

### `contrib_general`

A collection of independent research datasets contributed by academics.
There is no shared schema. Each table is a standalone finished dataset —
download the ones relevant to your research question.

**Governance and ownership structure**

**`classified_boards`** (9.8 MB) — does the firm have a staggered board?

One row = one firm (gvkey) × one year. Key column: `cbi` (1 = classified board).
A classified board means directors serve staggered 3-year terms, so an acquirer
can't replace the whole board in a single proxy vote. Used in anti-takeover and
governance research.

Example: gvkey `001004` had `cbi=1` in fiscal years 1991 and 1992.

**`blocksv`** — blockholders (>5% stake) per company per year

One row = one blockholder × one company × one year. Key columns:
`blockholder_name`, `company_name`, `position` (% stake held), `block_type`,
`files_13f` (1 if the blockholder also files 13F).

Example: T. Rowe Price held a 6.4% block in K-Tron International in 1995,
rising to 7.9% in 1996.

**`ceo_turnover`** — forced CEO departures

One row = one forced CEO departure. Key columns: `gvkey`, `year`,
`exec_lname`, `exec_fname`, `forced` (1 = forced out), `anndate`.

Example: Gert Munthe forced out of gvkey `001034` in September 1999.
Donald Carty forced out of gvkey `001045` in April 2003.

**`common_own_firm`** (170 GB) — how much do two firms share the same institutional owners?

One row = one pair of companies (gvkey_a, gvkey_b) × one year. Key columns:
`ggl_linear`, `ggl_full_attn`, `ggl_concave`, `ggl_convex`, `ggl_fitted` —
five variants of the Azar-Schmalz-Tecu common-ownership index. Higher = more
institutional shareholders in common. Used in antitrust research ("does common
ownership soften competition?") and governance coordination studies.

Example: gvkeys `1001` and `1003` had zero common ownership in 1983–1984.

---

**Text analytics and NLP**

**`as_firm_risks`** (38.7 MB) — risk topic exposure from 10-K filings

One row = one firm (CIK) × one fiscal year. Reads each firm's 10-K Item 1A
"Risk Factors" section and scores how much of the language covers eight
categories.

Key columns:
- `cik`, `fyear`, `filing_date`
- `item_1a_word_count` — total words in the risk section
- `technology`, `operations`, `finance`, `legal`, `management`, `marketing`,
  `accounting`, `international` — word count per topic category
- `*_probability` — ML probability score (0–1) for each category
- `*_classification` — binary flag (1 = category is significant)

Example: CIK `20` in fiscal year 2006 had 1,622 words in Item 1A with
operations scoring highest probability (0.43), finance second (0.33).

**`arc`** (127 MB) — how complex/opaque is a firm's financial report?

One row = one SEC filing (10-Q or 10-K). Measures accounting complexity by
counting unique monetary line items, XBRL tags, and non-standard extensions.

Key columns: `adsh` (SEC accession number), `cik`, `fiscal_period_end`,
`arc` (overall score), `arc_face`/`arc_notes`/`arc_is`/`arc_bs`/`arc_cf`
(complexity by statement section), `arc_extensions` (number of non-standard
XBRL tags), `arc_pct_extended` (fraction of facts using non-standard tags —
high = harder to parse automatically).

Example: CIK `1750` Q3 2010 filing scored `arc=99`, used 232 numeric facts,
14 XBRL extensions, 14.1% non-standard tags.

---

**Risk measures and factors**

**`better_beta`** (254 MB) — improved CAPM beta estimates

One row = one stock (CRSP `permno`) × one month-end date. Key columns:
- `bswa32` — Bayesian shrinkage beta using 32-month rolling window, shrunk
  toward 1.0 for thinly-traded stocks. More stable than raw OLS beta.
- `sd0111` — alternative beta variant

Use instead of a raw OLS beta when you need a less noisy market-risk estimate.

**`marginal_tax`** (11.5 MB) — firm-year marginal corporate tax rate

One row = one firm (gvkey) × one year. The marginal tax rate is simulated
from a tax-loss carryforward model — a better proxy for the actual tax benefit
of debt than the average effective tax rate from the income statement.

**`factors*` tables** — academic factor return series

Daily and monthly return series for standard factor portfolios (market, size,
value, momentum, etc.) in multiple currencies. Small and ready to use as
benchmark returns.

---

**Linkage tables**

**`dealscan_link_comp`** — DealScan loan deals → Compustat companies

One row = one (DealScan lender/borrower, Compustat gvkey) match with date
ranges. Use when you want to connect syndicated loan data to Compustat
fundamentals.

Example: Morgan Stanley Group (`lcoid=257`) linked to Compustat gvkey
`012124` valid 1987-05-25 to 1998-12-15.

---

**Helper tables:** `_states_` (US state FIPS codes), `cik_types` (SEC filer
category codes — e.g., whether a CIK is an investment company or operating firm)
