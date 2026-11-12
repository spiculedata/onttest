# For Priya: things the pipeline could not resolve

Register as of 2026-10-31. Pipeline run `run_20261112T164536083074Z`. 37 item(s).
Each item names the tab and row it came from. Nothing listed here was dropped; the record is in the database with the value as written.

## DV002 (warning): Every device is linked to a register machine

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 1 | FieldTrax | ftx_5927a6bf | Spare tracker 1 | Device matches no machine on the register |
| 2 | FieldTrax | ftx_b1d282cc | Spare tracker 3 | Device matches no machine on the register |
| 3 | FieldTrax | ftx_c10c3e89 | Spare tracker 2 | Device matches no machine on the register |

## DV012 (warning): A tracker that matches no machine is not running

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 4 | FieldTrax | ftx_5927a6bf | Spare tracker 1 | Spare tracker 1 ran 28.0 h between 18 and 31 Oct (reporting since 22 Oct). It is fitted to a machine that is working. |
| 5 | FieldTrax | ftx_b1d282cc | Spare tracker 3 | Spare tracker 3 ran 21.3 h between 18 and 31 Oct (reporting since 22 Oct). It is fitted to a machine that is working. |
| 6 | FieldTrax | ftx_c10c3e89 | Spare tracker 2 | Spare tracker 2 ran 15.3 h between 18 and 31 Oct (reporting since 22 Oct). It is fitted to a machine that is working. |

## HR001 (warning): A hire line is not an exact copy of an earlier line

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 7 | Hires 25-26!15 | H-1014 |  | Identical to row 14; is this one hire or two? |

## HR016 (warning): Reading a date month-first would not change whether the hire is open

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 8 | Hires 25-26!4 | H-1015 | 2026-10-11 | Start 11 Oct 2026 (Excel date); read month-first it is 10 Nov 2026 and the hire would not be open on 31 Oct. |
| 9 | Hires 25-26!7 | H-1046 | 2026-03-11 | Start 11 Mar 2026 (Excel date); read month-first it is 3 Nov 2026 and the hire would not be open on 31 Oct. |
| 10 | Hires 25-26!36 | H-1010 | 2026-11-10 | Off-hire 10 Nov 2026 (Excel date); read month-first it is 11 Oct 2026 and the hire would not be open on 31 Oct. |
| 11 | Hires 25-26!42 | H-1035 | 12/07/26 | Start 12 Jul 2026 (typed d/m/y); read month-first it is 7 Dec 2026 and the hire would not be open on 31 Oct. |
| 12 | Hires 25-26!48 | H-1042 | 2026-07-11 | Start 11 Jul 2026 (Excel date); read month-first it is 7 Nov 2026 and the hire would not be open on 31 Oct. |

## MC003 (warning): Every machine has a VIN

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 13 | NH Fleet!2 | EX-06 |  | VIN blank; FieldTrax tracker on rego CL164X reports VIN AC6KD84NB3BJGE4YM |
| 14 | NH Fleet!14 | LV-07 |  | VIN blank; FieldTrax tracker on rego GL197T reports VIN XDTSEJAC8P8JUF0PB |
| 15 | NH Fleet!25 | TP-05 |  | VIN blank; FieldTrax tracker on rego AQ183S reports VIN BLK0TT4CWJ58R3HFJ |
| 16 | NH Fleet!37 | SK-03 |  | VIN blank; FieldTrax tracker on rego DM172T reports VIN R5BWNX0CNYKZVFMMC |

## MC009 (warning): Capital cost is a number

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 17 | BE Plant!23 | SK-01 | TBC | Capital cost is not a number |
| 18 | BE Plant!50 | RL-01 | TBC | Capital cost is not a number |

## MC012 (warning): A disposed machine was not built in the register's own year

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 19 | BE Plant!25 | SK-03 | 2026 / Disposed | Disposed in the same year as its Year column |
| 20 | BE Plant!32 | WC-03 | 2026 / Disposed | Disposed in the same year as its Year column |

## MC014 (warning): Every working machine has a FieldTrax tracker

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 21 | BE Plant!46 | mch_whlgxb0zdftg0m0z1 | BE TP-10 | BE TP-10 (on_project) has no FieldTrax device |
| 22 | BE Plant!67 | mch_phya2f7974j2lm9rp | BE GN-01 | BE GN-01 (workshop) has no FieldTrax device |
| 23 | BE Plant!68 | mch_4dsv1f53thmn1ncy8 | BE GN-02 | BE GN-02 (available) has no FieldTrax device |
| 24 | BE Plant!69 | mch_pwejcmb6j48juet25 | BE GN-03 | BE GN-03 (on_project) has no FieldTrax device |
| 25 | NH Fleet!13 | mch_un809z456wru10w3v | NH TP-07 | NH TP-07 (on_project) has no FieldTrax device |
| 26 | NH Fleet!15 | mch_7xb9335vsf0sgcymm | NH LV-02 | NH LV-02 (on_project) has no FieldTrax device |
| 27 | NH Fleet!18 | mch_6ch8daxhab22y54ku | NH RL-01 | NH RL-01 (on_project) has no FieldTrax device |
| 28 | NH Fleet!35 | mch_1ksvx6accm95xwa5h | NH GN-01 | NH GN-01 (available) has no FieldTrax device |
| 29 | NH Fleet!40 | mch_hnfu9ck4nz0jyut66 | NH GN-02 | NH GN-02 (on_project) has no FieldTrax device |

## MC015 (warning): An operator mobile belongs to one machine

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 30 | BE Plant!23 | SK-01 | 0491 555 646 | BE LV-03 and BE SK-01 share this operator mobile |
| 31 | BE Plant!46 | TP-10 | 0491 555 341 | BE LV-08 and BE TP-10 share this operator mobile |
| 32 | BE Plant!58 | LV-03 | 0491 555 646 | BE LV-03 and BE SK-01 share this operator mobile |
| 33 | BE Plant!63 | LV-08 | 0491 555 341 | BE LV-08 and BE TP-10 share this operator mobile |

## VC001 (warning): Term mappings that are judgement calls or typo matches are confirmed

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 34 | Hires 25-26!25 | Hire Well | Hire Well | 'Hire Well' read as supplier 'Hirewell Pty Ltd' by inferred alias on 5 line(s). Please confirm. |
| 35 | NH Fleet!2 | On job | On job | 'On job' read as status 'on_project' by inferred alias on 21 line(s). Please confirm. |
| 36 | NH Fleet!29 | Repairs | Repairs | 'Repairs' read as status 'workshop' by inferred alias on 4 line(s). Please confirm. |

## WB009 (warning): Typed grand total equals the sum of all lines

| # | Where | Record | Written as | What we found |
|---|---|---|---|---|
| 37 | BE Plant!71 | capital cost total | 10276000 | Typed 10276000.0 but lines sum to 10361000.0; typed subtotals sum to 10361000.0 |
