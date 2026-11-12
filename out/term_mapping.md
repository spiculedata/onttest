# Term mapping (MDM)

Every coded value found in the workbook and what it was normalised to. Edit `mdm/aliases.csv` to confirm or correct a mapping; the next run applies it.

| Domain | Written as | Normalised to | How | Lines | Confirm? |
|---|---|---|---|---|---|
| business | BE | BE | canonical | 27 |  |
| business | NH | NH | canonical | 36 |  |
| category | 20T Digger | Excavator 20t | readme | 6 |  |
| category | 20T Excavator | Excavator 20t | variant | 4 |  |
| category | EX20 | Excavator 20t | readme | 7 |  |
| category | Excavator 20t | Excavator 20t | canonical | 15 |  |
| category | 5T Digger | Excavator 5t | readme | 5 |  |
| category | 5T Excavator | Excavator 5t | variant | 3 |  |
| category | Excavator 5t | Excavator 5t | canonical | 11 |  |
| category | Generator | Generator | canonical | 9 |  |
| category | Genset | Generator | readme | 2 |  |
| category | Light vehicle | Light vehicle | canonical | 13 |  |
| category | Ute | Light vehicle | readme | 9 |  |
| category | Roller | Roller | canonical | 7 |  |
| category | Smooth drum | Roller | readme | 4 |  |
| category | Smooth drum roller | Roller | variant | 4 |  |
| category | Bobcat | Skid steer | readme | 7 |  |
| category | Skid steer | Skid steer | canonical | 9 |  |
| category | T&D | Tipper | readme | 8 |  |
| category | Tipper | Tipper | canonical | 20 |  |
| category | Tipper truck | Tipper | variant | 3 |  |
| category | Truck & dog | Tipper | readme | 9 |  |
| category | WC | Water cart | readme | 5 |  |
| category | Water cart | Water cart | canonical | 7 |  |
| category | Water truck | Water cart | readme | 8 |  |
| gst | ex | ex | canonical | 29 |  |
| gst | inc | inc | canonical | 15 |  |
| rate_basis | day | day | canonical | 45 |  |
| rate_basis | mth | mth | canonical | 6 |  |
| rate_basis | wk | wk | canonical | 12 |  |
| site | Brisbane Yard | Brisbane Yard | canonical | 28 |  |
| site | Dubbo | Dubbo | canonical | 19 |  |
| site | Newcastle | Newcastle | canonical | 27 |  |
| site | Toowoomba | Toowoomba | canonical | 30 |  |
| status | Available | available | canonical ('available') | 21 |  |
| status | Yard | available | readme | 15 |  |
| status | Disposed | disposed | canonical ('disposed') | 7 |  |
| status | Sold | disposed | readme | 1 |  |
| status | On job | on_project | inferred | 21 | yes |
| status | On project | on_project | canonical ('on_project') | 22 |  |
| status | Transferred to BE Jul-26 | transferred | readme ('pattern 'Transferred to <BE\|NH> <period>' (READ ME: moved machines keep a line)') | 5 |  |
| status | Repairs | workshop | inferred | 4 | yes |
| status | Workshop | workshop | canonical ('workshop') | 8 |  |
| supplier | HIREWELL PTY LTD | Hirewell Pty Ltd | canonical ('Hirewell Pty Ltd') | 7 |  |
| supplier | Hire Well | Hirewell Pty Ltd | inferred | 5 | yes |
| supplier | Hirewell | Hirewell Pty Ltd | canonical ('Hirewell Pty Ltd') | 11 |  |
| supplier | Murrawa | Murrawa Equipment | variant | 11 |  |
| supplier | Murrawa Equipment | Murrawa Equipment | canonical | 10 |  |
| supplier | SOUTHGATE PLANT | Southgate Plant Hire | variant ('Southgate Plant') | 3 |  |
| supplier | Southgate | Southgate Plant Hire | variant | 3 |  |
| supplier | Southgate Plant Hire | Southgate Plant Hire | canonical | 4 |  |
| supplier | TIDAL EARTHMOVING P/L | Tidal Earthmoving Pty Ltd | canonical ('Tidal Earthmoving Pty Ltd') | 5 |  |
| supplier | Tidal Earthmoving | Tidal Earthmoving Pty Ltd | canonical ('Tidal Earthmoving Pty Ltd') | 4 |  |