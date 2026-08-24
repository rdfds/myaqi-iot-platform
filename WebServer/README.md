# Historical backend prototype

`index.py` is the sanitized Flask/provider integration retained from the original project. It demonstrates the deployed route shapes and provider workflows, but it is tightly coupled to Backendless, IQAir, and Twilio and is not the current reference architecture.

New reliability work lives in `backend/`. The separation is intentional:

- historical code remains inspectable instead of being rewritten to look newer;
- the reference backend can be tested without real provider credentials;
- device ingestion, alert delivery, and external-provider failures have explicit boundaries.

Do not deploy this historical module directly. It lacks the signed requests, database constraints, idempotency protocol, transactional outbox, and operational controls implemented by the reference backend.
