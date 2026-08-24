# Security model

## Protected assets

- device identity and signing material
- student/school location metadata in a real deployment
- sensor readings and operational status
- notification recipients and provider credentials

## Implemented controls

| Threat | Control |
| --- | --- |
| Request body tampering | HMAC-SHA256 covers timestamp, method, path, and exact body hash |
| Captured-request replay | Five-minute timestamp window plus request idempotency |
| Retry-created duplicates | Unique idempotency key and unique `(device, sequence)` constraints |
| Device enumeration | Unknown and inactive devices return the same authentication response |
| Cross-device key reuse | Secrets are derived from the device ID and a versioned master key |
| Partial downstream writes | Measurement and outbox event share one transaction |
| Worker duplication | Row locks, `SKIP LOCKED`, lock ownership checks, and stale-lock recovery |
| Secret leakage in Git | Environment-only master/provider keys and ignored credential artifacts |

Signature verification uses constant-time comparison. Provisioning outputs a device secret once; the server derives it on demand and stores only the device identity and key version.

## Remaining deployment work

- terminate TLS and reject plaintext traffic;
- store the master key in a managed secret service and implement dual-key rotation;
- authenticate human/admin operations separately from devices;
- apply per-device rate limits at the edge;
- encrypt sensitive school metadata and define retention policy;
- add network policy, database least privilege, backups, and restore tests;
- audit provisioning, device disablement, and dead-letter replay;
- validate the signing client on target CircuitPython hardware.

The derived-key design reduces stored credential material but increases the impact of a master-key compromise. A larger deployment may prefer individually generated device keys stored in an HSM-backed secret service.
