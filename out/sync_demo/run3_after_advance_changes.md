# FieldTrax sync and record changes

Run `run_20261112T032234873270Z`.

## FieldTrax sync

- Devices listed: 87; readings received: 4763
- New reading lines stored: 180; new device versions stored: 3
- Items that could not be stored or fetched: 0 (see dq checks DV009/DV010/DV011)
- Requests: 200 (rate-limited and retried: 17, unavailable and retried: 6, network errors retried: 0, unreadable pages retried: 0, signed in again: 4)

## What changed since the previous run

| Table | Added | Removed | Changed (records) | Recomputed only (records) |
|---|---|---|---|---|
| devices | 1 | 0 | 2 | 2 |
| readings | 180 | 0 | 0 | 12 |

*Recomputed* = a value worked out from others (e.g. the gap to the previous reading, a device's version count) changed because something it depends on changed.

### devices

| Change | Record | Field | Was | Now |
|---|---|---|---|---|
| added | ftx_2f57c61e (BE SK-05 Bobcat) |  |  |  |
| changed | ftx_4a5aa7c0 (NH TP-06 Hino - reassigned) | name | NH TP-06 Hino | NH TP-06 Hino - reassigned |
| changed | ftx_a023c823 (NH MX-03 Kubota) | is_listed | true | false |
| recomputed | ftx_4a5aa7c0 (NH TP-06 Hino - reassigned) | last_changed_at | 2026-11-12 03:21:51.375157+00:00 | 2026-11-12 03:22:34.977552+00:00 |
| recomputed | ftx_4a5aa7c0 (NH TP-06 Hino - reassigned) | name_suffix | Hino | Hino - reassigned |
| recomputed | ftx_4a5aa7c0 (NH TP-06 Hino - reassigned) | version_count | 1 | 2 |
| recomputed | ftx_a023c823 (NH MX-03 Kubota) | last_changed_at | 2026-11-12 03:21:51.375157+00:00 | 2026-11-12 03:22:34.977552+00:00 |
| recomputed | ftx_a023c823 (NH MX-03 Kubota) | version_count | 1 | 2 |

### readings

| Change | Field | Per device | Readings from | to | Devices |
|---|---|---|---|---|---|
| added |  | 2 | 2026-10-31 22:00 UTC | 2026-11-01 08:00 UTC | 72: ftx_01894596, ftx_09f79dd0, ftx_0a28dc26, ftx_0e42d379, ftx_0f32b2fc, ftx_1261c59d, ftx_129f92ec, ftx_13275b1e, ftx_18784409, ftx_1c3a1ec9, ftx_25227436, ftx_28a43be1, ftx_28b3f018, ftx_2a182d70, ftx_2aa31da6, ftx_2b661d3e, ftx_2f57c61e, ftx_36eefe3d, ftx_37a69deb, ftx_39b36d55, ftx_3bf3558e, ftx_3dcd69d4, ftx_444cc36c, ftx_4877bebd, ftx_4c575c6f, ftx_4f776eef, ftx_535ef050, ftx_569ec423, ftx_5927a6bf, ftx_64606f52, ftx_6594d562, ftx_68c3e1ee, ftx_6ecfab80, ftx_6fd585af, ftx_7d7bf4a0, ftx_7fab447b, ftx_84c746c6, ftx_868fccfc, ftx_88cc9e38, ftx_89e0ff81, ftx_99e2a50f, ftx_9abb9d71, ftx_9be10d65, ftx_9f541c93, ftx_a5be673b, ftx_a978bcee, ftx_aae56d2a, ftx_ac145cce, ftx_aea1da42, ftx_aebf0bdb, ftx_b1cdacd6, ftx_b1d282cc, ftx_b47250ea, ftx_b87414b1, ftx_b9cbbe84, ftx_ba41a8b5, ftx_bedbee9a, ftx_c10c3e89, ftx_c393a963, ftx_c49ee2e2, ftx_c97c2e2d, ftx_caa05319, ftx_cdf2385b, ftx_de37562a, ftx_e2618220, ftx_e6bb82d5, ftx_ec06e81e, ftx_f3bab77c, ftx_f67a4e90, ftx_f762d92c, ftx_fd05f66e, ftx_fd45d029 |
| added |  | 3 | 2026-10-18 02:00 UTC | 2026-11-01 08:00 UTC | 11: ftx_353c03fb, ftx_4a5aa7c0, ftx_4d04b0fe, ftx_5bb307c6, ftx_68e0da6a, ftx_76d59116, ftx_93808e74, ftx_a3c87e47, ftx_b670aa5d, ftx_bd118415, ftx_f8271656 |
| added |  | 3 | 2026-10-22 02:00 UTC | 2026-11-01 08:00 UTC | 1: ftx_c20f4e57 |
| recomputed | elapsed_hours | 1 | 2026-10-18 08:00 UTC | 2026-10-18 08:00 UTC | 11: ftx_353c03fb, ftx_4a5aa7c0, ftx_4d04b0fe, ftx_5bb307c6, ftx_68e0da6a, ftx_76d59116, ftx_93808e74, ftx_a3c87e47, ftx_b670aa5d, ftx_bd118415, ftx_f8271656 |
| recomputed | elapsed_hours | 1 | 2026-10-22 08:00 UTC | 2026-10-22 08:00 UTC | 1: ftx_c20f4e57 |

A *recomputed* reading is not an edited value: an older reading arrived late and was slotted in before it, so its derived gap to the previous reading (`hours_delta`/`elapsed_hours`) was recalculated.

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
