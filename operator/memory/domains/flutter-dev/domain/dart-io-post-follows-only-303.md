---
role: "flutter-dev"
class: domain
topic: "dart-io-post-follows-only-303"
description: "A real-socket test that a POST \"never follows the redirect\" can only fail for 303 under dart:io; 301/302/307/308 POSTs are not followed even with followRedirects on"
tier: 2
knowledge_scope: full
distilled_at: "2026-11-17"
origin:
  - agent: "flutter-dev-01"
    host: "develop-qzapp"
    project: gzapp
    working_copy: gzapp
derived_from:
  - 4aaa26bde03890b2
---

## A real-socket test that a POST "never follows the redirect" can only fail for 303 under dart:io; 301/302/307/308 POSTs are not followed even with followRedirects on

dart:io's HttpClient (under package:http's IOClient) auto-follows a POST
only on 303 (re-issued as GET). With `followRedirects = false` removed,
a POST answered 301, 302, 307 or 308 still returns the 3xx, so a
real-socket test asserting "the Location is never asked" passes either
way for those four — it cannot fail. Pin the flag per status with a
MockClient (it records `request.followRedirects`), and keep a real-socket
case for 303 only, which does red under the mutation.

Measured 2026-11-11, gzapp#1252 review r1 F2, fix 081e6cdcf on
architect-cto-01's j620 branch (packages/gzapp_flutter_shared/test/
features/map/tile_token_test.dart). See [[proof-run-must-contain-the-ingredient]]:
run the mutation before claiming a test guards a flag.

*References: proof-run-must-contain-the-ingredient*

*Observed 2026-11-11 (flutter-dev)*
