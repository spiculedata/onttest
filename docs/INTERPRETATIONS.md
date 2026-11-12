# How the rules were interpreted

The READ ME rules and the rules for the numbers are followed as written where they are clear.
Where a rule could be read more than one way, this is the reading taken, the alternative, and
where it shows up. "Flagged" means the choice is visible to Priya (her list or the screen), not
buried in code.

## READ ME rules

| Rule (as written) | How it was applied | Open to interpretation because | Flagged? |
|---|---|---|---|
| Rates: day unless Basis says wk or mth; week = 5 working days, month = 22 | Day rate = rate ÷ 1, 5 or 22. Rate text carrying its own unit ("5435/wk") must agree with Basis | A monthly hire ended early may still be charged the full month | HR009 if the unit disagrees; every monthly proposal warns that the month may be charged in full |
| GST: go by the GST column; blank = BE inc, NH ex | Column wins. Blank → business default. Anything unreadable gives no rate rather than a guess | "Blank" could include junk text; we treat only empty as blank | HR010 (info) lists every defaulted line; an unreadable GST fails the hire contract |
| Struck-through hire lines were cancelled | A line counts as cancelled only if every filled cell is struck | A partly struck line could be an edit, not a cancellation | WB006 if partly struck; WB007 if strike appears on another tab |
| Off-hire blank, ongoing or TBA = still on hire; Start TBA = not started | Applied as written. An off-hire date after 31 Oct also counts as still on hire | A future off-hire date could be read as "already arranged to end" | The proposal shows the planned off-hire date and the saving up to it |
| Yard and Available mean the same; Sold and Disposed too | Applied as written | Not stated: NH's "On job" and "Repairs" | "On job" = on project and "Repairs" = workshop are marked *inferred* and sent to Priya (VC001) |
| Fleet numbers aren't unique across the businesses | Uniqueness is checked within a business only | | MC002 |
| Moved machines keep a line on the old sheet; VIN or rego says it's the same machine | Only a "Transferred to …" line is linked to the line sharing its VIN or rego. The receiving sheet's line is the current record | Read loosely, any two lines sharing a VIN would merge. That lets one typo make a machine disappear, so it is not done | MC005 if two live lines share a VIN or rego; MC007/MC008 check each transfer pair |
| Yard words (20T Digger, Bobcat, T&D, Ute, …) | Held as master data in `mdm/aliases.csv`, together with spellings the READ ME doesn't list (Tipper truck, Smooth drum roller, regional words like bakkie) | Words not in the READ ME need a call | Each alias has a basis (`readme`, `variant`, `regional`, `inferred`); inferred and typo matches go to Priya (VC001); unknown words are never guessed (VC002) |
| "Bobcat" | Means Skid steer in a type column, and the maker in the Make column | Brand used as a type | Mapped only in type columns |
| Don't trust the totals | Subtotals and totals are never loaded as data; they are reconciled against the lines | | WB008/WB009: the BE total is $85,000 short of its lines |
| Hires 25-26 is all external hire for both businesses | BU column taken as the business; checked against the project's business | | HR011 |

## The rules for the numbers

| Rule (as given) | How it was applied | Open to interpretation because | Flagged? |
|---|---|---|---|
| As of 31 Oct 2026, end of day, AEST | Fixed UTC+10 for both businesses: the window is 17 Oct 14:00 to 31 Oct 13:59:59 UTC | NSW was on daylight saving (AEDT, UTC+11) in late October and NH's depots are in NSW, so NH's local window would be an hour earlier at both ends (17 Oct 13:00 to 31 Oct 12:59:59 UTC). Checked, and recomputed on every screen build: FieldTrax reports at 08:00 and 22:00 UTC, plus back-dated 02:00 UTC readings that arrived with the advance. None falls in either edge hour, so every machine's idle result is the same under both readings. Hire dates are whole days and unaffected | Yes: "Time zone" under "How this was worked out" on the screen |
| Answer before /__advance; only after_advance uses the world after it | The "before" view is rebuilt from the sync history: only device versions and readings first seen up to the last sync before the advance | The advance is spotted as the sync that brought new data after an earlier one did | Screen has a before/after switch; the answer is identical in both |
| Open hire: start on or before 31 Oct, off-hire after it or none | As written, on top of the READ ME rules. All dates are read day-first (02/04/26 = 2 Apr), whether typed as text or stored as Excel dates | Excel dates are stored unambiguously, but whoever typed them may have used month-first. Five dates would change whether a hire is open on 31 Oct if read month-first: H-1015, H-1046 and H-1042 are in proposals ($3,346.36 a day), and H-1010 and H-1035 would close | HR016 (warning, on Priya's list and screen) lists only the swaps that change the answer; HR008 (info) lists every ambiguous text date |
| Idle: reads Available or Yard | Read from the machine's current register line, not an old "Transferred to" line | | |
| …and FieldTrax confirms under 1.0 engine hour, 18 Oct 00:00 – 31 Oct 23:59 AEST | Strictly under 1.0. Only pairs of consecutive readings both inside the window count, so a pair that spans 18 Oct 00:00 adds nothing | Counting the pair that crosses the window start would add up to one reading gap of hours | Window and threshold are shown on the screen |
| Hours run = sum of positive increases between consecutive readings, across all of the machine's devices | Per device, after converting seconds to hours and keeping one reading per instant ("Z" and "+10:00" copies of the same moment). Meter resets add nothing. Retired trackers count | | RD001/RD003 explain duplicates and resets |
| A machine with no device is unconfirmed, never idle | As written. A device with fewer than two readings in the window is treated the same way | The rule doesn't say what a device with no data means. We read "FieldTrax confirms" as needing readings | SK-05 (no device before the advance, no window readings after) is shown unconfirmed |
| Replaceable: same category, project in the same state as the depot | Category through the MDM; depot state from the MDM site reference (Toowoomba and Brisbane Yard QLD, Newcastle and Dubbo NSW) | Depot states are inferred from the town names; the register doesn't give them | Interstate idle machines are named but not counted |
| Choose the pairs that save the most | Within a category and state every idle machine can take every open hire, so giving them to the dearest hires is the maximum. Confirmed-idle machines first; unconfirmed ones then take the next-dearest, counted separately | | Confirmed and unconfirmed totals are separate on the screen |
| Dollars per day excluding GST | As per the READ ME rate rules above | Cartage, running costs and notice periods aren't in the data | Every proposal lists them as unconfirmed |

## Not in any rule, decided here

- **A type with no size is not guessed.** "Digger" or "Excavator" on its own matches no category (VC002) rather than defaulting to 20t; only sized forms (20T Digger, EX5, …) map.
- **Short codes are never typo-matched.** GST, rate basis, business and unit values must match exactly; "GST" alone would otherwise typo-match "ex".
- **Running spare trackers matter.** Spare trackers 1–3 match no register machine but logged 15–28 h from 18 to 31 Oct, so each is on something working. If one is on an untracked Available machine (SK-05, GN-02, GN-01), that machine is not idle (DV012, on Priya's screen).
- **Telemetry detail goes to the data team.** Meter resets, late or duplicate readings, renamed or vanished trackers and sync status are on the internal console; Priya gets the business question they raise.

- **H-1014 appears twice, identical in every cell (rows 14 and 15).** Counted once and asked about (HR001). It might be two machines.
- **"Hire Well" is read as Hirewell Pty Ltd.** Inferred, so it goes to Priya.
- **Priya signs each proposal to end a hire.** The register has no approval rule; the READ ME names Priya N. as Group Plant Manager and keeper of the register, and the project owner confirmed she signs. Shown on every proposal and in `answers.json` (`who_signs`).
- **The 11 machines that read Available or Yard but ran 1 hour or more are not offered as replacements.** Following the rule, the tracker wins. The register may be out of date.
