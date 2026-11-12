# FieldTrax sync and record changes

Run `run_20261112T032213289748Z`.

## FieldTrax sync

- Devices listed: 87; readings received: 4639
- New reading lines stored: 0; new device versions stored: 0
- Items that could not be stored or fetched: 0 (see dq checks DV009/DV010/DV011)
- Requests: 201 (rate-limited and retried: 18, unavailable and retried: 5, network errors retried: 0, unreadable pages retried: 0, signed in again: 4)

## What changed since the previous run

Nothing. Every clean record is identical to the previous run.

## Device to machine matching

Matched by VIN first, then rego, then business + fleet number in the device name.

- rego: 7
- vin: 77
- no match: 3

### Devices that match nothing (3)

| Device | Name | VIN | Rego | Still listed | Why |
|---|---|---|---|---|---|
| ftx_5927a6bf | Spare tracker 1 | S0SC01RFB9VEG4A01 | ZZZ0 | yes | VIN, rego and name match no line on BE Plant or NH Fleet |
| ftx_b1d282cc | Spare tracker 3 | RY05ZKWWMR5LTTE2C | ZZZ2 | yes | VIN, rego and name match no line on BE Plant or NH Fleet |
| ftx_c10c3e89 | Spare tracker 2 | AB3D14EK3B1JNU7Z3 | ZZZ1 | yes | VIN, rego and name match no line on BE Plant or NH Fleet |

### Working machines with no device (10)

| Machine | Business | Fleet no | Status | Register line |
|---|---|---|---|---|
| mch_phya2f7974j2lm9rp | BE | GN-01 | workshop | BE Plant!67 |
| mch_4dsv1f53thmn1ncy8 | BE | GN-02 | available | BE Plant!68 |
| mch_pwejcmb6j48juet25 | BE | GN-03 | on_project | BE Plant!69 |
| mch_rpuh6pnv5uuefyy5l | BE | SK-05 | available | BE Plant!27 |
| mch_whlgxb0zdftg0m0z1 | BE | TP-10 | on_project | BE Plant!46 |
| mch_1ksvx6accm95xwa5h | NH | GN-01 | available | NH Fleet!35 |
| mch_hnfu9ck4nz0jyut66 | NH | GN-02 | on_project | NH Fleet!40 |
| mch_7xb9335vsf0sgcymm | NH | LV-02 | on_project | NH Fleet!15 |
| mch_6ch8daxhab22y54ku | NH | RL-01 | on_project | NH Fleet!18 |
| mch_un809z456wru10w3v | NH | TP-07 | on_project | NH Fleet!13 |
