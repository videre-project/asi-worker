## @file
# Copyright (c) 2025, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""NBAC binary encoding/decoding utilities."""

from __future__ import annotations

import base64
import struct
from math import isfinite
from typing import Any

from .model import NBACMeta, NBACModel, NBACModelParams


_META_MAGIC    = b"NBM1"  # Naive Bayes Meta v1
_CARD_MAGIC_V1 = b"NBC1"  # Naive Bayes Card v1
_CARD_MAGIC_V2 = b"NBC2"  # Naive Bayes Card v2 (includes background log-q)


def _as_bytes(blob: Any) -> bytes:
  if blob is None:
    raise ValueError("missing blob")

  if isinstance(blob, (bytes, bytearray)):
    return bytes(blob)

  if isinstance(blob, memoryview):
    return blob.tobytes()

  # Some D1 bindings may return Uint8Array proxies or objects with `to_py()`.
  to_py = getattr(blob, "to_py", None)
  if callable(to_py):
    py = to_py()
    if isinstance(py, (bytes, bytearray)):
      return bytes(py)
    if isinstance(py, list):
      return bytes(py)

  if isinstance(blob, str):
    # Support base64-wrapped blobs for environments that can't bind BLOBs.
    # Format: "b64:<base64>" (preferred) or raw base64.
    s = blob
    if s.startswith("b64:"):
      s = s[4:]
    return base64.b64decode(s)

  raise TypeError(f"unsupported blob type: {type(blob)!r}")


def encode_meta(meta: NBACMeta) -> bytes:
  if meta.version != 1:
    raise ValueError("unsupported meta version")

  archetypes = meta.archetypes
  a_count = len(archetypes)

  def _check_model(model: NBACModel) -> None:
    if len(model.log_prior) != a_count or len(model.log_unseen) != a_count:
      raise ValueError("meta arrays must match archetype count")
    for x in model.log_prior + model.log_unseen:
        if not isfinite(x):
          raise ValueError("meta contains non-finite float")

  _check_model(meta.counts)
  _check_model(meta.presence)

  parts: list[bytes] = []
  parts.append(_META_MAGIC)
  parts.append(struct.pack("<BQI", meta.version, meta.build_unix, a_count))

  for name in archetypes:
    b = name.encode("utf-8")
    if len(b) > 65535:
      raise ValueError("archetype name too long")
    parts.append(struct.pack("<H", len(b)))
    parts.append(b)

  parts.append(_encode_model(meta.counts))
  parts.append(_encode_model(meta.presence))

  return b"".join(parts)


def _encode_model(model: NBACModel) -> bytes:
  kind = 0 if model.kind == "counts" else 1
  p = model.params
  header = struct.pack("<Bfff", kind, float(p.alpha), float(p.background_lambda), float(p.temperature))

  # float32 arrays
  arr = struct.pack("<" + "f" * (len(model.log_prior) + len(model.log_unseen)),
                    *[float(x) for x in (model.log_prior + model.log_unseen)])
  return header + arr


def decode_meta(blob: Any) -> NBACMeta:
  b = _as_bytes(blob)
  if len(b) < 4 + 1 + 8 + 4:
    raise ValueError("meta blob too short")

  if b[:4] != _META_MAGIC:
    raise ValueError("invalid meta magic")

  version, build_unix, a_count = struct.unpack_from("<BQI", b, 4)
  if version != 1:
    raise ValueError("unsupported meta version")

  offset = 4 + struct.calcsize("<BQI")

  archetypes: list[str] = []
  for _ in range(a_count):
    (n,) = struct.unpack_from("<H", b, offset)
    offset += 2
    name = b[offset:offset + n].decode("utf-8")
    offset += n
    archetypes.append(name)

  counts_model, offset = _decode_model(b, offset, a_count)
  presence_model, offset = _decode_model(b, offset, a_count)

  if counts_model.kind != "counts" or presence_model.kind != "presence":
    raise ValueError("meta models out of order or invalid")

  return NBACMeta(
    version=version,
    build_unix=build_unix,
    archetypes=archetypes,
    counts=counts_model,
    presence=presence_model,
  )


def _decode_model(b: bytes, offset: int, a_count: int) -> tuple[NBACModel, int]:
  kind, alpha, background_lambda, temperature = struct.unpack_from("<Bfff", b, offset)
  offset += struct.calcsize("<Bfff")

  total = a_count * 2
  floats = struct.unpack_from("<" + "f" * total, b, offset)
  offset += 4 * total

  log_prior = list(map(float, floats[:a_count]))
  log_unseen = list(map(float, floats[a_count:]))

  model = NBACModel(
    kind="counts" if kind == 0 else "presence",
    params=NBACModelParams(alpha=float(alpha), background_lambda=float(background_lambda), temperature=float(temperature)),
    log_prior=log_prior,
    log_unseen=log_unseen,
  )
  return model, offset


def encode_card_entry(
  log_theta_counts: list[float],
  log_theta_presence: list[float],
  *,
  log_q_counts: float | None = None,
  log_q_presence: float | None = None,
) -> bytes:
  if len(log_theta_counts) != len(log_theta_presence):
    raise ValueError("model arrays must be same length")

  for x in log_theta_counts + log_theta_presence:
    if not isfinite(x):
      raise ValueError("card entry contains non-finite float")

  a_count = len(log_theta_counts)

  if log_q_counts is None or log_q_presence is None:
    header = _CARD_MAGIC_V1 + struct.pack("<I", a_count)
    payload = struct.pack(
      "<" + "f" * (2 * a_count),
      *[float(x) for x in (log_theta_counts + log_theta_presence)],
    )
    return header + payload

  if not isfinite(float(log_q_counts)) or not isfinite(float(log_q_presence)):
    raise ValueError("background log-q must be finite")

  header = _CARD_MAGIC_V2 + struct.pack("<Iff", a_count, float(log_q_counts), float(log_q_presence))
  payload = struct.pack(
    "<" + "f" * (2 * a_count),
    *[float(x) for x in (log_theta_counts + log_theta_presence)],
  )
  return header + payload


def decode_card_entry(blob: Any) -> tuple[list[float], list[float], float | None, float | None]:
  b = _as_bytes(blob)
  if len(b) < 4 + 4:
      raise ValueError("card blob too short")

  magic = b[:4]
  if magic == _CARD_MAGIC_V1:
    (a_count,) = struct.unpack_from("<I", b, 4)
    offset = 8
    expected = 8 + 4 * 2 * a_count
    if len(b) != expected:
      raise ValueError("card blob has unexpected length")

    floats = struct.unpack_from("<" + "f" * (2 * a_count), b, offset)
    counts = list(map(float, floats[:a_count]))
    presence = list(map(float, floats[a_count:]))
    return counts, presence, None, None

  if magic == _CARD_MAGIC_V2:
    a_count, log_q_counts, log_q_presence = struct.unpack_from("<Iff", b, 4)
    offset = 4 + struct.calcsize("<Iff")
    expected = offset + 4 * 2 * a_count
    if len(b) != expected:
        raise ValueError("card blob has unexpected length")

    floats = struct.unpack_from("<" + "f" * (2 * a_count), b, offset)
    counts = list(map(float, floats[:a_count]))
    presence = list(map(float, floats[a_count:]))
    return counts, presence, float(log_q_counts), float(log_q_presence)

  raise ValueError("invalid card magic")


def blob_to_db_value(blob: bytes, *, force_base64: bool = False) -> Any:
  """Return a value suitable for D1 parameter binding.

  - Prefer binding raw bytes (BLOB).
  - If an environment can't bind BLOBs, store base64 in TEXT.
  """

  if force_base64:
    return "b64:" + base64.b64encode(blob).decode("ascii")
  return blob
