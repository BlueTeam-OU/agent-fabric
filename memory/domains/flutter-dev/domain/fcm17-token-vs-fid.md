---
role: "flutter-dev"
class: domain
topic: "fcm17-token-vs-fid"
description: firebase_messaging 17 deprecates getToken() for register()/onRegistered, which hand out the installation id (FID), not a registration token
tier: 2
knowledge_scope: full
distilled_at: "2026-10-31"
origin:
  - agent: "flutter-dev-02"
    host: "develop-qzapp"
    project: "agent-fabric"
    working_copy: "agent-fabric"
derived_from:
  - ad7e25a5fc40c018
---

## firebase_messaging 17 deprecates getToken() for register()/onRegistered, which hand out the installation id (FID), not a registration token

In firebase_messaging 17.0.0 `getToken()` is `@Deprecated('Use register() and onRegistered instead.')`, but `onRegistered` yields the Firebase Installation ID (FID) for "direct-send", not an FCM registration token. A backend that sends through FCM HTTP v1 `message.token` (gzapp's PushWakeSender) needs the token, so the client keeps `getToken()` under `// ignore: deprecated_member_use` with the reason. Deleting the installation (`FirebaseInstallations.instance.delete()`, firebase_app_installations 0.5.0) invalidates its tokens; that is the per-journey rotation ADR-077 §2.3 asks for.

Also: `FirebaseMessaging.onBackgroundMessage` only registers callback handles over the method channel. It needs no initialised Firebase app, so it is safe at every launch. Set `firebase_messaging_auto_init_enabled=false` in the manifest so initialising Firebase mints no token.

Source: gzapi-org/gzapp branch develop-qzapp/flutter-dev-02/feat/j11-adr-077-s-passenger-app-half, lib/features/journey_wake/firebase_push_service.dart.

*Observed 2026-10-19 (flutter-dev)*
