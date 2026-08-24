# Hardware soak testing

This harness records board diagnostics, supervised fault injections, and a database sequence audit as one evidence bundle. It does not turn an unrun plan into a reliability claim: the result passes only after the full configured duration, every checkpoint is confirmed, the device queue drains, and PostgreSQL contains the complete expected sequence range.

## Prepare the run

Deploy one immutable Git revision, provision a dedicated test device, and record its next sequence from both the board diagnostic and `myaqi-admin inspect-device`. Do not place credentials, raw configuration, or CloudWatch exports containing secrets in the bundle.

Install the development tools and identify the board's serial port:

```bash
pip install -e "backend[dev]"
python -m serial.tools.list_ports
```

Start a new run directory. The command refuses to reuse an existing directory so earlier evidence is not silently overwritten.

```bash
python -m soak.run_hardware \
  --port /dev/cu.usbmodem101 \
  --device-id soak-001 \
  --revision "$(git rev-parse HEAD)" \
  --expected-start-sequence 1843 \
  --output soak/results/2026-08-24-soak-001
```

The seven-day scenario prompts for Wi-Fi outages, an outbox-worker restart, a staged API deployment, and a board power cycle. Confirm a checkpoint only after performing it, and retain the corresponding AWS deployment or alarm screenshot outside the repository if it contains account identifiers.

Use `--duration-seconds` only to validate the harness. A shortened run records both the planned and actual duration and cannot substantiate a seven-day resume claim.

## Verify the result

After the final device queue drains, audit the exact sequence interval against the deployed database:

```bash
myaqi-admin verify-sequence-range soak-001 \
  --start 1843 \
  --end 2850 > soak/results/2026-08-24-soak-001/backend-report.json

python -m soak.verify_results soak/results/2026-08-24-soak-001 \
  --backend-report soak/results/2026-08-24-soak-001/backend-report.json \
  --output soak/results/2026-08-24-soak-001/result.json
```

`result.json` follows [`results.schema.json`](results.schema.json). Review the raw timestamps, external deployment evidence, and CloudWatch alarm history before publishing a sanitized summary. The database uniqueness constraint prevents duplicate `(device_id, sequence)` rows; the sequence audit establishes that the expected range is also complete.
