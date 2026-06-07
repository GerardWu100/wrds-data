# IvyDB Open Interest Timing Note

This note documents an important timing convention in the OptionMetrics IvyDB
US `Option_Price` file.

## Field

`Open Interest` in the manual corresponds to the `open_interest` column in
WRDS `optionm_all.opprcdYYYY` tables.

`Open interest` means the number of option contracts outstanding for a contract.
It is not the same as volume. `Volume` counts contracts traded during the day;
`open_interest` counts contracts still open after trades, exercises,
assignments, and closing transactions have been processed.

## Manual Convention

The IvyDB US v5.4 Reference Manual says:

- After November 28, 2000, `Option_Price.Open Interest` is lagged by one day.
- Before November 28, 2000, `Option_Price.Open Interest` is not lagged.

This creates a timing break in the historical data.

## Research Implication

For dates after November 28, 2000, a same-date signal that uses
`open_interest` in `opprcdYYYY` usually uses information from the prior trading
day. That is often safer for avoiding lookahead bias because the value would
have been known before or near the start of the signal date.

For dates before November 28, 2000, same-date `open_interest` is not lagged.
That means it may reflect same-day information and should not automatically be
treated as known at the time a trading signal is formed.

`Lookahead bias` means using information in a backtest before it would have
been observable in real time. It can make a strategy look better than it would
have been in live trading.

## Practical Rule

For a conservative backtest, lag `open_interest` by one trading day before using
it as a signal input across the full sample. This applies one timing rule to
both pre- and post-November 28, 2000 data and avoids relying on the older
unlagged convention.

If a project specifically studies open interest timing, split the sample at
November 28, 2000 and document the treatment on each side of the break.

