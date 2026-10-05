---
role: "flutter-dev"
class: domain
topic: "locked-phone-ble-scan"
description: "A locked Android phone hears the beacon only with a FILTERED scan, renewed, and a beacon advertising fast enough — measured 2026-09-28 on the bench phone"
tier: 2
knowledge_scope: full
distilled_at: "2026-10-05"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 2a75bf5f43dbe630
  - 481405ccf0e10fdf
---

## A locked Android phone hears the beacon only with a FILTERED scan, renewed, and a beacon advertising fast enough — measured 2026-09-28 on the bench phone

Measured on the bench phone (Galaxy A40, Android 11) with the EYE BEACON, 2026-09-28,
reading `adb shell dumpsys bluetooth_manager` (per-app scan table + "Last 5 scans"):

1. **Android suspends an UNFILTERED scan while the screen is off.** "Suspended Time"
   appears on every locked scan; nothing is delivered from the lock on. The #982 aboard
   service therefore ended every ride on the 90 s silence timeout, ~90 s after the lock.
2. **A filtered scan (Eddystone 0xFEAA, withServices + withServiceData) is not suspended,
   but in lowPower it went quiet on a device it had reported** (1 match in 130 s without
   renewal); renewed every 20 s it reports again. In balanced mode ~3 per scan (with renewal;
   balanced without renewal not measured) — keep the 20 s renewal. Fix: dc382527 (passenger),
   05b47f70 (driver identity scan), PR #994.
3. **The beacon's factory advertising interval is 5000 ms; at that rate a lowPower,
   screen-off scan matched 4 times in 27.** At 1000 ms: 10 in 17, ride held 4+ min.
   No record sets the deployed interval — raised to architect-cto. Balanced at 5 s unmeasured (doze-contaminated).
4. **lowPower listens too little: balanced mode** (cfe7f023): 10-minute screen-off runs,
   beacon 1 s — lowPower ~1.3 matches/min + a false exit (10 s renewal no better: 20%/scan);
   balanced 98 in 30 scans (~10/min), none.
5. **Android light doze disables the service's wake lock** (`dumpsys power`:
   `ForegroundService:WakeLock DISABLED`; `dumpsys deviceidle` mLightState=IDLE): timers stall
   for minutes → false exit. Remedy (battery-optimisation exemption) is a product/Play-policy
   decision — asked architect-cto (GZCoord 01a0e82b, 2026-09-28), with the beacon interval.
6. **flutter_blue_plus `scanResults` REPLAYS the previous scan's list to a new listener**;
   use `onScanResults`, and pass on only entries whose timestamp moved (e6b131be, 411126ad).
All in PR #994, MERGED 2026-09-28 13:31Z.
**DECIDED (owner via architect-cto, GZCoord 01a0e847, 2026-09-28):** beacons advertise at
1000 ms — a PROVISIONING parameter on the registry entry (ADR-013 amendment), never a code
constant; NO battery-exemption dialog by default (only ever a rider-initiated setting, ADR-036
§2.5 A 2026-09-28) — offloaded filtered scan + idle-allowed timers, and MEASURE doze with #994
first. I told architect-cto (01a0e849) that setExactAndAllowWhileIdle needs SCHEDULE_EXACT_ALARM
(user-granted, not pre-granted on 14) or Play-restricted USE_EXACT_ALARM, and setAndAllowWhileIdle
is ~1 per 9 min in doze; proposed driving the service from scan deliveries instead of timers.
8. **Doze measured on main d1432991 (#994 in), 2026-09-28, 30 min screen off, beacon 1 s,
   journey active:** evidence 6/~180, crowding samples 1/~60, 2 false exit+enter at the
   maintenance windows (min 9, min 20). Light doze from minute 1, wake lock DISABLED, no scan
   renewal after the first minute, network up; scan deliveries do not wake the service either.
   Idle-allowed alarms are capped ~1/9 min in doze. Sent to architect-cto (01a0e884): next step
   = rider-initiated exemption (measure first) or accept in-front-only; and whether to stop
   reporting unvouched transitions. Checks 4 (journey evidence locked, 6/min) and 5 (BT off:
   posts stop; on: resume in 18 s) PASSED before doze set in.
9. **STOPPED by the owner (2026-09-28 ~15:00Z): "stop anything about doze problem".** architect-cto
   had asked (01a0e887) for an exemption measurement and ruled that an unobserved silence is not
   an exit (ADR-036 amendment on their branch). RESUMED the same day on the owner's word
   "do what architect-cto instructed you to do": measure the exemption, implement the ruling.
10. **Exemption measured 2026-09-28 18:36-19:36Z, both runs UNPLUGGED:** exempted 174 evidence/58
   samples/0 exits; NOT exempted 172/58/0, wake lock held, light IDLE + deep IDLE_PENDING. So the
   exemption did not separate working from frozen; the earlier freeze (wake lock DISABLED) was very
   probably ON THE CHARGER (unproven). Ruling built on fix/silence-counts-scanning-time (cf242d3c,
   7b2f9247, 861b7f68; review + 2 re-reviews, last clean; unpushed). Sent 01a0e985: ask (a) plugged
   run?, (b) fold into cto's ADR PR or own PR?, (c) wall-clock ceiling for a region held through
   repeated doze windows? DOZE RUNS NEED THE PHONE UNPLUGGED; up-role refuses if adb holds 5759.
11. **Plugged-in control 2026-09-28 19:59-20:16Z:** full cadence (101/34), no doze on the charger.
   CORRECTION: the frozen run was NOT on the charger (it showed light IDLE, impossible charging);
   charger and level ruled out; the two frozen runs (12:32Z run C, 14:25Z) share only a DISABLED
   wake lock — next time capture `cmd activity get-uid-state 10264` (4=FGS when healthy).
   **Android full backup (charging, night) KILLS the app process** (logcat: full_backup_package,
   quota exceeded 108 MB, "has died: prcp FGS"); the service restarts empty (start data taken once)
   and the ride is lost. Neither manifest sets allowBackup (default true). Asked architect-cto
   (01a0e9ac) to allow android:allowBackup="false" in both apps. DONE: supplied onto #999
   (c17fd26d, 48b4dc0a); iOS half OWED (see ios-no-os-backup-owed).
12. **Owner's 50% run DONE 2026-09-29 14:11-14:41Z** (main cdba1b1c, unplugged, not exempted, 48->46%,
   journey + crowding): evidence 181/~180, crowding 60/~60, 0 exits; light IDLE from min 1, wake lock
   held, uid 4 every minute. Level ruled out too; the two freezes remain unexplained (none since #994).
   Sent architect-cto 01a0ed9d. Per-minute monitor: scratchpad run4-watch.sh.
   **25% run DONE same day 16:11-16:41Z** (owner's ask, same build): 180/~180, 61/~60, 0 exits, same
   readings. Four clean unplugged runs; level, charger and exemption all ruled out. Sent 01a0ee0b.
7. A 0xFEAA filter can drop the Teltonika SCAN RESPONSE (battery/movement/magnet flags,
   company 0x089A), which does not carry 0xFEAA: keep the driver's scanForReading unfiltered.

**How to apply:** never trust `sample` rows as proof of hearing — the service samples a HELD
region on a timer; the proof is a sample PAST enter+90 s, or the scan table's results count.
Wireless adb drops when the phone sleeps long; the app then loses its adb-reverse route
(rows stop, no exit) — re-pair/connect and redo the run. Screen off remotely with `input keyevent 26` (223 did nothing on this phone); Bluetooth cannot
be toggled from adb on Android 11 (`svc bluetooth`/`cmd bluetooth_manager` do nothing).
Related: [[passenger-background-crowding-owed]], [[android-build-on-phone]].

*References: android-build-on-phone, passenger-background-crowding-owed*

*Observed 2026-09-28 (flutter-dev)*
