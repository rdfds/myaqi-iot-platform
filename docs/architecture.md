# System architecture

## Runtime flow

1. The CircuitPython device starts and reads its local configuration.
2. If Wi-Fi credentials are missing or invalid, the device enters access-point mode and serves a local setup page.
3. With valid credentials, the device connects to Wi-Fi, registers its serial number, reads the PM2.5 sensor, computes an AQI value, and sends the reading to the Flask API.
4. The backend resolves device metadata, stores indoor readings, fetches an outdoor AQI value, and stores the outdoor reading.
5. Threshold checks can send SMS alerts to configured contacts through Twilio.

## Boundaries

| Component | Responsibility | Failure behavior |
| --- | --- | --- |
| CircuitPython firmware | Sensor reads, provisioning, device state, upload loop | Persist an error, show state through the LED, and return to setup mode when recovery is required |
| Flask backend | Ingestion, provider calls, aggregation, retention, alerts | Log provider failures and skip incomplete alert paths rather than storing credentials in code |
| Data store | Device metadata and indoor/outdoor measurements | External dependency; deployment must supply credentials and access controls |
| AQI provider | Outdoor context | A failed provider call does not prevent the device from reporting its indoor reading |
| Twilio | Optional SMS delivery | Missing configuration disables SMS delivery with a warning |

## Design choices

- Provisioning is local and device-led so a new unit does not require a developer laptop.
- Device state is explicit (`Normal`, setup/AP mode, error, and resetting) so failures are visible to a person standing near the hardware.
- Provider credentials are environment-only; example files contain placeholders.
- The public repository is a sanitized demonstration. The deployed system used additional client and operational components that are intentionally not included here.
