## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""Module for fetching and analyzing archetypes from the Videre Project."""

from collections import Counter, OrderedDict
from datetime import datetime
import re


ARCHETYPE_COLORS = [
  # 1-color combinations
  'Mono-White', 'Mono-Blue', 'Mono-Black', 'Mono-Red', 'Mono-Green',
  'W',          'U',         'B',          'R',        'G',
  # 2-color combinations
  'Azorius', 'Orzhov', 'Boros', 'Selesnya', 'Dimir', 'Izzet', 'Rakdos',
  'WU',      'WB',     'WR',    'WG',       'UB',    'UR',    'BR',
  'Golgari', 'Gruul', 'Simic',
  'BG',      'RG',    'UG',
  # 3-color combinations
  'Jeskai', 'Grixis', 'Jund', 'Naya', 'Bant', 'Abzan', 'Sultai', 'Mardu',
  'WUR',    'UBR',    'BRG',  'WRG',  'GWU',  'WBG',   'UBG',    'WBR',
  'Temur', 'Esper', 'Bant',
  'URG',   'WUB',   'WUG',
  # 4/5-color combinations
  'WBRG', 'WURG', 'WUBG', 'WUBR', 'UBRG', 'WUBRG', '4c', '5c', '4/5c',
  # Specialty
  'Colorless', 'Snow',
  'C',         'S',
]

MACRO_ARCHETYPES = [
  'Aggro',
  'Control',
  'Midrange',
  'Combo',
  # Specialty
  'Prison',
  'Tempo',
  'Ramp',
]

def remove_colors(name):
  if name is None:
    return None

  for color in ARCHETYPE_COLORS:
    if color in name:
      name = re.sub(rf'^{color}\b', '', name, flags=re.IGNORECASE)
  return name.strip()

  # pattern = r'\b(?:' + '|'.join(map(re.escape, ARCHETYPE_COLORS)) + r')\b'
  # return re.sub(pattern, '', name, flags=re.IGNORECASE).strip()

def fetch_archetypes(format: str, date: datetime) -> list[tuple]:
  """Fetch archetypes from the Videre Project MTGO database.

  Args:
    format (str): The format to fetch archetypes for (e.g. 'standard', 'modern',
      'legacy', etc.)
    date (datetime): The date to query archetypes from. This restricts the query
      to only return archetypes from events that occurred on or after this date.
  
  Returns:
    list[tuple]: A list of archetypes, each represented as a tuple containing
      the archetype ID, name, archetype, format, date, mainboard, and sideboard.

  Raises:
    ValueError: If no archetypes are found for the given format and date.
  """

  # Delay import to avoid requiring build-time dependencies
  from .postgres import get_cursor, parse_decklist

  cur = get_cursor()
  cur.execute(f"""
    SELECT
      a.id,
      a.name,
      a.archetype,
      e.format,
      e.date,
      d.mainboard,
      d.sideboard
    FROM
      -- Start with smallest table first
      archetypes a
      -- Use INNER JOIN to only return matching rows
      INNER JOIN decks d ON a.deck_id = d.id
      INNER JOIN events e ON d.event_id = e.id
    WHERE
      a.id IS NOT NULL
      AND e.format = '{format.capitalize()}'
      AND e.date >= '{date.strftime('%Y-%m-%d')}'
  """)

  archetypes = cur.fetchall()
  if len(archetypes) == 0:
    raise ValueError(f'No archetypes found for {format} on or after {date}.')

  for i, archetype in enumerate(archetypes):
    mainboard = parse_decklist(archetype[5])
    sideboard = parse_decklist(archetype[6])
    archetypes[i] = archetype[:5] + (mainboard, sideboard)

  return archetypes

def analyze_archetypes(archetypes):
  analyzed = {}
  for archetype in archetypes:
    _, name, archetype_name, *_ = archetype
    # Skip if there isn't an archetype associated with the deck
    if archetype_name is None:
      continue
    # Skip if the archetype is a color combination
    elif name in ARCHETYPE_COLORS:
      assert len(remove_colors(name)) == 0
      continue
    elif (base_name := remove_colors(archetype_name)) not in MACRO_ARCHETYPES:
      archetype_name = base_name

    if archetype_name not in analyzed:
      analyzed[archetype_name] = {
        'name': Counter(),
        'count': 0
      }
    analyzed[archetype_name]['name'][name] += 1
    analyzed[archetype_name]['count'] += 1

  for archetype_name, counters in analyzed.items():
    analyzed[archetype_name]['name'] = dict(counters['name'])

  # Sort by count in descending order using OrderedDict
  analyzed = OrderedDict(sorted(analyzed.items(),
                                key=lambda item: item[1]['count'], reverse=True))

  return analyzed

def find_nearest_archetypes(
    bigrams: dict[tuple[str, str], dict[str, float]],
    decklist: list[str]):
  """Find the nearest archetypes to the given decklist.

  This function ranks archetypes by the number of shared card-pair bigrams with
  the given decklist. The bigrams are weighted by the joint probability of the
  two cards appearing together in the same deck and being drawn a 7-card hand.

  Args:
    bigrams (dict[str, dict[str, float]]): A dictionary of bigrams and their
      joint probabilities for each archetype. The bigrams are represented as
      tuples of card names, and the joint probabilities are normalized to the
      range [0, 1].
    decklist (dict[str, int]): A dictionary of card names and quantities in the
      decklist to compare against. The quantities are ignored.

  Returns:
    dict[str, float]: A dictionary of archetypes and their similarity scores.
  """

  # Sum the joint probabilities for each bigram present in the decklist for each
  # archetype; if the bigram is unique to an archetype, double its contribution.
  nearest = {}
  for (card1, card2), joint_probs in bigrams.items():
    if card1 in decklist and card2 in decklist:
      for archetype, joint_prob in joint_probs.items():
        if archetype not in nearest:
          nearest[archetype] = 0
        # Double the weight if there's only one bigram (i.e. it's a unique).
        weight = 2 if len(joint_probs) == 1 else 1
        nearest[archetype] += weight * joint_prob

  #
  # If we have several very close matches, we can compare each set of cards that
  # are unique to each archetype and give a bonus to the archetype that has the
  # most unique cards.
  #
  # We start by removing all cards that are shared among the nearest archetypes,
  # i.e. those that are within 2 pts of the highest score.
  #
  # Among our top archetypes, we filter each bigram to see which archetypes
  # match, and among them if only one archetype has that bigram, we can treat it
  # as a unique card for that archetype.
  #
  max_score = max(nearest.values())
  candidates = { a: w for a, w in nearest.items() if w >= max_score - 2 }
  for (card1, card2), joint_probs in bigrams.items():
    if card1 in decklist and card2 in decklist:
      filtered_joint_props = dict(filter(lambda kv: kv[0] in candidates,
                                         joint_probs.items()))
      weight = 2 if len(filtered_joint_props) == 1 else 1
      for archetype, joint_prob in filtered_joint_props.items():
        # For each archetype not in the filtered list, give it a penalty
        if archetype not in candidates:
          nearest[archetype] -= joint_prob
        # If the bigram is unique to the candidate archetype, give it a bonus
        elif len(filtered_joint_props) < len(candidates)//3:
          nearest[archetype] += weight * joint_prob

  # Normalize the scores by the maximum joint probability for each bigram
  # present in the decklist.
  max_score = 0
  for (card1, card2), joint_probs in bigrams.items():
    if card1 in decklist and card2 in decklist:
      max_score += max(joint_probs.values())
  for archetype in nearest:
    nearest[archetype] = min(1, nearest[archetype] / max_score)

  # Sort the archetypes by their final similarity scores.
  nearest = OrderedDict(sorted(
    nearest.items(),
    key=lambda item: item[1],
    reverse=True
  ))

  return nearest


__all__ = [
  # Constants (2)
  'ARCHETYPE_COLORS',
  'MACRO_ARCHETYPES',
  # Functions (4)
  'remove_colors',
  'fetch_archetypes',
  'analyze_archetypes',
  'find_nearest_archetypes',
]
