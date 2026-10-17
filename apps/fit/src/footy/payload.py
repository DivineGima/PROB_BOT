"""The exact text and hash of a stored model payload (``model_params.payload_json`` and
``payload_sha256``). The fit job writes them and the promotion gate re-verifies them, so both use
these two functions and can never disagree about the encoding."""

from __future__ import annotations

import hashlib
import json


def payload_text(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def payload_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
