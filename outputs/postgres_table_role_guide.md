# WRDS Table Role Guide

## Scope

This guide is a practical interpretation layer on top of the WRDS catalog
exports. It answers four questions:

1. What is each sampled library actually about?
2. Which tables are the main research tables?
3. Which tables are helper, bridge, or staging tables?
4. Where should you start if you want usable data quickly?

Evidence used for this refresh:

- `outputs/postgres_libraries.csv` for official library descriptions and library
  size summaries
- `outputs/postgres_tables.csv` for official table comments, estimated row
  counts, sizes, and column counts
- `outputs/postgres_columns.csv` for official column inventories
- `library_samples/<library>/<table>.csv` for 100-row live samples from each
  sampled table
- live WRDS PostgreSQL metadata queried on 2026-03-16 to confirm current table
  counts and total schema sizes

Important correctness update: the old guide was written against much thinner
samples and still described "10-row" examples. The current sample exporter is
configured for 100 rows, and the sampled library area now covers 20 WRDS
library folders plus the `__pycache__` directory.

For every sampled WRDS library below, the live WRDS table count matched the
number of CSV sample files in `library_samples/<library>/` on 2026-03-16.

## Classification Rules

- Main table: the table you would normally model on, backtest on, aggregate
  from, or treat as the research panel of record.
- Helper table: a lookup, identifier map, code table, metadata table,
  descriptive dimension, or small supporting table used to decode or enrich the
  main data.
- Bridge table: a crosswalk whose main job is connecting two libraries or
  identifier systems.
- Staging table: a cleaned or transformed upstream table that supports a more
  analysis-ready table in the same library.
- Mixed library: no single table is "the" center of the library; different
  tables support different research questions.

Naming rules that hold up well across this sample set:

- `*_map`, `*_code`, `*_type`, `*_lookup`, `*_names`, `*_info`, `*_ref`,
  `*_coverage`, `*_metadata`, `*_features` usually means helper.
- Yearly shards such as `cds2025`, `opprcd2024`, `rpa_djpr_equities_2025` are
  usually main fact tables.
- `wrds_*` often means a WRDS-curated rollup, flattened view, or bridge. These
  are often better starting points than the raw vendor tables.
- In TRACE-like libraries, `masterfile` usually means helper, `trace*` usually
  means raw trade facts, and `trade_summary*` usually means derived aggregate
  facts.
- In ownership libraries, `*_detail_*`, `ownholddet`, and transaction tables
  are usually main, while `ent`, `sec`, `map`, and `code` tables are helpers.

## Quick Triage

| Library | Live tables / sample CSVs | Approx size | Overall role | Start here |
| --- | ---: | ---: | --- | --- |
| `boardex_na` | 39 / 39 | 630 GB | Main + helper | `na_wrds_dir_profile_all`, `na_wrds_company_profile`, `na_wrds_individual_networks` |
| `ciq_pplintel` | 16 / 16 | 37 GB | Main + helper | `wrds_professional`, `wrds_compensation`, `wrds_compensationdetails` |
| `ciq_ratings` | 43 / 43 | 16 GB | Main + helper | `wrds_srating`, `wrds_irating`, `wrds_erating`, `ratings_ids` |
| `comp_global_daily` | 125 / 125 | 128 GB | Mixed main + helper | `g_secd`, `g_sec_dprc`, `g_funda`, `g_fundq`, `g_secm` |
| `contrib_general` | 20 / 20 | 171 GB | Mixed library | Start from the specific research table comment |
| `contrib_global_factor` | 4 / 4 | 76 GB | Main + helper | `global_factor`, `ctff_daily_ret`, `ctff_chars` |
| `factset_common` | 193 / 193 | 49 GB | Helper library | `sym_coverage`, `sym_entity`, `sym_sec_entity`, `wrds_securities_v3` |
| `factset_own` | 34 / 34 | 299 GB | Main + helper | `wrds_own_13f`, `wrds_own_fund`, `own_fund_detail_eq`, `own_inst_13f_detail_eq` |
| `fisd_fisd` | 59 / 59 | 71 GB | Main + helper | `fisd_mergedissue`, `fisd_tsales`, `fisd_ratings` |
| `markit_cds` | 28 / 28 | 341 GB | Main + helper | `cdsYYYY`, then `cdslookup` |
| `msrb_all` | 3 / 3 | 79 GB | Main + helper | `msrb`, then `msrb_lookup` |
| `optionm_all` | 280 / 280 | 2894 GB | Main + helper | `opprcdYYYY`, `secprdYYYY`, `vsurfdYYYY`, then reference tables |
| `ravenpack_dj` | 55 / 55 | 296 GB | Main dataset | `rpa_djpr_equities_YYYY`, `rpa_djpr_global_macro_YYYY` |
| `tr_common` | 30 / 30 | 225 GB | Helper library | `permquoteinfo`, `perminstrinfo`, `permorginfo`, `permsecmapx` |
| `tr_ibes` | 166 / 166 | 711 GB | Main + helper | `det_*`, `statsum_*`, `act_*`, `ptg*`, `recd*`, then `id`, `curr`, `adj` |
| `tr_ownership` | 44 / 44 | 466 GB | Main + helper | `ownholddet`, `ownholdcf`, `ownsecfdata`, `owninsdata` |
| `trace_enhanced` | 14 / 14 | 132 GB | Main + helper | relevant `trace*_enhanced` family, then `*masterfile` |
| `trace_standard` | 23 / 23 | 105 GB | Main + helper | `trace`, `trace_*`, `trade_summary*`, then `*masterfile` |
| `wrdsapps_bondret` | 4 / 4 | 93 GB | Main + staging | `bondret`, `bondret_std` |
| `wrdsapps_plink_boardex_ciq` | 2 / 2 | 500 MB | Bridge library | `boardex_ciq`, `boardex_ciq_link` |

## Library Notes

### `boardex_na`

Official description: BoardEx - North America.

What the data is: governance, executive, board, and professional-network data
for people and companies. This is a graph-like library with profile tables,
association edges, and compensation/wealth tables.

Evidence that matters:

- The largest table is `na_wrds_individual_networks` at roughly 1.35 billion
  estimated rows. Sample columns such as `associationtype`, `dirbrdname`,
  `companyname`, `directorname`, `overlapyearstart`, and `overlapyearend`
  clearly describe relationship edges.
- `na_wrds_dir_profile_all` is the cleanest person master.
- `na_wrds_company_profile` is the cleanest company master.
- `na_dir_*_assoc` and `na_board_*_assoc` tables carry the actual
  person-company, school, nonprofit, and other affiliation edges.

Main tables:

- `na_wrds_dir_profile_all` (4.40 GiB): person master table with one cleaned
  BoardEx person record per `directorid`, including name fields, title fields,
  and profile attributes. This is the best entry point for person-level
  governance research.
- `na_wrds_company_profile` (200.91 MiB): company master table with one cleaned
  BoardEx company record per `companyid`, used as the anchor for company-level
  joins before moving into boards, executives, or network edges.
- `na_wrds_individual_networks` (370.92 GiB): the dominant edge table in the
  library, storing person-to-person overlap links with relationship type,
  organization context, and start/end overlap years.
- `na_wrds_company_networks` (1.65 GiB): company-to-company overlap network
  derived from shared directors, managers, and affiliations; useful for board
  interlock and network-centrality studies.
- `na_dir_*_assoc` and `na_board_*_assoc` (~243.01 GiB combined): affiliation
  edge families linking people or boards to listed firms, unlisted firms,
  nonprofits, education institutions, and other organizations.
- `na_ltip_compensation`, `na_options_compensation`, `na_ltip_wealth`,
  `na_options_wealth`, `na_dir_standard_remun` (~998.87 MiB combined):
  director-level compensation and wealth tables covering cash pay, option
  awards, long-term incentive awards, and related remuneration measures.

Helper tables:

- `na_wrds_company_names`, `na_wrds_company_dir_names`: cleaned name helpers
- `na_wrds_company_region`: geography helper
- `na_wrds_org_composition`, `na_wrds_org_summary`: organizational summaries
- `na_dir_characteristics`, `na_board_characteristics`: enrichment dimensions

Practical read: treat this as a people-company network dataset, not as market
data.

### `ciq_pplintel`

Official description: Capital IQ People Intelligence.

What the data is: executive, professional-role, biography, and compensation
data linking people to firms and functions.

Evidence that matters:

- `wrds_professional` is large, well-commented, and already flattened around
  company, person, and role identifiers.
- `wrds_compensation` and `wrds_compensationdetails` are clearly annual
  compensation panels.
- Small tables such as `ciqprofunction`, `ciqcompensationtype`, and
  `ciqcompensationsubtype` are pure decoders.

Main tables:

- `wrds_professional` (8.46 GiB): flattened person-role panel linking
  `companyid`, `personid`, `proid`, function ids, company name, and person
  name. This is the cleanest starting table for executive-role histories.
- `wrds_compensation` (3.09 GiB): annual compensation panel by company, person,
  and fiscal year, already organized for panel work on pay levels and changes.
- `wrds_compensationdetails` (1.59 GiB): more granular compensation detail table
  with subtype-level breakdowns such as salary, bonus, stock awards, or option
  awards.
- `ciqprofessional` (3.33 GiB): raw professional-role records before the WRDS
  flattening layer; useful if you need Capital IQ’s native schema.
- `ciqperson` (695.80 MiB): raw person master table with Capital IQ person
  attributes.
- `ciqcompensation` (9.95 GiB): raw compensation facts at the report/event
  level, larger and less analysis-friendly than `wrds_compensation`.
- `ciqcompensationdetail` (2.60 GiB): raw compensation component detail table
  with subtype sequences and filing metadata.

Helper tables:

- `ciqprofunction`, `ciqprotoprofunction`: role and function decoding
- `ciqcompensationtype`, `ciqcompensationsubtype`,
  `ciqcompensationadjustmenttype`: compensation code lookups
- `ciqprofessionalcoverage`: coverage helper
- `compensation_length`: subtype metadata helper
- `ciqpersonbiography`: text enrichment, not a core panel

Practical read: if the question is "who held which role and what were they
paid?", start with the `wrds_*` tables.

### `ciq_ratings`

Official description: Capital IQ Ratings.

What the data is: S&P ratings and assessments across entities, instruments, and
securities, with both raw normalized tables and WRDS-flattened views.

Evidence that matters:

- `wrds_srating` is the cleanest security-rating table and carries rating,
  outlook, and prior-rating fields directly.
- `spratingdata` is a raw rating-detail table, while `spratingleveldata`,
  `spsecurityleveldata`, `spinstrumentleveldata`, and `spentityleveldata` are
  narrow attribute-value extensions. Those are useful but awkward as first
  tables.
- `ratings_ids` is the identifier spine linking entity, instrument, and sector
  codes.

Main tables:

- `wrds_srating` (2.90 GiB): security-level ratings panel with current rating,
  prior rating, outlook, and watch fields already expanded into columns. This
  is the best security-rating starting point.
- `wrds_irating` (20.77 MiB): instrument-level ratings table when you want to
  work above the security level but below the entity level.
- `wrds_erating` (105.27 MiB): entity-level ratings table for issuer/obligor
  style analysis.
- `wrds_sassessment` (33.17 MiB) and `wrds_eassessment` (736.00 KiB):
  assessment-oriented panels parallel to the ratings tables, useful when the
  research question needs S&P assessments rather than published ratings.
- `ratings_ids` (4.79 GiB): identifier spine tying together entity, instrument,
  and security ids along with sector, subsector, SIC, and NAICS fields. In
  practice this is the key bridge table for joining the rating layers.

Helper tables:

- `spratingdata`, `spratingleveldata`: raw rating detail plus attribute-value
  expansion
- `spassessmentdata`, `spassessmentleveldata`: raw assessment detail
- `spratingtype`, `spassessmenttype`: decoder tables
- `spratingidentifier`, `spinstrumenttoentity`, sector and industry tables:
  identifier and classification helpers
- `wrds_sec_info`, `wrds_inst_info`, `wrds_entity_info`: descriptive join
  helpers around the main rating panels

Practical read: start with the `wrds_*rating` or `wrds_*assessment` tables
unless you explicitly want the raw S&P normalized schema.

### `comp_global_daily`

Official description: Compustat Global - daily updates.

What the data is: Compustat Global security, fundamentals, index, and reference
data. This is a mixed library with multiple main table families rather than one
single center.

Evidence that matters:

- `g_secd` and `g_sec_dprc` dominate the library by row count and size, and the
  sample columns are daily security price and trading fields keyed by `gvkey`,
  `iid`, and `datadate`.
- `g_secm` is the monthly security panel.
- `g_funda` and `g_fundq` are the likely primary company fundamentals tables,
  while many `g_co_*` and `g_sec_*` tables are narrower item-group tables.
- `dd_*`, `xfl_*`, and many `r_*` tables are clearly metadata/reference
  structures.

Main tables:

- `g_secd` (74.29 GiB): merged global security daily panel keyed by `gvkey`,
  `iid`, and `datadate`, with price, volume, adjustment, and identity fields.
  This is the broadest daily market-data entry point in the library.
- `g_sec_dprc` (34.04 GiB): narrower daily security price table with the core
  price, volume, dividend, and adjustment fields when you do not need the full
  merged descriptor payload from `g_secd`.
- `g_secm` (2.17 GiB): merged monthly security panel for lower-frequency
  market-data work.
- `g_funda` (1.02 GiB): merged annual fundamentals file, the standard annual
  company-accounting entry point.
- `g_fundq` (2.95 GiB): merged quarterly fundamentals file, the standard
  quarter-level accounting entry point.
- `g_co_*` family (~7.00 GiB across 22 tables): company-level annual and
  interim descriptor, item, footnote, industry, and supplemental tables used
  when you need a specific Compustat company data group rather than the merged
  `g_funda` or `g_fundq` files.
- `g_sec_*` family (~38.69 GiB across 17 tables): security-level price,
  dividend, adjustment, and security-fundamental tables used when the security
  rather than the company is the unit of analysis.
- `g_idx_daily` (297.71 MiB): daily global index history for index-level return
  and constituent work.

Helper tables:

- `dd_group`, `dd_group_xref`, `dd_item`, `dd_package`: data-dictionary
  helpers
- `xfl_table`, `xfl_column`: metadata cross-reference helpers
- many `r_*` tables: reference/code helpers
- name and identity tables such as `g_names*` are support tables rather than
  the main panel of record

Practical read: for market data start with `g_secd` or `g_sec_dprc`; for
fundamentals start with `g_funda` or `g_fundq`; use `dd_*` only to decode the
schema.

### `contrib_general`

Official description: Contributed Data.

What the data is: a heterogeneous collection of separate research datasets.
There is no single backbone table.

Evidence that matters:

- `common_own_firm` is by far the largest table and is already a research-ready
  pairwise panel keyed by `year`, `gvkey_a`, and `gvkey_b`.
- `arc`, `better_beta`, `as_firm_risks`, `marginal_tax`, and
  `classified_boards` each look like standalone finished datasets.
- `cik_types` and `_states_` are obviously helper classification tables.

Main tables:

- Treat each substantive research table as its own main dataset, including
  `common_own_firm` (170.41 GiB), a pairwise firm-year common-ownership panel;
  `common_own_industry` (896.00 KiB), the industry-level analogue;
  `arc` (126.91 MiB), a filing-text accounting reporting complexity dataset;
  `better_beta` (254.21 MiB), a return-risk panel of improved beta estimates;
  `as_firm_risks` (38.66 MiB), firm-year Item 1A topic exposures and
  probabilities; `classified_boards` (9.84 MiB), governance board-classification
  labels; `marginal_tax` (11.45 MiB), firm-year marginal tax rates; the
  `factors*` tables, small factor-return panels in different currency variants;
  `liva` (77.38 MiB), a standalone contributed research panel; and `shale`
  (2.07 MiB), a small topic-specific contributed dataset.

Helper tables:

- `_states_`, `cik_types`
- small decode tables whose only job is labeling another contributed table

Practical read: do not search for one "master" table here. Read the table
comment in `postgres_tables.csv` and treat each research table on its own.

### `contrib_global_factor`

Official description: Global Factor Data.

What the data is: a compact factor-research library with a wide integrated
panel, a daily return panel, a monthly characteristic panel, and one feature
dictionary.

Evidence that matters:

- `global_factor` is a 443-column wide panel and is the natural centerpiece.
- `ctff_daily_ret` is the largest table by rows and is a simple daily
  `id`-by-`date` return panel.
- `ctff_chars` is a wide monthly characteristic table.
- `ctff_features` contains only one column and behaves like a dictionary for
  feature names.

Main tables:

- `global_factor` (67.41 GiB): the widest integrated factor panel, combining
  security identifiers, market structure fields, and hundreds of characteristics
  into one analysis table.
- `ctff_daily_ret` (4.26 GiB): simple daily excess-return panel keyed by `id`
  and `date`, useful when you only need the return leg.
- `ctff_chars` (4.78 GiB): monthly characteristic panel with hundreds of
  cross-sectional features such as price, market equity, enterprise value, and
  other firm characteristics.

Helper tables:

- `ctff_features`: feature dictionary

Practical read: start with `global_factor` if you want one merged dataset;
split to `ctff_daily_ret` or `ctff_chars` only when you want a narrower panel.

### `factset_common`

Official description: Factset Common Files.

What the data is: symbology, entity mapping, security classification, and code
tables shared across FactSet products. This is a helper library by design.

Evidence that matters:

- `sym_coverage`, `sym_entity`, and `sym_sec_entity` are clearly symbology
  backbones.
- The library has many `*_map` tables, metadata tables, and classification
  tables.
- Nothing in the sample set looks like a return series, holding panel, or event
  stream.

Main tables:

- There are no true main research fact tables here.
- The closest thing to a backbone is `sym_coverage`, `sym_entity`,
  `sym_sec_entity`, `sym_cusip[_hist]`, `sym_isin[_hist]`,
  `sym_ticker_exchange[_hist]`, and `wrds_securities_v3`.
- `sym_coverage` (12.07 GiB): the main FactSet security/listing coverage table,
  carrying FSYM ids, security flags, primary listing ids, and broad listing
  metadata.
- `sym_entity` (1.91 GiB): entity master mapping FactSet entity ids to entity
  names, countries, and entity types.
- `sym_sec_entity` (118.76 MiB): bridge table linking security-level FSYM ids to
  entity ids.
- `sym_cusip_hist` (2.26 GiB), `sym_isin_hist` (37.16 MiB),
  `sym_ticker_exchange_hist` (2.80 GiB): the historical external-identifier
  mapping tables most often needed in joins.
- `wrds_securities_v3` (2.05 GiB): WRDS-curated security backbone that is often
  easier to use than stitching multiple raw symbology tables yourself.

Helper tables:

- almost everything else in the library
- all `*_map` tables
- `ref_metadata_*`
- country, region, RBICS, NAICS, SIC, exchange, and security-type lookups

Practical read: this is the FactSet join spine. Use it before touching
`factset_own`.

### `factset_own`

Official description: Factset Ownership LionShares.

What the data is: fund, institutional, 13F, stake, and insider ownership data,
plus the entity and security tables required to decode it.

Evidence that matters:

- `own_fund_detail_eq` and `own_inst_13f_detail_eq` are clear holdings detail
  panels keyed by owner, security, and `report_date`.
- `wrds_own_fund` and `wrds_own_13f` are large WRDS-curated rollups that are
  easier to start from than the raw detail.
- `own_ent_*` and `own_sec_*` families are mostly reference structures around
  holders and securities.

Main tables:

- `own_fund_detail_eq` (57.15 GiB): historical fund-by-security holdings detail
  for active and terminated funds, keyed by fund, security, and report date.
- `own_inst_13f_detail_eq` (11.67 GiB): historical institutional equity
  holdings sourced from 13F filings.
- `own_inst_stakes_detail_eq` (1.12 GiB) and `own_stakes_detail_eq`
  (2.11 GiB): stakes-based holdings detail outside the standard 13F channel.
- `own_uksr_detail_eq` (2.47 GiB) and `own_uksr_cust_detail_eq` (82.26 MiB):
  UK shareholder-register and custodial-holder detail tables.
- `own_insider_trans_eq` (3.77 GiB): insider and stakeholder transaction fact
  table for equity securities.
- `wrds_own_13f` (29.79 GiB): WRDS-curated 13F table that adds holder metadata
  and is usually easier to start from than the raw detail.
- `wrds_own_fund` (184.75 GiB): WRDS-curated fund holdings rollup with holder
  descriptors attached; this is often the most convenient broad fund-holdings
  starting table in the library.

Helper tables:

- `own_ent_*`: institution, fund, filing, manager, and objective references
- `own_sec_*`: security coverage, mappings, history, and pricing helpers
- `own_ent_coverage`: entity role flags
- `own_sec_prices_eq`: fact-like, but mostly used as a valuation helper

Practical read: the holdings live in the detail tables; the `own_ent_*` tables
tell you who the holder is, and the `own_sec_*` tables tell you what the
security is.

### `fisd_fisd`

Official description: Mergent FISD Database.

What the data is: fixed-income security reference data, issue terms, ratings,
actions, covenants, and a large historical time-and-sales table.

Evidence that matters:

- `fisd_tsales` is the dominant fact table and is clearly a trade tape.
- `fisd_mergedissue` is the broad issue master with many columns.
- Many tables are keyed by `issue_id` and describe one aspect of that issue:
  ratings, calls, changes, agents, bankruptcy, sinking funds, or covenants.

Main tables:

- `fisd_mergedissue` (288.58 MiB): the best issue-level master table, combining
  a broad set of issue terms and identifiers into one wide security record.
- `fisd_issue` (221.59 MiB): narrower issue master if you want the base issue
  file without the merged extras.
- `fisd_issuer` (2.09 MiB): issuer anchor table for bond-level joins up to the
  issuing firm.
- `fisd_tsales` (68.06 GiB): historical bond time-and-sales fact table and the
  clear starting point for transaction research.
- `fisd_ratings` (331.48 MiB), `fisd_rating` (166.09 MiB), and
  `fisd_rating_hist` (165.43 MiB): current and historical ratings tables used
  to attach rating states and rating transitions to issues.

Helper tables:

- `fisd_code`: code/decode table
- `fisd_agent`, `fisd_contact`, `fisd_issue_agents`: relationship helpers
- many `fisd_*schedule`, `fisd_*protective`, `fisd_bankruptcy*`,
  `fisd_warrant*`, `fisd_convertible*`, `fisd_treasury*` tables: specialized
  supporting issue-event or term tables
- `fisd_notes`: support text around an issue, not the main key panel

Practical read: start from `fisd_mergedissue` for bond master data or
`fisd_tsales` for transaction research, then pull in the specialized issue
tables only as needed.

### `markit_cds`

Official description: Markit Credit Default Swap.

What the data is: yearly CDS quote panels plus a small lookup layer.

Evidence that matters:

- `cds2001` through `cds2026` all share the same wide quote structure keyed by
  `date`, `ticker`, and `redcode`.
- `cdslookup` is a small cleaner identifier helper.
- `chars` exists but is tiny and not central.

Main tables:

- `cds2001` through `cds2026` (~341.29 GiB across 26 yearly tables): the core
  CDS quote panels, each storing daily CDS observations with `date`, `ticker`,
  `redcode`, sector, region, country, ratings context, contract tier, and the
  wide quote surface used in spread research.

Helper tables:

- `cdslookup`: identifier helper
- `chars`: auxiliary table if populated for a specific use case

Practical read: start with the yearly `cdsYYYY` table you need, then join
`cdslookup` if you want cleaner labels.

### `msrb_all`

Official description: MSRB - Municipal Securities Transaction Data.

What the data is: municipal bond trade data with one main trade table, one
small lookup, and one web-query helper table.

Evidence that matters:

- `msrb` has over 215 million estimated rows and clearly contains municipal
  trade facts keyed by trade identifiers, CUSIP, trade date, coupon, and
  maturity.
- `msrb_lookup` is a lightweight CUSIP-prefix description helper.
- `msrb_qvards` is empty in the catalog and explicitly labeled as web-query
  support only.

Main tables:

- `msrb` (79.13 GiB): the municipal trade tape with trade identifiers, CUSIP,
  security description, dated date, coupon, maturity, trade date/time, and
  settlement fields. This is effectively the whole dataset of interest.

Helper tables:

- `msrb_lookup`: security description helper by `cusip6`
- `msrb_qvards`: query-support helper, not a research table

Practical read: almost everything you want is in `msrb`; the other two tables
exist to support search and labeling.

### `optionm_all`

Official description: IvyDB US by OptionMetrics.

What the data is: large yearly option, underlying, volatility-surface, forward,
borrow-rate, and distribution families plus a smaller reference layer.

Evidence that matters:

- There are 280 tables and the families are extremely regular: 30 yearly tables
  each for `opprcd`, `secprd`, `vsurfd`, `stdopd`, `hvold`, `borrate`,
  `fwdprd`, and `stdbrte`, plus 28 yearly `distrprojd` tables.
- Samples show `opprcdYYYY` as option price panels, `secprdYYYY` as underlying
  security panels, and `vsurfdYYYY` as volatility surface grids.
- Timeless short-name tables serve mostly as identifiers or support datasets.

Main table families:

- `opprcdYYYY` (~1.10 TiB across 30 yearly tables): contract-level option
  price and volume history keyed by security id, trade date, expiration, call/
  put flag, and strike.
- `stdopdYYYY` (~100.39 GiB across 30 yearly tables): standardized option price
  panels, useful when you want the normalized version of the option pricing
  history.
- `vsurfdYYYY` (~1.48 TiB across 30 yearly tables): implied-volatility surface
  grids by security, date, days-to-expiry, delta, and option side.
- `secprdYYYY` (~10.92 GiB across 30 yearly tables): underlying security daily
  prices and returns used to connect options back to the underlying asset.
- `hvoldYYYY` (~37.27 GiB across 30 yearly tables): historical volatility
  series.
- `borrateYYYY` (~14.20 GiB across 30 yearly tables): borrow-rate panels by
  security, date, and expiration horizon.
- `fwdprdYYYY` (~14.21 GiB across 30 yearly tables): forward-price panels by
  security, date, and tenor.
- `distrprojdYYYY` (~21.27 GiB across 28 yearly tables): distribution-
  projection panels used in option valuation and risk decomposition.

Helper tables:

- short timeless reference tables such as `optionmnames`, `securd`, `secnmd`,
  `indexd`, `idxdvd`, `exchgd`, `opinfd`, `opvold`, `distrd`, and `zerocd`

Practical read: if the name ends in a year and sounds like a market panel, it
is usually a main table. If it is a short timeless name, it is usually helper.

### `ravenpack_dj`

Official description: RavenPack - Dow Jones Edition.

What the data is: event-level news analytics for equities and macro entities.

Evidence that matters:

- `rpa_djpr_equities_YYYY` and `rpa_djpr_global_macro_YYYY` share the same
  timestamped event structure with story id, entity id, relevance, and
  sentiment fields.
- `djpr_chars` exists but appears auxiliary and non-central.

Main table families:

- `rpa_djpr_equities_YYYY` (~116.09 GiB across 27 yearly tables): equity-linked
  event stream with UTC timestamps, story ids, entity ids, entity names,
  relevance, sentiment, and event similarity fields.
- `rpa_djpr_global_macro_YYYY` (~179.97 GiB across 27 yearly tables):
  macro-linked event stream in the same format, covering countries, macro
  entities, and macro news events.

Helper tables:

- `djpr_chars`: auxiliary/helper table if populated

Practical read: the yearly `rpa_*` tables are already the event stream. There
is very little helper complexity here.

### `tr_common`

Official description: blank in the library catalog, but the tables clearly show
that this is Refinitiv common identifier and mapping infrastructure.

What the data is: a Refinitiv symbology, identifier-history, and security-map
library.

Evidence that matters:

- `permquoteinfo`, `perminstrinfo`, and `permorginfo` are descriptive backbones
  for quote, instrument, and organization permanent identifiers.
- `permricdata`, `permisindata`, `permcusipdata`, and related tables are
  historical identifier maps.
- `permsecmapx`, `gsecmapx`, and `secmapx` are explicit bridge tables.

Main tables:

- There are no real market-data fact tables here.
- The closest thing to a backbone is `permquoteinfo`, `perminstrinfo`,
  `permorginfo`, `permquoteref`, and `perminstrref`.
- `permquoteinfo` (38.35 GiB): quote-level master table with QuotePermID and
  broad quote descriptors.
- `perminstrinfo` (26.50 GiB): instrument-level master table with InstrPermID
  and broad asset-class/category descriptors.
- `permorginfo` (4.27 GiB): organization-level master table with OrgPermID-style
  descriptors.
- `permquoteref` (28.90 GiB) and `perminstrref` (13.95 GiB): richer reference
  tables carrying more detailed quote and instrument attributes than the `info`
  tables.

Helper tables:

- `permsecmapx`, `gsecmapx`, `secmapx`, `vw_securitymappingx`,
  `vw_securitymasterx`
- historical identifier maps such as `permcusipdata`, `permcincusipdata`,
  `permisindata`, `permsedoldata`, and `permricdata`
- code tables such as `permcode`, `tmccode`, `secventype`,
  `tmcregncntrymap`

Practical read: this is the Refinitiv join spine. Use it before joining to
`tr_ownership` or other Refinitiv libraries.

### `tr_ibes`

Official description: Thomson Reuters IBES Historical Estimates (Global).

What the data is: analyst estimates, actuals, consensus statistics, price
targets, recommendations, surprises, and the helper tables needed to interpret
them.

Evidence that matters:

- The library is huge and highly regular. Many families repeat across EPS,
  non-EPS, US, international, normalized, and unadjusted variants.
- `det_*` tables are analyst-level detail history.
- `statsum_*` tables are consensus summary history.
- `act_*`, `ract_*`, `ptg*`, and `recd*` families cover actuals, revisions,
  price targets, and recommendations.

Main table families:

- `det_*`, `detu_*`, `ndet_*`, `ndetu_*` (~298.65 GiB across 16 tables):
  analyst-level estimate detail history, including normalized and unadjusted
  variants across EPS/non-EPS and US/international regions.
- `statsum_*`, `statsumu_*`, `nstatsum_*`, `nstatsumu_*` (~179.94 GiB across 16
  tables): consensus and summary-statistics history, the natural starting point
  for consensus-level IBES work.
- `act_*`, `actu_*`, `ract_*`, `ractu_*`, `nact_*`, `nactu_*`, `nract_*`,
  `nractu_*` (~29.30 GiB across 32 tables): actuals and realized outcomes,
  including normalized, restated, and unadjusted variants.
- `ptgdet*`, `ptgsum*`, `nptgdet*`, `nptgsum*` (~8.79 GiB across 8 tables):
  price-target detail and summary families.
- `recd*` (~2.17 GiB across 5 tables): recommendation detail, identifier, and
  summary tables.
- `surp*` and `nsurp*` (~5.82 GiB across 4 tables): surprise-history tables.
- `newact*` and `newnact*` (~53.33 GiB across 4 tables): newer actuals history
  families layered alongside the older `act_*` families.

Helper tables:

- `id`, `idsum`: identifier backbones
- `curr`, `currnew`, `ncurr`: report-currency helpers
- `adj`, `adjsum`: adjustment-factor helpers
- `trbc`: classification helper
- `eurx`, `hsxrat`, `hdxrati`: FX/conversion helpers
- `stop*` and some `secd*` tables: specialized support state tables rather than
  the main forecast panel

Practical read: for analyst-level behavior, start with `det_*`; for consensus
history, start with `statsum_*`; keep `id`, `curr`, and `adj` nearby.

### `tr_ownership`

Official description: Thomson Reuters Global OP Ownership.

What the data is: holdings, ownership carry-forward logic, security metadata,
insider activity, and code/identifier infrastructure.

Evidence that matters:

- `ownholddet` is the dominant holdings panel by size and row count.
- `ownholdcf` is the carry-forward and next-report-date companion table.
- `ownsecfdata` is a narrow historical security metric panel used for pricing
  and shares-outstanding style enrichment.
- `wrds_ownholddet_type1/2/3` are WRDS-curated splits of the holdings detail.

Main tables:

- `ownholddet` (116.24 GiB): the core holder-security-date holdings fact table
  with shares held, value held, position-change fields, and holding type flags.
- `ownholdcf` (92.96 GiB): carry-forward and next-report-date companion table
  used to understand reporting continuity and stale holdings intervals.
- `ownsecdata` (23.85 GiB): numeric security-level history keyed by
  `securitycode`, used to enrich holdings with security metrics.
- `ownsecfdata` (5.32 GiB): historical pricing and shares-outstanding table for
  security-level valuation work.
- `owninsdata` (854.46 MiB) and `owninsasiadata` (567.14 MiB): insider
  transaction fact tables for global and Asia-specific insider activity.
- `wrds_ownholddet_type1` (61.68 GiB), `wrds_ownholddet_type2` (55.18 GiB), and
  `wrds_ownholddet_type3` (94.89 GiB): WRDS-curated holdings splits that make
  certain ownership subtypes easier to study directly.
- `wrds_ownsecfdata` (11.77 GiB): WRDS-enriched security information plus
  pricing data, usually more convenient than rebuilding the same enrichment from
  the raw security tables.

Helper tables:

- `owncode`, `ownconspcode`, `owninscode`, `ownsecsectorcode`: decode helpers
- `ownastalloc`, `owndesc`, `owninfo`, `ownsecinfo`, `ownsecissuer`,
  `ownconinfo`: descriptive reference tables
- `ownsecmap`, `ownsecident`: identifier maps
- `ownprofcode`: owner profile text
- `chars`: characteristic helper
- `wrds_ownids`: useful identifier bridge, but still support relative to the
  holdings facts

Practical read: the ownership story starts with `ownholddet`; most other
tables explain who the owner is, what the security is, or how to decode the
attached codes.

### `trace_enhanced`

Official description: FINRA TRACE Enhanced.

What the data is: enhanced TRACE bond trade tapes split across product families,
plus bond masterfiles.

Evidence that matters:

- `trace_enhanced` is the largest table and is clearly the core BTDS enhanced
  trade tape.
- `trace_btds144a_enhanced`, `trace_agency_enhanced`,
  `trace_spds_mbs_enhanced`, `trace_spds_tba_enhanced`, and related
  `trace_spds*` tables are product-specific trade fact tables.
- `absmasterfile`, `camasterfile`, `cmomasterfile`, `mbsmasterfile`, and
  `tbamasterfile` are security master helpers.

Main tables:

- `trace_enhanced` (98.59 GiB): the core enhanced BTDS trade tape with trade
  dates/times, report dates/times, message sequence numbers, trade status, and
  richer TRACE fields than the standard feed.
- `trace_btds144a_enhanced` (6.82 GiB): enhanced 144A corporate-bond trade
  tape.
- `trace_agency_enhanced` (3.69 GiB): enhanced agency-bond trade tape.
- `trace_spds_abs_enhanced` (302.35 MiB), `trace_spds_cmo_enhanced`
  (2.01 GiB), `trace_spds_mbs_enhanced` (4.16 GiB),
  `trace_spds_tba_enhanced` (9.16 GiB), `trace_spds144a_abs_enhanced`
  (169.85 MiB), and `trace_spds144a_cmo_enhanced` (205.59 MiB): product-family
  enhanced trade tapes for structured products.

Helper tables:

- `absmasterfile`, `camasterfile`, `cmomasterfile`, `mbsmasterfile`,
  `tbamasterfile`: master security reference tables

Practical read: choose the `trace*_enhanced` family that matches the product
you care about, then join the relevant masterfile for security attributes.

### `trace_standard`

Official description: FINRA TRACE corporate bond trades.

What the data is: standard TRACE raw trade tapes, product-specific trade tapes,
daily trade summaries, and security masterfiles.

Evidence that matters:

- `trace` is the raw core trade tape.
- `trace_*` families extend the raw tape across product families such as agency
  and structured products.
- `trade_summary*` tables are daily aggregates rather than raw trades.
- `*masterfile` tables are security reference helpers.

Main tables:

- `trace` (69.95 GiB): the core raw TRACE trade tape for BTDS corporate bond
  trades.
- `trace_agency` (3.37 GiB), `trace_btds144a` (4.89 GiB), and the
  `trace_spds_*` product tables (about 8.58 GiB combined): product-specific raw
  trade tapes for agency, 144A, ABS, CMO, MBS, and TBA segments.
- `trade_summary` (7.72 GiB) and `trade_summary_*` (~10.73 GiB across 9
  tables): daily aggregate panels that summarize trading activity and are often
  a better starting point than raw message-level trades when you only need
  daily measures.

Helper tables:

- `absmasterfile`, `camasterfile`, `cmomasterfile`, `mbsmasterfile`,
  `tbamasterfile`: security master/reference tables

Practical read: use `trace*` for raw trade research, `trade_summary*` for a
lighter aggregated entry point, and `*masterfile` only for enrichment.

### `wrdsapps_bondret`

Official description: WRDS Bond Returns.

What the data is: WRDS-derived bond return panels plus cleaned TRACE staging
tables that support the return construction.

Evidence that matters:

- `bondret` and `bondret_std` are the only tables that look like finished
  return datasets; both contain bond identifiers and return-related fields.
- `trace_enhanced_clean` and `trace_standard_clean` are much larger and look
  like cleaned upstream trade tapes rather than end-user return tables.

Main tables:

- `bondret` (1.85 GiB): the main WRDS bond return panel, with bond identifiers,
  issue-level attributes, and return-ready monthly observations derived from
  TRACE and bond reference data.
- `bondret_std` (84.16 MiB): smaller standard-TRACE-based return panel useful
  when you want the narrower standard-data construction.

Staging tables:

- `trace_enhanced_clean` (55.69 GiB): cleaned enhanced TRACE source used
  upstream in the return construction pipeline.
- `trace_standard_clean` (35.43 GiB): cleaned standard TRACE source used
  upstream in the return construction pipeline.

Practical read: if you want returns, start with `bondret`; only go to the
`trace_*_clean` tables if you need to inspect the construction inputs.

### `wrdsapps_plink_boardex_ciq`

Official description: WRDS-developed research or utility dataset.

What the data is: a BoardEx-to-Capital-IQ person and company crosswalk.

Evidence that matters:

- `boardex_ciq` contains BoardEx director and board identifiers plus company
  identifiers such as ticker, ISIN, and CIK.
- `boardex_ciq_link` is a leaner person-link table centered on matched names
  and `personid`.

Main tables:

- None in the sense of a standalone research panel

Bridge tables:

- `boardex_ciq` (410.74 MiB): richer bridge table linking BoardEx people and
  boards to Capital IQ company identifiers such as ticker, ISIN, and CIK.
- `boardex_ciq_link` (89.37 MiB): leaner person-match bridge table centered on
  name matching and `personid` linkage.

Practical read: this library is only useful as crosswalk infrastructure between
`boardex_na` and Capital IQ data.

## Where The Old Guide Was Most Likely To Be Wrong

The previous version was directionally useful, but it had three real
limitations:

- it described 10-row samples even though the active sample snapshots are
  100-row extracts
- it missed eight sampled libraries entirely:
  `ciq_ratings`, `comp_global_daily`, `contrib_global_factor`, `fisd_fisd`,
  `msrb_all`, `trace_enhanced`, `trace_standard`, and `wrdsapps_bondret`
- it leaned too heavily on naming heuristics for some families that now have
  enough metadata and sample depth to classify more confidently

The updated classifications that matter most:

- `comp_global_daily` is not a single-table dataset; it has several main table
  families plus a large metadata layer
- `ciq_ratings` is best approached through the WRDS-flattened `wrds_*rating`
  and `wrds_*assessment` tables, not the raw `sp*leveldata` tables
- `fisd_fisd` has two distinct centers: issue master data and historical time
  and sales
- `trace_standard` and `trace_enhanced` are clearly raw-trade libraries with
  masterfile helpers, not just generic bond helper libraries
- `wrdsapps_bondret` is a derived analysis-ready library with staging tables,
  not a pure helper library

## Common Sources Of Confusion

- `tr_common` and `factset_common` are large, but they are mostly helper
  libraries, not the final research panel.
- `contrib_general` is not one dataset. Each substantive table stands on its
  own.
- `wrdsapps_plink_boardex_ciq` is a bridge library, not a destination dataset.
- `comp_global_daily`, `optionm_all`, `factset_own`, `tr_ibes`, and
  `tr_ownership` all contain both main and helper tables, so the table family
  matters more than the library name alone.
