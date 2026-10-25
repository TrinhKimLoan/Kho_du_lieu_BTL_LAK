# Phase 4 Fix 1 — UUID fingerprint serialization

The client runtime reached snapshot reconciliation, then failed because psycopg returns source_epoch as uuid.UUID. Explicitly serialize UUID as standard text in canonical(); retain strict errors for unsupported types. No DDL, credentials, volume, checkpoint or source data changes.

Offline: 22 phase 4 unit tests and 14 phase 3 regression tests passed. Docker CDC runtime validation remains required on the client. Rebuild with scripts/run_phase4.ps1 and retain the existing volumes and credentials. Do not reset connector offsets or delete volumes.
