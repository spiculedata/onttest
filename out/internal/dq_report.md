# Data quality report (internal)

Run `run_20261112T032234873270Z` · status **ok** · FieldTrax refreshed: True · workbook sha256 `ab3e12e0b397…`

**12 errors, 39 warnings, 265 info** from 112 checks (61 rule, 51 contract). 29 checks have hits.

## Scorecard

| Table | Records | With an error | With an error or warning | Clean % |
|---|---|---|---|---|
| clean.machine_lines | 104 | 0 | 20 | 80.8 |
| clean.hires | 63 | 0 | 7 | 88.9 |
| clean.projects | 6 | 0 | 0 | 100.0 |
| clean.rate_card | 8 | 0 | 0 | 100.0 |
| clean.devices | 88 |  | 16 | 81.8 |
| clean.readings | 4776 |  | 20 | 99.6 |

## Checks with hits

| Check | Severity | Entity | Hits | Previous run | Rule |
|---|---|---|---|---|---|
| RD003 | error | reading | 9 | 9 | Engine hours never go backwards |
| RD004 | error | reading | 3 | 0 | Engine hours do not grow faster than the clock |
| DV002 | warning | device | 3 | 3 | Every device is linked to a register machine |
| DV004 | warning | device | 1 | 0 | Device name agrees with the linked machine |
| DV008 | warning | device | 1 | 0 | Devices are still listed by FieldTrax |
| DV012 | warning | device | 3 | 3 | A tracker that matches no machine is not running |
| HR001 | warning | hire | 1 | 1 | A hire line is not an exact copy of an earlier line |
| HR016 | warning | hire | 5 | 5 | Reading a date month-first would not change whether the hire is open |
| MC003 | warning | machine | 4 | 4 | Every machine has a VIN |
| MC009 | warning | machine | 2 | 2 | Capital cost is a number |
| MC012 | warning | machine | 2 | 2 | A disposed machine was not built in the register's own year |
| MC014 | warning | machine | 9 | 10 | Every working machine has a FieldTrax tracker |
| MC015 | warning | machine | 4 | 4 | An operator mobile belongs to one machine |
| VC001 | warning | vocabulary | 3 | 3 | Term mappings that are judgement calls or typo matches are confirmed |
| WB009 | warning | workbook | 1 | 1 | Typed grand total equals the sum of all lines |
| DV006 | info | device | 3 | 3 | Replaced trackers are recorded as retired |
| DV007 | info | device | 7 | 7 | Devices reporting in seconds are converted to hours |
| HR005 | info | hire | 1 | 1 | Start of TBA means not started |
| HR008 | info | hire | 12 | 12 | Day/month order is read Australian-style |
| HR010 | info | hire | 19 | 19 | Blank GST is defaulted by business |
| HR012 | info | hire | 21 | 21 | Projects given by name or bare number are resolved to a code |
| HR015 | info | hire | 4 | 4 | Struck-through lines are loaded as cancelled |
| MC004 | info | machine | 4 | 4 | VINs typed in lower case or with spaces are normalised |
| MC010 | info | machine | 15 | 15 | Capital cost typed as text is read as a number |
| MC013 | info | machine | 46 | 46 | Make and model are known |
| RD001 | info | reading | 43 | 43 | Repeated readings at the same instant are kept once |
| RD006 | info | reading | 87 | 87 | Reading timestamps with an offset are normalised to UTC |
| WB004 | info | workbook | 2 | 2 | Hidden tabs, columns and rows are read, not skipped |
| WB005 | info | workbook | 1 | 1 | Cell comments are captured as data |

## Checks whose hit count moved since the previous run

| Check | Before | Now | Rule |
|---|---|---|---|
| DV004 | 0 | 1 | Device name agrees with the linked machine |
| DV008 | 0 | 1 | Devices are still listed by FieldTrax |
| MC014 | 10 | 9 | Every working machine has a FieldTrax tracker |
| RD004 | 0 | 3 | Engine hours do not grow faster than the clock |

## New issues since the previous run

| Severity | Check | Record | Tab | Row | Message |
|---|---|---|---|---|---|
| warning | DV004 | ftx_4a5aa7c0 | FieldTrax |  | Linked to NH TP-06 on the register |
| warning | DV008 | ftx_a023c823 | FieldTrax |  | Not in the FieldTrax device list since 2026-11-12 03:22 UTC; kept with its readings |
| error | RD004 | ftx_4a5aa7c0 | FieldTrax |  | +7.7 h in 6.0 h elapsed at 2026-10-18 08:00 UTC (the reading before it arrived late, in a later FieldTrax pull) |
| error | RD004 | ftx_4d04b0fe | FieldTrax |  | +8.0 h in 6.0 h elapsed at 2026-10-18 08:00 UTC (the reading before it arrived late, in a later FieldTrax pull) |
| error | RD004 | ftx_5bb307c6 | FieldTrax |  | +6.5 h in 6.0 h elapsed at 2026-10-18 08:00 UTC (the reading before it arrived late, in a later FieldTrax pull) |
| info | RD006 | ftx_353c03fb | FieldTrax |  | 32 readings converted to UTC |
| info | RD006 | ftx_4a5aa7c0 | FieldTrax |  | 33 readings converted to UTC |
| info | RD006 | ftx_4d04b0fe | FieldTrax |  | 31 readings converted to UTC |
| info | RD006 | ftx_5bb307c6 | FieldTrax |  | 36 readings converted to UTC |
| info | RD006 | ftx_68e0da6a | FieldTrax |  | 27 readings converted to UTC |
| info | RD006 | ftx_76d59116 | FieldTrax |  | 22 readings converted to UTC |
| info | RD006 | ftx_93808e74 | FieldTrax |  | 29 readings converted to UTC |
| info | RD006 | ftx_a3c87e47 | FieldTrax |  | 27 readings converted to UTC |
| info | RD006 | ftx_b670aa5d | FieldTrax |  | 31 readings converted to UTC |
| info | RD006 | ftx_bd118415 | FieldTrax |  | 27 readings converted to UTC |
| info | RD006 | ftx_c20f4e57 | FieldTrax |  | 20 readings converted to UTC |
| info | RD006 | ftx_f8271656 | FieldTrax |  | 29 readings converted to UTC |

## Resolved since the previous run

| Severity | Check | Record | Tab | Row | Message |
|---|---|---|---|---|---|
| warning | MC014 | mch_rpuh6pnv5uuefyy5l | BE Plant | 27 | BE SK-05 (available) has no FieldTrax device |
| info | RD006 | ftx_353c03fb | FieldTrax |  | 31 readings converted to UTC |
| info | RD006 | ftx_4a5aa7c0 | FieldTrax |  | 32 readings converted to UTC |
| info | RD006 | ftx_4d04b0fe | FieldTrax |  | 30 readings converted to UTC |
| info | RD006 | ftx_5bb307c6 | FieldTrax |  | 35 readings converted to UTC |
| info | RD006 | ftx_68e0da6a | FieldTrax |  | 26 readings converted to UTC |
| info | RD006 | ftx_76d59116 | FieldTrax |  | 21 readings converted to UTC |
| info | RD006 | ftx_93808e74 | FieldTrax |  | 28 readings converted to UTC |
| info | RD006 | ftx_a3c87e47 | FieldTrax |  | 26 readings converted to UTC |
| info | RD006 | ftx_b670aa5d | FieldTrax |  | 30 readings converted to UTC |
| info | RD006 | ftx_bd118415 | FieldTrax |  | 26 readings converted to UTC |
| info | RD006 | ftx_c20f4e57 | FieldTrax |  | 19 readings converted to UTC |
| info | RD006 | ftx_f8271656 | FieldTrax |  | 28 readings converted to UTC |

## Row accounting (nothing dropped)

| Tab | State | Hidden columns | Disposition | Rows |
|---|---|---|---|---|
| BE Plant | visible | K | blank | 1 |
| BE Plant | visible | K | header | 1 |
| BE Plant | visible | K | record | 58 |
| BE Plant | visible | K | subtotal | 8 |
| BE Plant | visible | K | title | 2 |
| BE Plant | visible | K | total | 1 |
| Hires 25-26 | visible |  | header | 1 |
| Hires 25-26 | visible |  | record | 63 |
| NH Fleet | visible |  | blank | 3 |
| NH Fleet | visible |  | header | 1 |
| NH Fleet | visible |  | record | 46 |
| Projects | visible |  | header | 1 |
| Projects | visible |  | record | 6 |
| READ ME | visible |  | blank | 1 |
| READ ME | visible |  | documentation | 13 |
| _old rates | hidden |  | header | 1 |
| _old rates | hidden |  | record | 8 |

## FieldTrax syncs

| run_id | devices_listed | readings_received | new_readings | new_device_versions | errors | requests | rate_limited | unavailable | reauths |
|---|---|---|---|---|---|---|---|---|---|
| run_20261112T032151257875Z | 87 | 4639 | 4639 | 87 | 0 | 201 | 18 | 5 | 4 |
| run_20261112T032213289748Z | 87 | 4639 | 0 | 0 | 0 | 201 | 18 | 5 | 4 |
| run_20261112T032234873270Z | 87 | 4763 | 180 | 3 | 0 | 200 | 17 | 6 | 4 |
