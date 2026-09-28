---
role: "flutter-dev"
class: domain
topic: "locked-phone-ble-scan"
description: "A locked Android phone hears the beacon only with a FILTERED scan, renewed, and a beacon advertising fast enough — measured 2026-09-28 on the bench phone"
tier: 2
knowledge_scope: full
distilled_at: "2026-09-28"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 2a75bf5f43dbe630
---

## A locked Android phone hears the beacon only with a FILTERED scan, renewed, and a beacon advertising fast enough — measured 2026-09-28 on the bench phone

Measured on the bench phone (Galaxy A40, Android 11) with the EYE BEACON, 2026-09-28,
reading `adb shell dumpsys bluetooth_manager` (per-app scan table + "Last 5 scans"):

1. **Android suspends an UNFILTERED scan while the screen is off.** "Suspended Time"
   appears on every locked scan; nothing is delivered from the lock on. The #982 aboard
   service therefore ended every ride on the 90 s silence timeout, ~90 s after the lock.
2. **A filtered scan (Eddystone 0xFEAA, withServices + withServiceData) is not suspended,
   but the controller reports each device about ONCE per scan.** Without renewal: 1 match
   in 130 s. Renewing the scan every 20 s: ~1 match per renewal. Fix: dc382527 (passenger),
   05b47f70 (driver identity scan) on develop-qzapp/flutter-dev-01/fix/ble-scan-filter-screen-off.
3. **The beacon's factory advertising interval is 5000 ms; at that rate a lowPower,
   screen-off scan matched 4 times in 27.** At 1000 ms: 10 in 17, ride held 4+ min.
   No record sets the deployed interval — raised to architect-cto.
4. A 0xFEAA filter can drop the Teltonika SCAN RESPONSE (battery/movement/magnet flags,
   company 0x089A), which does not carry 0xFEAA: keep the driver's scanForReading unfiltered.

**How to apply:** never trust `sample` rows as proof of hearing — the service samples a HELD
region on a timer; the proof is a sample PAST enter+90 s, or the scan table's results count.
Screen off remotely with `input keyevent 26` (223 did nothing on this phone); Bluetooth cannot
be toggled from adb on Android 11 (`svc bluetooth`/`cmd bluetooth_manager` do nothing).
Related: [[passenger-background-crowding-owed]], [[android-build-on-phone]].

*References: android-build-on-phone, passenger-background-crowding-owed*

*Observed 2026-09-28 (flutter-dev)*
