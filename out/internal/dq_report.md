# Data quality report (internal)

Run `run_20261112T164536083074Z` · status **ok** · FieldTrax refreshed: False · workbook sha256 `ab3e12e0b397…`

**12 errors, 40 warnings, 265 info** from 112 checks (61 rule, 51 contract). 30 checks have hits.

## Scorecard

| Table | Records | With an error | With an error or warning | Clean % |
|---|---|---|---|---|
| clean.machine_lines | 104 | 0 | 20 | 80.8 |
| clean.hires | 63 | 0 | 7 | 88.9 |
| clean.projects | 6 | 0 | 0 | 100.0 |
| clean.rate_card | 8 | 0 | 0 | 100.0 |
| clean.devices | 88 |  | 17 | 80.7 |
| clean.readings | 4776 |  | 21 | 99.6 |

## Checks with hits

| Check | Severity | Entity | Hits | Previous run | Rule |
|---|---|---|---|---|---|
| RD003 | error | reading | 9 | 9 | Engine hours never go backwards |
| RD004 | error | reading | 3 | 3 | Engine hours do not grow faster than the clock |
| DV001 | warning | device | 1 | 0 | FieldTrax data was refreshed this run |
| DV002 | warning | device | 3 | 3 | Every device is linked to a register machine |
| DV004 | warning | device | 1 | 1 | Device name agrees with the linked machine |
| DV008 | warning | device | 1 | 1 | Devices are still listed by FieldTrax |
| DV012 | warning | device | 3 | 3 | A tracker that matches no machine is not running |
| HR001 | warning | hire | 1 | 1 | A hire line is not an exact copy of an earlier line |
| HR016 | warning | hire | 5 | 5 | Reading a date month-first would not change whether the hire is open |
| MC003 | warning | machine | 4 | 4 | Every machine has a VIN |
| MC009 | warning | machine | 2 | 2 | Capital cost is a number |
| MC012 | warning | machine | 2 | 2 | A disposed machine was not built in the register's own year |
| MC014 | warning | machine | 9 | 9 | Every working machine has a FieldTrax tracker |
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
| DV001 | 0 | 1 | FieldTrax data was refreshed this run |

## New issues since the previous run

| Severity | Check | Record | Tab | Row | Message |
|---|---|---|---|---|---|
| warning | DV001 | fieldtrax | FieldTrax |  | Using the previous FieldTrax snapshot |

## Resolved since the previous run

_None._

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
