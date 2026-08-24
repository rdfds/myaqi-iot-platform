"""CircuitPython-compatible client for reliable myAQI ingestion."""

import binascii
import hashlib
import json
import os
import time

SHA256_BLOCK_SIZE = 64
DEFAULT_STATE = {"next_sequence": 1, "pending": [], "dropped_readings": 0}


class UploadError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _sha256(data):
    digest = hashlib.new("sha256")
    digest.update(data)
    return digest.digest()


def _xor_bytes(value, mask):
    return bytes(byte ^ mask for byte in value)


def hmac_sha256(key, message):
    """Small HMAC implementation for boards without Python's hmac module."""
    if len(key) > SHA256_BLOCK_SIZE:
        key = _sha256(key)
    padded = key + bytes(SHA256_BLOCK_SIZE - len(key))
    inner = _sha256(_xor_bytes(padded, 0x36) + message)
    return _sha256(_xor_bytes(padded, 0x5C) + inner)


def sha256_hex(data):
    return binascii.hexlify(_sha256(data)).decode("ascii")


def decode_device_secret(encoded):
    standard = encoded.replace("-", "+").replace("_", "/")
    standard += "=" * (-len(standard) % 4)
    return binascii.a2b_base64(standard.encode("ascii"))


def sign_request(secret, timestamp, method, path, body):
    canonical = f"{timestamp}\n{method.upper()}\n{path}\n{sha256_hex(body)}".encode()
    signature = binascii.hexlify(hmac_sha256(secret, canonical)).decode("ascii")
    return "v1=" + signature


def format_utc(epoch_seconds):
    value = time.localtime(epoch_seconds)
    date = f"{value.tm_year:04d}-{value.tm_mon:02d}-{value.tm_mday:02d}"
    clock = f"{value.tm_hour:02d}:{value.tm_min:02d}:{value.tm_sec:02d}"
    return date + "T" + clock + "Z"


class JsonStateStore:
    """Persist the upload queue with a recoverable primary/backup swap."""

    def __init__(self, path):
        self.path = path
        self.backup_path = path + ".bak"
        self.temporary_path = path + ".tmp"

    def _read(self, path):
        with open(path) as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError("Invalid state document")
        next_sequence = value.get("next_sequence")
        if isinstance(next_sequence, bool) or not isinstance(next_sequence, int):
            raise ValueError("Invalid next_sequence")
        if next_sequence < 1:
            raise ValueError("Invalid next_sequence")
        pending = value.get("pending")
        if not isinstance(pending, list):
            raise ValueError("Invalid pending queue")
        last_sequence = 0
        for reading in pending:
            if not isinstance(reading, dict):
                raise ValueError("Invalid pending reading")
            sequence = reading.get("sequence")
            concentration = reading.get("pm25_ug_m3")
            if (
                isinstance(sequence, bool)
                or not isinstance(sequence, int)
                or sequence <= last_sequence
                or sequence >= next_sequence
                or not isinstance(reading.get("observed_at"), str)
                or isinstance(concentration, bool)
                or not isinstance(concentration, (int, float))
                or concentration != concentration
                or not 0 <= concentration <= 5000
            ):
                raise ValueError("Invalid pending reading")
            last_sequence = sequence
        dropped_readings = value.setdefault("dropped_readings", 0)
        if (
            isinstance(dropped_readings, bool)
            or not isinstance(dropped_readings, int)
            or dropped_readings < 0
        ):
            raise ValueError("Invalid dropped_readings")
        return value

    def load(self):
        found_state_file = False
        for path in (self.path, self.backup_path, self.temporary_path):
            try:
                os.stat(path)
                found_state_file = True
            except OSError:
                continue
            try:
                return self._read(path)
            except (OSError, ValueError):
                continue
        if found_state_file:
            raise ValueError("No valid ingestion state file remains")
        return {
            "next_sequence": DEFAULT_STATE["next_sequence"],
            "pending": [],
            "dropped_readings": 0,
        }

    @staticmethod
    def _remove_if_present(path):
        try:  # noqa: SIM105 - contextlib is not guaranteed on CircuitPython.
            os.remove(path)
        except OSError:
            pass

    def save(self, state):
        with open(self.temporary_path, "w") as handle:
            json.dump(state, handle, separators=(",", ":"))
        sync_filesystems = getattr(os, "sync", None)
        if sync_filesystems is not None:
            sync_filesystems()

        self._remove_if_present(self.backup_path)
        try:  # noqa: SIM105 - contextlib is not guaranteed on CircuitPython.
            os.rename(self.path, self.backup_path)
        except OSError:
            pass

        try:
            os.rename(self.temporary_path, self.path)
        except OSError:
            try:  # noqa: SIM105 - contextlib is not guaranteed on CircuitPython.
                os.rename(self.backup_path, self.path)
            except OSError:
                pass
            raise
        if sync_filesystems is not None:
            sync_filesystems()


class MyAQIClient:
    def __init__(
        self,
        session,
        api_base_url,
        device_id,
        device_secret,
        state_store,
        batch_size=20,
        max_pending=120,
        time_fn=None,
    ):
        normalized_url = api_base_url.rstrip("/")
        is_https_origin = normalized_url.startswith("https://")
        is_local_origin = normalized_url == "http://localhost" or normalized_url.startswith(
            "http://localhost:"
        )
        authority = normalized_url.split("://", 1)[-1]
        if (
            (not is_https_origin and not is_local_origin)
            or not authority
            or "/" in authority
            or "?" in authority
            or "#" in authority
        ):
            raise ValueError("api_base_url must be an HTTPS origin")
        if batch_size < 1 or batch_size > 500 or max_pending < batch_size:
            raise ValueError("Invalid queue limits")
        allowed_device_id = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
        if not device_id or not all(character in allowed_device_id for character in device_id):
            raise ValueError("device_id contains unsupported characters")

        self.session = session
        self.api_base_url = normalized_url
        self.device_id = device_id
        self.secret = decode_device_secret(device_secret)
        if len(self.secret) != 32:
            raise ValueError("device_secret must decode to 32 bytes")
        self.state_store = state_store
        self.batch_size = batch_size
        self.max_pending = max_pending
        self.time_fn = time_fn or time.time
        self.state = state_store.load()

    @property
    def pending_count(self):
        return len(self.state["pending"])

    def enqueue(self, pm25_ug_m3, observed_at=None):
        concentration = float(pm25_ug_m3)
        if concentration != concentration or not 0 <= concentration <= 5000:
            raise ValueError("pm25_ug_m3 must be between 0 and 5000")
        reading = {
            "sequence": self.state["next_sequence"],
            "observed_at": observed_at or format_utc(int(self.time_fn())),
            "pm25_ug_m3": concentration,
        }
        next_pending = list(self.state["pending"])
        dropped_readings = self.state["dropped_readings"]
        if len(next_pending) >= self.max_pending:
            next_pending.pop(0)
            dropped_readings += 1
        next_pending.append(reading)
        next_state = {
            "next_sequence": self.state["next_sequence"] + 1,
            "pending": next_pending,
            "dropped_readings": dropped_readings,
        }
        self.state_store.save(next_state)
        self.state = next_state
        return reading

    def _close_response(self, response):
        if response is not None:
            response.close()

    def flush_one(self):
        if not self.state["pending"]:
            return {"accepted": 0, "duplicates": 0, "remaining": 0}

        batch = self.state["pending"][: self.batch_size]
        wire_batch = [
            {
                "sequence": reading["sequence"],
                "observed_at": reading["observed_at"],
                "pm25_ug_m3": reading["pm25_ug_m3"],
            }
            for reading in batch
        ]
        body = json.dumps({"readings": wire_batch}, separators=(",", ":")).encode("utf-8")
        path = f"/v1/devices/{self.device_id}/measurements:batch"
        timestamp = str(int(self.time_fn()))
        first_sequence = batch[0]["sequence"]
        last_sequence = batch[-1]["sequence"]
        headers = {
            "Content-Type": "application/json",
            "Connection": "close",
            "Idempotency-Key": f"myaqi-batch-{self.device_id}-{first_sequence}-{last_sequence}",
            "X-Device-Timestamp": timestamp,
            "X-Device-Signature": sign_request(
                self.secret,
                timestamp,
                "POST",
                path,
                body,
            ),
        }

        response = None
        try:
            response = self.session.post(
                self.api_base_url + path,
                data=body,
                headers=headers,
                timeout=15,
            )
            status = response.status_code
            if status != 202:
                raise UploadError(f"Ingestion returned HTTP {status}", status=status)

            result = response.json()
            acknowledged = int(result.get("accepted", 0)) + int(result.get("duplicates", 0))
            if acknowledged != len(batch):
                raise UploadError("Ingestion acknowledgement did not cover the batch")

            next_state = {
                "next_sequence": self.state["next_sequence"],
                "pending": self.state["pending"][len(batch) :],
                "dropped_readings": self.state["dropped_readings"],
            }
            self.state_store.save(next_state)
            self.state = next_state
            result["remaining"] = len(next_state["pending"])
            return result
        finally:
            self._close_response(response)

    def flush(self, max_batches=3):
        result = {"accepted": 0, "duplicates": 0, "remaining": self.pending_count}
        for _index in range(max_batches):
            if not self.state["pending"]:
                break
            current = self.flush_one()
            result["accepted"] += int(current.get("accepted", 0))
            result["duplicates"] += int(current.get("duplicates", 0))
            result["remaining"] = current["remaining"]
        return result
