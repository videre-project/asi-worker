## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""Module for computing joint hypergeometric probabilities of card bigrams."""

from collections import OrderedDict
from math import gamma

from .archetypes import MACRO_ARCHETYPES, remove_colors, analyze_archetypes


def comb(n: float, k: float) -> float:
  """Calculates the binomial coefficient C(n, k) = n! / (k! * (n - k)!).

  Args:
    n: The total number of items.
    k: The number of items to choose.

  Returns:
    The binomial coefficient C(n, k).
  """

  # Convert to int for integer operations, but handle edge cases first
  if k < 0 or k > n or n < 0:
    return 0
  if k == 0 or k == n:
    return 1
  
  # Handle large values that would cause overflow
  if n > 170 or k > 170:
    return 0
  
  # Use symmetry property: C(n, k) = C(n, n-k)
  k = min(k, n - k)
  
  # For small values, use direct calculation
  if k == 1:
    return n
  if k == 2:
    return n * (n - 1) / 2
  
  # C(n, k) = n! / (k! * (n - k)!)
  try:
    return gamma(n + 1) / (gamma(k + 1) * gamma(n - k + 1))
  except (OverflowError, ValueError):
    return 0

def hypergeo(K: float, N: float = 60, n: int = 1, n_draws: int = 7) -> float:
  """Calculates the hypergeometric probability of drawing at least n successes.

  Args:
    K: The number of successes in the population.
    N: The population size.
    n: The minimum number of successes in the sample.
    n_draws: The sample size.

  Returns:
    The hypergeometric probability of drawing at least n successes.
  """
  
  # Guard against invalid parameters
  if K < 0 or N < 0 or n_draws < 0 or n < 0:
    return 0 # Invalid parameters
  
  if n_draws > N:
    return 0 # Cannot draw more than population size
  
  if K < n:
    return 0 # Cannot get n successes if fewer than n exist
  
  if n > n_draws:
    return 0 # Cannot get more successes than draws
  
  if n == 0:
    return 1 # Probability of getting at least 0 successes is always 1
  
  # Avoid division by zero
  if (denominator := comb(N, n_draws)) == 0: return 0
  
  return sum((comb(K, i) * comb(N - K, n_draws - i)) / denominator
             for i in range(n, n_draws + 1))

def compute_archetype_bigrams(archetypes: list[tuple]) -> dict[tuple, dict]:
  """Computes the joint hypergeometric probabilities for each card pair (bigram)
    in the given list of archetypes, grouped by archetype name.

  Args:
    archetypes: A list of archetype entries, where each entry is a tuple
      containing the following fields:
        0: The archetype ID.
        1: The archetype name.
        2: The archetype base name.
        3: The archetype color identity.
        4: The archetype format.
        5: The archetype mainboard.

  Returns:
    A dictionary of bigrams, where each key is a tuple of card names and each
    value is a dictionary of archetype names and their corresponding joint
    hypergeometric probabilities for the given card pair.
  """

  bigram_counts: dict[tuple[str, str], dict[str, tuple[int, int, int, int]]] = {}

  archetype_names = analyze_archetypes(archetypes)
  for entry in archetypes:
    # Skip if there isn't a valid archetype name associated with the deck.
    base_name = remove_colors(entry[2])
    archetype = base_name \
                    if base_name in archetype_names and \
                        base_name not in MACRO_ARCHETYPES \
                    else entry[2]
    if archetype not in archetype_names or not isinstance(archetype, str):
      continue

    # Create a bigram for each pair of cards in the deck and sum the quantities.
    mainboard = entry[5]
    cards = set(c["name"] for c in mainboard)
    count = sum(c["quantity"] for c in mainboard)
    for bigram in (tuple(sorted([c1, c2])) for c1 in cards 
                                          for c2 in cards if c1 != c2):
      if bigram not in bigram_counts:
        bigram_counts[bigram] = {}
      if archetype not in bigram_counts[bigram]:
        bigram_counts[bigram][archetype] = (0, 0, 0, 0)

      # Sum the quantities for all copies of the card in the maindeck (since
      # there may be multiple entries for the same card under different IDs).
      qty1 = sum(c["quantity"] for c in mainboard if c["name"] == bigram[0])
      qty2 = sum(c["quantity"] for c in mainboard if c["name"] == bigram[1])

      bigram_counts[bigram][archetype] = (bigram_counts[bigram][archetype][0] + qty1,
                                    bigram_counts[bigram][archetype][1] + qty2,
                                    bigram_counts[bigram][archetype][2] + count,
                                    bigram_counts[bigram][archetype][3] + 1)

  # Convert counts to probabilities
  bigrams: dict[tuple[str, str], dict[str, float]] = {}
  for key, entry in bigram_counts.items():
    bigrams[key] = {}
    for archetype, (qty1, qty2, total, count) in entry.items():
      #
      # Calculate joint probability of the bigram appearing in an opening hand,
      # given the marginal probabilities of each card in the bigram being drawn.
      # 
      # Here the joint probability is p(x,y) = 1 - (p(~x) + p(~y) - p(~x,~y)),
      # where p(x) and p(y) are the probabilities of drawing the two cards, and
      # p(x,y) is the joint probability of drawing both cards.
      #
      N = total / count
      P_A = hypergeo(k1 := qty1 / count, N)
      P_B = hypergeo(k2 := qty2 / count, N)
      P_AB = 1 - ((1 - P_A) + (1 - P_B) - hypergeo(N - k1 - k2, N))

      # Normalize the joint probability by the maximum joint probability.
      k_max = max(4, (k1 + k2) / 2)
      P_MAX = 1 - (1 - hypergeo(k_max, N))**2
      bigrams[key][archetype] = min(1, P_AB / P_MAX)

    # Re-sort the bigrams by their joint probabilities for each archetype entry.
    bigrams[key] = OrderedDict(sorted(
      bigrams[key].items(),
      key=lambda item: item[1], reverse=True
    ))

  return bigrams


__all__ = [
  # Functions (3)
  'comb',
  'hypergeo',
  'compute_archetype_bigrams'
]
