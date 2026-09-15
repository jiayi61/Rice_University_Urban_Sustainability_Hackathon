# EventFlow: English submission narrative and pitch

## Devpost narrative

### Inspiration

A large stadium event creates several transport systems with very different clearance times. We use New York/New Jersey's reported 2026 experience to ask a practical question: with a limited budget, which combination of operational changes should a future event test first?

### What it does

EventFlow compares a baseline with costed portfolios of coaches, transfer staffing, accessible service, managed pickup, rail overlay and shade. A user selects a budget, policy priority and disruption. The dashboard explains the selected actions, cost tradeoffs, uncertainty, delivery dependencies and source limitations, then exports an English decision brief.

### How we built it

We transcribed eight matches of agency egress aggregates, scanned all 191 organizer data shards, and preserved the original 192-file package with checksums in private release storage. Organizer data are transformed educational samples, so historical market activity and relative heat context are kept separate from actual event observations. Current MTA and OSM geometry provide map context. A transparent aggregate queue model exhaustively compares 128 portfolios and runs 81 assumption combinations. Eight-match holdout tests show where baseline transfer is reliable and where it is weak.

### What we learned

Rideshare throughput varies substantially across matches: its holdout error is much larger than rail's. A polished forecast would hide this; a useful decision tool makes it visible. Central costs also differ from high estimates, so a portfolio fitting the nominal budget still needs procurement review.

### Impact and legacy

The default $500,000 scenario selects a $435,000 central-cost portfolio and projects maximum clearance from 180 to about 132 minutes. These are model outputs, not demonstrated operational improvements. The reusable contribution is the evidence-to-decision workflow: account for cohorts, test budgets and disruptions, assign delivery responsibility, then measure a pilot. It can support later stadium events once local demand and operating constraints are verified.

### What's next

Obtain operator feedback, actual procurement quotations, historical event timetables and accessible-path audits; collect arrival and boarding time series; then evaluate an intervention at a subsequent event. No agency partnership or field validation is claimed.

## Three-minute recording script

**0:00–0:25 — Problem; show the hero.**

“At the New York/New Jersey final, NJ TRANSIT reported a 60-minute rail egress window and a 180-minute rideshare window. These are different passenger cohorts, not individual waiting times. For the next major event, a city needs more than a busy map. It needs a decision it can afford and explain.”

**0:25–0:55 — Decision; show the default portfolio.**

“This is EventFlow. With a five-hundred-thousand-dollar planning budget, it compares every combination of seven possible actions. Our balanced scenario selects coaches, accessible transfers, a protected bus operating window, managed pickup, and transfer staffing. Their central estimated cost is four hundred thirty-five thousand dollars. The high estimate is six hundred thousand, so quotations still matter.”

**0:55–1:20 — Results; show the KPIs and frontier.**

“The model projects maximum clearance falling from 180 to about 132 minutes, and queue burden falling by about eighteen percent. These are planning projections, not results we claim to have achieved. The frontier shows which additional spending produces a better policy outcome, and which combinations are dominated.”

**1:20–1:45 — Interaction; select rail disruption, then resilience.**

“Now assume an eighty-five-percent loss of rail service rate. The preferred actions and outcomes change. We can prioritize resilience, compare the result, and inspect the same selected portfolio under other disruptions. Nothing here relies on a fixed improvement percentage.”

**1:45–2:15 — Evidence; show holdouts and sample labels.**

“We keep evidence types separate. Eight actual matches anchor the event case. All organizer shards were scanned, but their transformed historical samples are context, not actual FIFA travel origins. Current transport geometry is also labelled. Our holdout test predicts one match from the other seven. Rideshare's large error tells us exactly where more measurement is needed.”

**2:15–2:40 — Uncertainty and feasibility.**

“We test eighty-one assumption combinations, disclose every intervention assumption, and list the proposed owner, lead time, approval dependency and success measure. The ranges are sensitivity scenarios, not confidence intervals. This makes the next field test specific and reviewable.”

**2:40–3:00 — Close; download brief.**

“EventFlow turns crowd evidence into a costed action plan. Its legacy is a repeatable planning process for future stadium events. Our next milestone is an operator-reviewed pilot, measured against a later event. The decision brief gives reviewers the actions, evidence and limitations in one place.”

## Recording checklist

Use the NY/NJ homepage. Rehearse the selector changes before recording; restore $500,000 / Balanced / Normal at the start. Keep narration in English, show the source register, and never call modelled reductions observed savings. Export the matching brief. This file is a script; it is not a recorded video or a submitted entry.
