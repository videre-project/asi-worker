## @file
# Copyright (c) 2025, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""NBAC training utilities."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import exp, log
from time import time

from .archetypes import analyze_archetypes, normalize_label
from .binary import encode_card_entry
from .model import NBACMeta, NBACModel, NBACModelParams


@dataclass(frozen=True)
class TrainedArtifacts:
  meta: NBACMeta
  # card -> encoded BLOB entry
  cards: dict[str, bytes]


def train_nbac(
  corpus: list[tuple],
  *,
  alpha: float = 1.0,
  background_lambda: float = 0.15,
  temperature_counts: float = 1.0,
  temperature_presence: float = 1.0,
  clip_qty: int = 4,
  self_filter_rho: float = 0.0,
) -> TrainedArtifacts:
  """Train two multinomial NB models:

  - counts: uses clipped mainboard quantities
  - presence: binarized mainboard (k_c ∈ {0,1})

  Returns binary artifacts suitable for Cloudflare D1 storage.

  If `self_filter_rho` is > 0, performs the spec's one-pass self-filtering:
  train an initial model, drop the bottom fraction `rho` of decks within each
  archetype by $P(A \\mid D)$, then retrain on the filtered corpus.
  """

  def _train_once(entries: list[tuple]) -> tuple[TrainedArtifacts, dict[str, list[float]]]:
    analyzed = analyze_archetypes(entries)
    allowed = set(analyzed.keys())

    archetypes = list(analyzed.keys())
    a_index = {a: i for i, a in enumerate(archetypes)}

    # counts[model][archetype][card] -> int
    counts_counts: list[defaultdict[str, int]] = [defaultdict(int) for _ in archetypes]
    counts_presence: list[defaultdict[str, int]] = [defaultdict(int) for _ in archetypes]

    decks_per_arch = [0 for _ in archetypes]
    vocab: set[str] = set()

    for entry in entries:
      label = normalize_label(entry, allowed)
      if label is None:
        continue
      idx = a_index[label]
      decks_per_arch[idx] += 1

      mainboard = entry[5]
      seen: set[str] = set()
      for c in mainboard:
        name = str(c["name"])
        qty = int(c["quantity"])
        if qty <= 0:
          continue

        vocab.add(name)

        # counts model
        qty_c = min(clip_qty, qty)
        counts_counts[idx][name] += qty_c

        # presence model
        if name not in seen:
          counts_presence[idx][name] += 1
          seen.add(name)

    total_decks = sum(decks_per_arch)
    if total_decks == 0:
      raise ValueError("no labeled decks after normalization")

    cards = sorted(vocab)
    v_size = len(cards)

    # Background counts per model
    bg_counts_counts: defaultdict[str, int] = defaultdict(int)
    bg_counts_presence: defaultdict[str, int] = defaultdict(int)

    mass_counts = [0 for _ in archetypes]
    mass_presence = [0 for _ in archetypes]

    for i in range(len(archetypes)):
      for card, n in counts_counts[i].items():
        bg_counts_counts[card] += n
        mass_counts[i] += n
      for card, n in counts_presence[i].items():
        bg_counts_presence[card] += n
        mass_presence[i] += n

    bg_mass_counts = sum(bg_counts_counts.values())
    bg_mass_presence = sum(bg_counts_presence.values())

    denom_counts = [m + alpha * v_size for m in mass_counts]
    denom_presence = [m + alpha * v_size for m in mass_presence]
    denom_bg_counts = bg_mass_counts + alpha * v_size
    denom_bg_presence = bg_mass_presence + alpha * v_size

    def _unseen_prime(denom_a: float, denom_bg: float) -> float:
      unseen = alpha / denom_a
      bg_unseen = alpha / denom_bg
      return (1.0 - background_lambda) * unseen + background_lambda * bg_unseen

    log_unseen_counts = [log(_unseen_prime(denom_counts[i], denom_bg_counts)) for i in range(len(archetypes))]
    log_unseen_presence = [log(_unseen_prime(denom_presence[i], denom_bg_presence)) for i in range(len(archetypes))]

    log_prior = [log(decks_per_arch[i] / total_decks) for i in range(len(archetypes))]

    meta = NBACMeta(
      version=1,
      build_unix=int(time()),
      archetypes=archetypes,
      counts=NBACModel(
        kind="counts",
        params=NBACModelParams(alpha=alpha, background_lambda=background_lambda, temperature=temperature_counts),
        log_prior=log_prior,
        log_unseen=log_unseen_counts,
      ),
      presence=NBACModel(
        kind="presence",
        params=NBACModelParams(alpha=alpha, background_lambda=background_lambda, temperature=temperature_presence),
        log_prior=log_prior,
        log_unseen=log_unseen_presence,
      ),
    )

    artifacts: dict[str, bytes] = {}
    theta_counts_by_card: dict[str, list[float]] = {}

    # Build per-card dense arrays for both models.
    for card in cards:
      # background q per model
      q_counts = (bg_counts_counts.get(card, 0) + alpha) / denom_bg_counts
      q_presence = (bg_counts_presence.get(card, 0) + alpha) / denom_bg_presence

      log_q_counts = log(q_counts)
      log_q_presence = log(q_presence)

      log_theta_counts: list[float] = []
      log_theta_presence: list[float] = []

      for i in range(len(archetypes)):
        # counts
        theta = (counts_counts[i].get(card, 0) + alpha) / denom_counts[i]
        theta_p = (1.0 - background_lambda) * theta + background_lambda * q_counts
        log_theta_counts.append(log(theta_p))

        # presence
        theta2 = (counts_presence[i].get(card, 0) + alpha) / denom_presence[i]
        theta2_p = (1.0 - background_lambda) * theta2 + background_lambda * q_presence
        log_theta_presence.append(log(theta2_p))

      theta_counts_by_card[card] = log_theta_counts
      artifacts[card] = encode_card_entry(
        log_theta_counts,
        log_theta_presence,
        log_q_counts=log_q_counts,
        log_q_presence=log_q_presence,
      )

    return TrainedArtifacts(meta=meta, cards=artifacts), theta_counts_by_card

  # Default: single-pass training.
  artifacts, theta_counts_by_card = _train_once(corpus)

  rho = float(self_filter_rho)
  if rho <= 0.0:
    return artifacts
  if rho >= 1.0:
    rho = 1.0

  # One-pass self-filtering using the initial counts model.
  model = artifacts.meta.counts
  archetypes = artifacts.meta.archetypes
  a_index = {a: i for i, a in enumerate(archetypes)}

  # Determine which labels are valid for scoring (must appear in the initial model).
  allowed = set(archetypes)

  scored_by_label: dict[str, list[tuple[float, tuple]]] = {a: [] for a in archetypes}
  for entry in corpus:
    label = normalize_label(entry, allowed)
    if label is None:
      continue
    label_idx = a_index[label]

    mainboard = entry[5]
    deck_counts: dict[str, int] = {}
    for c in mainboard:
      name = str(c["name"])
      qty = int(c["quantity"])
      if qty <= 0:
        continue
      deck_counts[name] = deck_counts.get(name, 0) + min(clip_qty, qty)

    total_mass = 0
    for qty in deck_counts.values():
      if qty > 0:
        total_mass += int(qty)

    log_scores = [model.log_prior[i] + total_mass * model.log_unseen[i] for i in range(len(archetypes))]

    for card, qty in deck_counts.items():
      if qty <= 0:
        continue
      log_theta = theta_counts_by_card.get(card)
      if log_theta is None:
        continue
      k = int(qty)
      for i in range(len(archetypes)):
        log_scores[i] += k * (log_theta[i] - model.log_unseen[i])

    # Stable softmax; use uncalibrated scores for filtering.
    max_s = max(log_scores)
    exps = [exp(s - max_s) for s in log_scores]
    z = sum(exps)
    if z <= 0:
      continue
    p_label = exps[label_idx] / z
    scored_by_label[label].append((float(p_label), entry))

  filtered: list[tuple] = []
  for label, items in scored_by_label.items():
    if not items:
      continue
    items.sort(key=lambda kv: kv[0], reverse=True)
    keep_n = int((1.0 - rho) * len(items))
    if keep_n < 1:
      keep_n = 1
    filtered.extend([e for _, e in items[:keep_n]])

  artifacts2, _ = _train_once(filtered)
  return artifacts2
