# Data Quality Notes — Perth Rental Finder

This document records what the underlying data actually supports, where it's
thin, and the specific bugs this project caught and fixed by testing against
real data and a live running app rather than trusting the code to be correct
by inspection alone. It exists so a reader (or a future version of me) can
tell the difference between a measured number and an estimate, and
understand why certain design decisions were made the way they were.

## Coverage: 1,222 suburbs, not 26

The original `affordability` table — built early in this project around the
WA rental bond dataset — only had detailed profile data (2BR/3BR median
rent, tenancy duration, dispute rate, ATO income, SEIFA decile) for 26
suburbs. Every part of the app that read from that table directly was
therefore silently capped at 26 suburbs, no matter how the question was
phrased. A user asking about Cannington, Mingenew, or any of the other
~1,196 suburbs with real rent history but no detailed profile would get
nothing, or — worse — a tool that fell back to fuzzy string matching against
that same 26-suburb table and returned no result at all.

The actual underlying rental bond dataset covers far more ground. Building a
proper dimensional warehouse (`dim_suburb`, `dim_suburb_alias`,
`fact_rent_trend`, `fact_suburb_profile`, `fact_suburb_amenities`) surfaced
the real numbers:

| Coverage | Suburbs |
|---|---|
| Total suburbs in `dim_suburb` | 1,222 |
| With rent history (`fact_rent_trend`) | 1,163 |
| With full affordability profile (2BR/3BR rent, tenancy stats) | 26 |
| With ATO income / SEIFA decile | 173 |
| With school data | 1,129 |
| With train proximity data | 1,055 |
| With crime data | 173 |

The 26-suburb profile set was never wrong — it's real, measured data for
those 26 suburbs. The bug was treating it as if it were the whole dataset,
when it was a small, detailed subset of a much larger one.

## The postcode-as-suburb-name bug

When first building `fact_suburb_profile`, the join from `dim_suburb` to the
ATO income and SEIFA tables used `dim_suburb_alias` (a name-based bridge) on
the assumption that those tables' `suburb`/`SUBURB_NAME` columns held actual
suburb names. They didn't — they held postcodes formatted as strings (e.g.
`6150`, `6160`, `6027`). The name-based join matched almost nothing, and the
ATO/SEIFA coverage looked like only ~22 suburbs.

Fixing the join to use `dim_suburb.postcode = CAST(ai.suburb AS VARCHAR)`
brought real coverage up to 173 suburbs — an 8x difference between "the join
technically ran without error" and "the join actually found the data that
was there." This is the kind of bug that's invisible from the code alone;
it only showed up by inspecting the actual column values and checking the
row counts against an independent expectation (this dataset's known scope).

## Small-area-estimation fallback: where the line is drawn

Two fields — `avg_tenancy_years` and `dispute_rate_pct` — get a fallback
value (region average, falling back further to a Perth-wide average) for
suburbs that don't have their own measured figure. This is a deliberate,
narrow exception to an otherwise strict "never backfill" policy, and it
only exists because these two fields feed into the *internal ranking score*
used to order search results — not because they're meant to be shown to a
user as if they were a specific suburb's own statistic.

Every row in `get_all_suburbs_data()` carries an `avg_tenancy_years_is_estimated`
and `dispute_rate_pct_is_estimated` flag alongside the value itself. The
boundary enforced throughout `main.py` and `tools.py` is: the fallback value
may influence which suburbs get recommended and in what order, but it is
never presented in a card, in prose, or in any user-facing text as if it
were that suburb's own measured bond-return rate or tenancy length. Decision-
tier fields — median rent, 2BR/3BR rent, ATO income, SEIFA decile — are
never backfilled at all; they stay genuinely absent when the data is absent.

This distinction mattered in practice, not just in theory: an earlier version
of `suburb_to_card()` and `suburb_deep_dive()` checked only whether a bond-
rate/tenure value was present, not whether it was real or estimated. The
result was suburbs like Maylands — which has no detailed profile data —
showing a fabricated "86% bond return, 2.1 years avg stay," which was
actually the eastern-suburbs regional average dressed up as Maylands'
own number. Both card-building functions now check the `_is_estimated`
flags before presenting either figure, and omit them entirely rather than
mislabel an estimate as a measurement.

## Known display quirk: "nearest station" can be very far away

`fact_suburb_amenities.nearest_station` and `distance_km` record the closest
train station *in the dataset*, with no upper bound. For suburbs in or near
Perth this is genuinely useful — for remote and regional WA suburbs, it can
mean a result like "Mandurah Station, 260.7km away" (Mingenew) or "Mandurah
Station, 15.6km away" (North/South Yunderup), which reads as a normal
nearby-amenity chip if displayed without context.

The app applies a 15km cutoff before showing a train chip or sentence
anywhere a suburb is presented — beyond that, the train fields are simply
omitted rather than shown as if they meant "nearby." 15km was chosen as
generous enough to still be locally relevant while clearly excluding
results that are really reporting "the nearest station in WA," not
"the nearest station to this place."

## Suburb name resolution and ambiguity

User text is matched against suburb names via `find_suburb_mentions()`,
which checks full-name substring matches first, falling back to matching
just the first word of a suburb's stored name (to handle cases where a name
is stored with a state or postcode suffix). This two-pass ordering matters:
"Cannington" contains the substring "canning," which is also the first word
of "Canning Vale." Without prioritizing full matches, a message mentioning
Cannington could resolve to the wrong suburb depending on iteration order —
and this happened in testing, including under an adversarial correction
("I said Cannington not caning whale") where the fallback-only matching
logic was still finding "Canning Vale" via its first-word heuristic. Full
matches are now always preferred over first-word fallback matches, and
sorted longest-first among themselves.

## The `general` workflow and `tools.py`: a second, independent lookup path

Most user questions are classified into one of six named workflows (search,
deep dive, compare, negotiate, property advisor, application review), each
of which reads from the warehouse described above. A catch-all `general`
workflow exists for anything that doesn't match those triggers, and routes
to a separate Claude-powered tool-calling loop (`agent.py` / `tools.py`).

This second system had its own, independent suburb-lookup implementation
that queried the raw `affordability`/`rent_trend`/`tenancy_duration` staging
tables directly by uppercased string match — bypassing the warehouse,
the alias normalization, and the 1,222-suburb coverage entirely, while
silently inheriting the same 26-suburb ceiling described above. In testing,
this surfaced as two different, contradicting numeric profiles for the same
suburb in the same conversation: a correctly-resolved deep-dive card showing
one set of figures, and the `general` workflow's tool-calling response
showing a different set, sourced from a different table via a different
matching method.

`build_suburb_context()`, `get_rent_trend()`, and `find_cheap_suburbs()` in
`tools.py` were rewritten to resolve suburbs through the same
`dim_suburb_alias` → `dim_suburb` → `fact_*` path the rest of the app uses,
with the original implementations preserved as fallback functions (used
automatically if the warehouse tables aren't present, so neither path
hard-fails depending on which build step has been run). `agent.py`'s system
prompt also had hardcoded, stale figures ("1,152 suburbs," "$510 → $700/wk")
written once and never refreshed; these are now computed live from the
database at call time, with the original hardcoded values retained only as
a fallback if the live query fails.

`find_suburbs_near()` (landmark-based search) in `tools.py` was not
separately audited for the same class of issue — it's flagged here as a
known gap rather than a confirmed problem.

## Crime data is district-level, not suburb-level

The 173 suburbs with a `safety_score` get that figure from WA Police
district-level crime statistics, not suburb-specific reporting. Several
suburbs can share a single police district and therefore the same score.
This is disclosed in the app itself ("Check police.wa.gov.au" alongside any
displayed crime chip) rather than presented as if it were suburb-specific
data.

## A few `dim_suburb.suburb_name` values are postcode strings

A small number of suburbs in the dataset had no name source available when
`dim_suburb` was built, and fall back to displaying their postcode as the
suburb name. This is a low-priority cosmetic issue, not a data integrity
one — it affects suburb display casing/naming consistency for a handful of
very sparse, likely very small or very remote, entries.
