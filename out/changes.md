# FieldTrax sync and record changes

Run `run_20261112T164536083074Z`.

## FieldTrax sync

Not refreshed this run: skipped by request. Devices and readings come from the last successful sync.

## What changed since the previous run

| Table | Added | Removed | Changed (records) | Recomputed only (records) |
|---|---|---|---|---|
| hires | 0 | 0 | 22 | 0 |

*Recomputed* = a value worked out from others (e.g. the gap to the previous reading, a device's version count) changed because something it depends on changed.

### hires

| Change | Record | Field | Was | Now |
|---|---|---|---|---|
| changed | Hires 25-26 \| 14 | day_rate_ex_gst | 395.66 | 395.661157025 |
| changed | Hires 25-26 \| 15 | day_rate_ex_gst | 395.66 | 395.661157025 |
| changed | Hires 25-26 \| 16 | day_rate_ex_gst | 1223.64 | 1223.636363636 |
| changed | Hires 25-26 \| 17 | day_rate_ex_gst | 572.73 | 572.727272727 |
| changed | Hires 25-26 \| 18 | day_rate_ex_gst | 759.09 | 759.090909091 |
| changed | Hires 25-26 \| 20 | day_rate_ex_gst | 1290.91 | 1290.909090909 |
| changed | Hires 25-26 \| 25 | day_rate_ex_gst | 872.73 | 872.727272727 |
| changed | Hires 25-26 \| 26 | day_rate_ex_gst | 909.09 | 909.090909091 |
| changed | Hires 25-26 \| 27 | day_rate_ex_gst | 568.18 | 568.181818182 |
| changed | Hires 25-26 \| 28 | day_rate_ex_gst | 1354.55 | 1354.545454545 |
| changed | Hires 25-26 \| 29 | day_rate_ex_gst | 163.64 | 163.636363636 |
| changed | Hires 25-26 \| 35 | day_rate_ex_gst | 1341.14 | 1341.136363636 |
| changed | Hires 25-26 \| 38 | day_rate_ex_gst | 1718.18 | 1718.181818182 |
| changed | Hires 25-26 \| 40 | day_rate_ex_gst | 1197.27 | 1197.272727273 |
| changed | Hires 25-26 \| 41 | day_rate_ex_gst | 1090.91 | 1090.909090909 |
| changed | Hires 25-26 \| 48 | day_rate_ex_gst | 151.82 | 151.818181818 |
| changed | Hires 25-26 \| 49 | day_rate_ex_gst | 890.91 | 890.909090909 |
| changed | Hires 25-26 \| 51 | day_rate_ex_gst | 1345.45 | 1345.454545455 |
| changed | Hires 25-26 \| 61 | day_rate_ex_gst | 240.91 | 240.909090909 |
| changed | Hires 25-26 \| 7 | day_rate_ex_gst | 1554.55 | 1554.545454545 |
| changed | Hires 25-26 \| 8 | day_rate_ex_gst | 925.68 | 925.681818182 |
| changed | Hires 25-26 \| 9 | day_rate_ex_gst | 988.18 | 988.181818182 |

## Device to machine matching

Matched by VIN first, then rego, then business + fleet number in the device name.

- rego: 7
- vin: 78
- no match: 3

### Devices that match nothing (3)

| Device | Name | VIN | Rego | Still listed | Why |
|---|---|---|---|---|---|
| ftx_5927a6bf | Spare tracker 1 | S0SC01RFB9VEG4A01 | ZZZ0 | yes | VIN, rego and name match no line on BE Plant or NH Fleet |
| ftx_b1d282cc | Spare tracker 3 | RY05ZKWWMR5LTTE2C | ZZZ2 | yes | VIN, rego and name match no line on BE Plant or NH Fleet |
| ftx_c10c3e89 | Spare tracker 2 | AB3D14EK3B1JNU7Z3 | ZZZ1 | yes | VIN, rego and name match no line on BE Plant or NH Fleet |

### Working machines with no device (9)

| Machine | Business | Fleet no | Status | Register line |
|---|---|---|---|---|
| mch_phya2f7974j2lm9rp | BE | GN-01 | workshop | BE Plant!67 |
| mch_4dsv1f53thmn1ncy8 | BE | GN-02 | available | BE Plant!68 |
| mch_pwejcmb6j48juet25 | BE | GN-03 | on_project | BE Plant!69 |
| mch_whlgxb0zdftg0m0z1 | BE | TP-10 | on_project | BE Plant!46 |
| mch_1ksvx6accm95xwa5h | NH | GN-01 | available | NH Fleet!35 |
| mch_hnfu9ck4nz0jyut66 | NH | GN-02 | on_project | NH Fleet!40 |
| mch_7xb9335vsf0sgcymm | NH | LV-02 | on_project | NH Fleet!15 |
| mch_6ch8daxhab22y54ku | NH | RL-01 | on_project | NH Fleet!18 |
| mch_un809z456wru10w3v | NH | TP-07 | on_project | NH Fleet!13 |
