# CircuitPython firmware

The firmware reads the PM2.5 sensor, communicates status through the onboard LED, provisions Wi-Fi through a local access point, synchronizes UTC through NTP, and sends retry-safe measurement batches to the myAQI API.

## Board files

Copy these project files to the CircuitPython volume:

- `boot.py`
- `code.py`
- `myaqi_client.py`
- `index.html`
- `config.json`, based on `config.example.json`

Install the matching CircuitPython libraries for `adafruit_requests`, `adafruit_httpserver`, `adafruit_ntp`, `adafruit_pm25`, `neopixel`, and their dependencies in the board's `lib/` directory.

## Device provisioning

Provision the device in the backend first:

```bash
myaqi-admin provision-device school-001 --name "Science room 201"
```

Copy the returned secret and the same device ID into `config.json`:

```json
{
  "serial_number": "school-001",
  "api_base_url": "https://api.example.org",
  "device_secret": "<provisioned secret>",
  "upload_batch_size": 20,
  "max_buffered_readings": 120,
  "measurement_interval_seconds": 600
}
```

The API URL must use HTTPS on a device. The secret is a credential: do not commit a populated `config.json` or reuse one secret across devices.

## Upload behavior

`myaqi_client.py` persists a monotonic sequence and pending queue in `/myaqi_state.json`. Each request uses compact JSON, a stable batch-derived idempotency key, and an HMAC-SHA256 signature compatible with the backend. A reading remains queued after timeouts, server errors, malformed acknowledgements, or reset. It is removed only when the API reports every reading as accepted or duplicate.

The state writer keeps a last-complete backup so an interrupted flash write can recover on the next boot. The queue is bounded by `max_buffered_readings`; once full, the oldest reading is discarded and the persisted `dropped_readings` counter increases.

Host-side tests cover signing compatibility, queue recovery, retry behavior, and a simulated lost response through the real Flask route. Run them from the repository root:

```bash
pytest firmware_tests
```

These tests do not replace a target-board soak test. Verify NTP, TLS memory use, filesystem durability, sensor wiring, and power-loss recovery on the exact CircuitPython board and version before deployment.
