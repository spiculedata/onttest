# Master data report (internal)

53 distinct written forms across 7 domains. 3 need a decision; 57 aliases in mdm/aliases.csv were not seen in this workbook.

## Coverage by domain

| Domain | Written forms | Lines | Lines mapped without review | % without review |
|---|---|---|---|---|
| business | 2 | 63 | 63 | 100.0 |
| category | 23 | 175 | 175 | 100.0 |
| gst | 2 | 44 | 44 | 100.0 |
| rate_basis | 3 | 63 | 63 | 100.0 |
| site | 4 | 104 | 104 | 100.0 |
| status | 9 | 104 | 79 | 76.0 |
| supplier | 10 | 63 | 58 | 92.1 |

## Needs a decision (inferred, typo match or unmapped)

| Domain | Written as | Mapped to | Basis | Score | Nearest | Lines | Where |
|---|---|---|---|---|---|---|---|
| status | On job | on_project | inferred | 1.0 |  | 21 | NH Fleet!2, NH Fleet!6, NH Fleet!7, NH Fleet!8, NH Fleet!9, NH Fleet!11, NH Fleet!12, NH Fleet!13, NH Fleet!15, NH Fleet!16, NH Fleet!17, NH Fleet!18, NH Fleet!20, NH Fleet!24, NH Fleet!28, NH Fleet!31, NH Fleet!32, NH Fleet!33, NH Fleet!34, NH Fleet!38, NH Fleet!40 |
| status | Repairs | workshop | inferred | 1.0 |  | 4 | NH Fleet!29, NH Fleet!37, NH Fleet!39, NH Fleet!43 |
| supplier | Hire Well | Hirewell Pty Ltd | inferred | 1.0 |  | 5 | Hires 25-26!25, Hires 25-26!31, Hires 25-26!50, Hires 25-26!53, Hires 25-26!61 |

## Everything seen

| Domain | Written as | Canonical | Basis | Matched alias | Lines |
|---|---|---|---|---|---|
| business | BE | BE | canonical | BE | 27 |
| business | NH | NH | canonical | NH | 36 |
| category | 20T Digger | Excavator 20t | readme | 20T Digger | 6 |
| category | 20T Excavator | Excavator 20t | variant | 20T Excavator | 4 |
| category | EX20 | Excavator 20t | readme | EX20 | 7 |
| category | Excavator 20t | Excavator 20t | canonical | Excavator 20t | 15 |
| category | 5T Digger | Excavator 5t | readme | 5T Digger | 5 |
| category | 5T Excavator | Excavator 5t | variant | 5T Excavator | 3 |
| category | Excavator 5t | Excavator 5t | canonical | Excavator 5t | 11 |
| category | Generator | Generator | canonical | Generator | 9 |
| category | Genset | Generator | readme | Genset | 2 |
| category | Light vehicle | Light vehicle | canonical | Light vehicle | 13 |
| category | Ute | Light vehicle | readme | Ute | 9 |
| category | Roller | Roller | canonical | Roller | 7 |
| category | Smooth drum | Roller | readme | Smooth drum | 4 |
| category | Smooth drum roller | Roller | variant | Smooth drum roller | 4 |
| category | Bobcat | Skid steer | readme | Bobcat | 7 |
| category | Skid steer | Skid steer | canonical | Skid steer | 9 |
| category | T&D | Tipper | readme | T&D | 8 |
| category | Tipper | Tipper | canonical | Tipper | 20 |
| category | Tipper truck | Tipper | variant | Tipper truck | 3 |
| category | Truck & dog | Tipper | readme | Truck & dog | 9 |
| category | WC | Water cart | readme | WC | 5 |
| category | Water cart | Water cart | canonical | Water cart | 7 |
| category | Water truck | Water cart | readme | Water truck | 8 |
| gst | ex | ex | canonical | ex | 29 |
| gst | inc | inc | canonical | inc | 15 |
| rate_basis | day | day | canonical | day | 45 |
| rate_basis | mth | mth | canonical | mth | 6 |
| rate_basis | wk | wk | canonical | wk | 12 |
| site | Brisbane Yard | Brisbane Yard | canonical | Brisbane Yard | 28 |
| site | Dubbo | Dubbo | canonical | Dubbo | 19 |
| site | Newcastle | Newcastle | canonical | Newcastle | 27 |
| site | Toowoomba | Toowoomba | canonical | Toowoomba | 30 |
| status | Available | available | canonical | available | 21 |
| status | Yard | available | readme | Yard | 15 |
| status | Disposed | disposed | canonical | disposed | 7 |
| status | Sold | disposed | readme | Sold | 1 |
| status | On job | on_project | inferred | On job | 21 |
| status | On project | on_project | canonical | on_project | 22 |
| status | Transferred to BE Jul-26 | transferred | readme | pattern 'Transferred to <BE\|NH> <period>' (READ ME: moved machines keep a line) | 5 |
| status | Repairs | workshop | inferred | Repairs | 4 |
| status | Workshop | workshop | canonical | workshop | 8 |
| supplier | HIREWELL PTY LTD | Hirewell Pty Ltd | canonical | Hirewell Pty Ltd | 7 |
| supplier | Hire Well | Hirewell Pty Ltd | inferred | Hire Well | 5 |
| supplier | Hirewell | Hirewell Pty Ltd | canonical | Hirewell Pty Ltd | 11 |
| supplier | Murrawa | Murrawa Equipment | variant | Murrawa | 11 |
| supplier | Murrawa Equipment | Murrawa Equipment | canonical | Murrawa Equipment | 10 |
| supplier | SOUTHGATE PLANT | Southgate Plant Hire | variant | Southgate Plant | 3 |
| supplier | Southgate | Southgate Plant Hire | variant | Southgate | 3 |
| supplier | Southgate Plant Hire | Southgate Plant Hire | canonical | Southgate Plant Hire | 4 |
| supplier | TIDAL EARTHMOVING P/L | Tidal Earthmoving Pty Ltd | canonical | Tidal Earthmoving Pty Ltd | 5 |
| supplier | Tidal Earthmoving | Tidal Earthmoving Pty Ltd | canonical | Tidal Earthmoving Pty Ltd | 4 |

## Aliases defined but not seen in this workbook

Kept on purpose for future spellings (regional words, typos seen elsewhere). Review if the list grows stale.

| Domain | Alias | Canonical | Basis |
|---|---|---|---|
| business | Brackenfield | BE | variant |
| business | Brackenfield Earthworks | BE | variant |
| business | Norland | NH | variant |
| business | Norland Haulage | NH | variant |
| category | EX5 | Excavator 5t | readme |
| category | Mini digger | Excavator 5t | regional |
| category | Mini excavator | Excavator 5t | regional |
| category | Gen set | Generator | variant |
| category | Genny | Generator | regional |
| category | Bakkie | Light vehicle | regional |
| category | LV | Light vehicle | variant |
| category | Pick-up | Light vehicle | regional |
| category | Pickup | Light vehicle | regional |
| category | Utility | Light vehicle | regional |
| category | Drum roller | Roller | variant |
| category | SD roller | Roller | variant |
| category | Smooth drum compactor | Roller | variant |
| category | Smooth roller | Roller | variant |
| category | Vibe roller | Roller | regional |
| category | Skid steer loader | Skid steer | variant |
| category | Skidsteer | Skid steer | variant |
| category | Dump truck | Tipper | regional |
| category | Tip truck | Tipper | regional |
| category | Water tanker | Water cart | regional |
| gst | +gst | ex | variant |
| gst | ex gst | ex | variant |
| gst | excl | ex | variant |
| gst | excluding | ex | variant |
| gst | plus gst | ex | variant |
| gst | inc gst | inc | variant |
| gst | incl | inc | variant |
| gst | incl gst | inc | variant |
| gst | including | inc | variant |
| rate_basis | d | day | variant |
| rate_basis | daily | day | variant |
| rate_basis | pd | day | variant |
| rate_basis | per day | day | variant |
| rate_basis | mo | mth | variant |
| rate_basis | month | mth | variant |
| rate_basis | monthly | mth | variant |
| rate_basis | per month | mth | variant |
| rate_basis | pm | mth | variant |
| rate_basis | per week | wk | variant |
| rate_basis | pw | wk | variant |
| rate_basis | w | wk | variant |
| rate_basis | week | wk | variant |
| rate_basis | weekly | wk | variant |
| site | Bris Yard | Brisbane Yard | variant |
| site | Brisbane | Brisbane Yard | variant |
| status | Written off | disposed | inferred |
| status | On site | on_project | inferred |
| status | In for service | workshop | inferred |
| unit | hours | h | variant |
| unit | hr | h | variant |
| unit | hrs | h | variant |
| unit | sec | s | variant |
| unit | seconds | s | variant |
