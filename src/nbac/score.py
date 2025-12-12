## @file
# Copyright (c) 2025, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""NBAC scoring and explanation utilities."""

from __future__ import annotations

from math import exp

from .binary import decode_card_entry
from .model import ModelKind, NBACMeta


def score_deck(
  meta: NBACMeta,
  *,
  deck_counts: dict[str, int],
  model_kind: ModelKind,
  card_blobs: dict[str, object],
) -> dict[str, float]:
  """Score a deck and return normalized posteriors.

  `card_blobs` maps card name -> D1 `entry` blob.
  """

  model = meta.model(model_kind)
  a_count = len(meta.archetypes)

  # Total mass for multinomial NB.
  total_mass = 0
  for qty in deck_counts.values():
    if qty > 0:
      total_mass += int(qty)

  # Initialize scores with log prior + total_mass * log_unseen.
  log_scores = [model.log_prior[i] + total_mass * model.log_unseen[i]
                for i in range(a_count)]

  # Add per-card contributions for cards we have weights for.
  for card, qty in deck_counts.items():
    if qty <= 0:
      continue
    blob = card_blobs.get(card)
    if blob is None:
      continue
    log_theta_counts, log_theta_presence, _, _ = decode_card_entry(blob)
    log_theta = log_theta_counts if model_kind == "counts" else log_theta_presence

    k = int(qty)
    # log_scores[A] += k * (log_theta[A] - log_unseen[A])
    for i in range(a_count):
      log_scores[i] += k * (log_theta[i] - model.log_unseen[i])

  # Temperature-scaled softmax
  t = float(model.params.temperature) if model.params.temperature > 0 else 1.0
  scaled = [s / t for s in log_scores]
  max_s = max(scaled)
  exps = [exp(s - max_s) for s in scaled]
  z = sum(exps)
  if z == 0:
    return {}

  probs = {meta.archetypes[i]: exps[i] / z for i in range(a_count)}
  return probs


def top_k(probs: dict[str, float], k: int = 10) -> list[tuple[str, float]]:
  if k <= 0:
    return []
  return sorted(probs.items(), key=lambda kv: kv[1], reverse=True)[:k]


def is_ambiguous(
  probs: dict[str, float],
  *,
  p_min: float = 0.0,
  delta: float = 0.0,
) -> bool:
  """Ambiguity policy from the spec (top-1 too low or top-1/top-2 too close)."""
  if not probs:
    return True
  ranked = top_k(probs, 2)
  p1 = ranked[0][1]
  p2 = ranked[1][1] if len(ranked) > 1 else 0.0
  return (p1 < p_min) or ((p1 - p2) < delta)


def explain_deck(
  meta: NBACMeta,
  *,
  deck_counts: dict[str, int],
  model_kind: ModelKind,
  card_blobs: dict[str, object],
  archetype: str,
  top_n: int = 12,
  use_lift: bool = False,
) -> list[tuple[str, float]]:
  """Return per-card evidence for a specific archetype.

  - contrib: k_c * log(theta')
  - lift: k_c * (log(theta') - log(q)) if q is available (requires NBC2 entries)
  """
  if top_n <= 0:
    return []
  try:
    a_idx = meta.archetypes.index(archetype)
  except ValueError:
    return []

  out: list[tuple[str, float]] = []
  for card, qty in deck_counts.items():
    if qty <= 0:
      continue
    blob = card_blobs.get(card)
    if blob is None:
      continue
    log_theta_counts, log_theta_presence, log_q_counts, log_q_presence = decode_card_entry(blob)
    log_theta = log_theta_counts if model_kind == "counts" else log_theta_presence
    log_q = log_q_counts if model_kind == "counts" else log_q_presence

    k = int(qty)
    if use_lift and log_q is not None:
      score = k * (log_theta[a_idx] - float(log_q))
    else:
      score = k * log_theta[a_idx]
    out.append((card, float(score)))

  out.sort(key=lambda kv: kv[1], reverse=True)
  return out[:top_n]
