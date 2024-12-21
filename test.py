## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""Test script for verifying consistency of the ASI metric."""

from datetime import datetime, timedelta
from pathlib import Path
from pprint import pprint
from random import sample
from json import dumps, loads

from src.asi import remove_colors, fetch_archetypes, \
                    find_nearest_archetypes, compute_archetype_bigrams


def load_bigrams(filename: str):
  # Access the 'archetypes' variable from the top-level scope
  global archetypes

  file = Path(filename)
  if not file.exists():
    bigrams = compute_archetype_bigrams(archetypes)
    # Convert tuples to lists for JSON serialization

    # Convert tuples to lists for JSON serialization
    file.write_text(dumps({ dumps(k): v for k, v in bigrams.items()}, indent=2))
  else:
    # Convert lists back to tuples
    bigrams = { tuple(loads(k)): v for k, v in loads(file.read_text()).items() }

  return bigrams

format = 'modern'
min_date = (date := datetime.now()) - timedelta(days=90)
archetypes = fetch_archetypes(format, min_date)
bigrams = load_bigrams(f'{format}_3M_{date:%Y%m%d}.json')

# Get our random archetypes from the 'archetypes' list
n_test = 25
n_cards = 15
for archetype in filter(lambda e: e[4] >= min_date.date(),
                        sample(archetypes, n_test)):
  # Create a random subset of the mainboard
  mainboard = sample(list(c["name"] for c in archetype[5]), n_cards)
  nearest = find_nearest_archetypes(bigrams, mainboard)

  nearest_archetype = list(nearest.keys())[0]
  if remove_colors(archetype[2]) != nearest_archetype and \
      archetype[2] != nearest_archetype:
    # Print the archetype and it's scored nearest archetypes
    print(f"\nNearest archetype to {archetype[1]} ({archetype[2]}):")
    for name, score in filter(lambda kv: kv[1] >= 0.20, 
                              nearest.items()):
      print(f"  {name}: {score:.2f}")

    # Print the randomly selected mainboard
    print('\nSampled Mainboard:')
    pprint(list(mainboard))
