# Historical CircuitPython firmware

This directory preserves the firmware and local provisioning interface from the original myAQI deployment. It covers sensor reads, status LEDs, access-point setup, persisted configuration, connectivity recovery, and measurement upload.

The firmware currently targets the historical `WebServer/` routes. The 2026 reference backend defines a signed batch protocol; connecting physical devices to it requires a small compatibility client that persists a monotonic sequence number, batches buffered readings, reuses idempotency keys across retries, and computes the documented HMAC signature.

That integration is intentionally not claimed as complete until it is exercised on supported CircuitPython hardware.
