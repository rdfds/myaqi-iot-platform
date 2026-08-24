# Retired provider adapter

`index.py` is the retired Flask integration for Backendless, IQAir, and Twilio. It remains inspectable for implementation traceability but is not part of the runtime documented at the repository root.

Do not deploy this module directly. It lacks the signed requests, database constraints, idempotency protocol, transactional outbox, and operational controls implemented under `backend/`.
