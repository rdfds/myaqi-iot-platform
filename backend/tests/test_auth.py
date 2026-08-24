from __future__ import annotations

import pytest

from myaqi_backend.auth import (
    AuthenticationError,
    canonical_request,
    decode_device_secret,
    derive_device_secret,
    encode_device_secret,
    sign_request,
    verify_request_signature,
)


def test_signature_covers_method_path_timestamp_and_body() -> None:
    secret = derive_device_secret("master-key", "device-1")
    body = b'{"readings":[]}'
    signature = sign_request(secret, "1000", "POST", "/v1/example", body)

    verify_request_signature(
        secret=secret,
        timestamp="1000",
        signature=signature,
        method="POST",
        path="/v1/example",
        body=body,
        max_clock_skew_seconds=300,
        now=1000,
    )

    with pytest.raises(AuthenticationError, match="Invalid device signature"):
        verify_request_signature(
            secret=secret,
            timestamp="1000",
            signature=signature,
            method="POST",
            path="/v1/example",
            body=b'{"readings":[1]}',
            max_clock_skew_seconds=300,
            now=1000,
        )


def test_stale_timestamp_is_rejected() -> None:
    secret = derive_device_secret("master-key", "device-1")
    signature = sign_request(secret, "1000", "POST", "/v1/example", b"{}")

    with pytest.raises(AuthenticationError, match="outside the allowed clock window"):
        verify_request_signature(
            secret=secret,
            timestamp="1000",
            signature=signature,
            method="POST",
            path="/v1/example",
            body=b"{}",
            max_clock_skew_seconds=300,
            now=1301,
        )


def test_canonical_request_is_stable() -> None:
    assert canonical_request("1000", "post", "/v1/example", b"{}").decode().splitlines() == [
        "1000",
        "POST",
        "/v1/example",
        "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
    ]


def test_device_secret_encoding_round_trips() -> None:
    secret = derive_device_secret("master-key", "device-1")
    assert decode_device_secret(encode_device_secret(secret)) == secret


@pytest.mark.parametrize(
    ("timestamp", "signature", "message"),
    [
        (None, None, "Missing device authentication headers"),
        ("not-a-number", "v1=bad", "Invalid device timestamp"),
    ],
)
def test_malformed_authentication_headers_are_rejected(timestamp, signature, message) -> None:
    with pytest.raises(AuthenticationError, match=message):
        verify_request_signature(
            secret=b"secret",
            timestamp=timestamp,
            signature=signature,
            method="POST",
            path="/v1/example",
            body=b"{}",
            max_clock_skew_seconds=300,
            now=1000,
        )
