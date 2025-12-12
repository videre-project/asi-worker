## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""PostgreSQL utilities for the NBAC build."""

from __future__ import annotations

from atexit import register as on_exit
from hashlib import md5
from os import environ as env

from psycopg2 import pool
from psycopg2.extensions import QuotedString, cursor

try:
  from dotenv import load_dotenv
  load_dotenv()
except ImportError:
  pass


connection_pool: pool.SimpleConnectionPool | None = None
connection_count: int = 0


def start_pool(minconn: int = 1, maxconn: int = 10, url: str = env['DATABASE_URL']) -> None:
  global connection_pool
  if connection_pool is not None:
    return

  if 'DATABASE_URL' not in env:
    raise ValueError("No DATABASE_URL in environment")

  connection_pool = pool.SimpleConnectionPool(minconn, maxconn, url, connect_timeout=600)


def close_pool():
  global connection_pool, connection_count
  if connection_pool is not None and connection_count == 0:
    connection_pool.closeall()
    connection_pool = None


def get_cursor() -> cursor:
  global connection_pool, connection_count
  start_pool()

  assert connection_pool is not None

  conn = connection_pool.getconn()
  connection_count += 1
  cur = conn.cursor()

  def cleanup():
    global connection_pool, connection_count
    cur.close()
    assert connection_pool is not None
    connection_pool.putconn(conn)
    connection_count -= 1

  on_exit(cleanup)
  on_exit(close_pool)

  return cur


def parse_decklist(decklist_str: str) -> list[dict[str, int]]:
  """Parse a decklist string from a JSON blob into a list of card dictionaries."""

  # Unescape postgresql string literals
  decklist_str = QuotedString(decklist_str)\
    .getquoted()\
    .decode('iso-8859-1')[1:-1]

  # If the decklist is empty, return an empty list
  if decklist_str == '{}': return []

  # Here, we're left with a string containing a bunch of tuples, e.g.
  # "(67210,\"Simian Spirit Guide\",4)","(22775,\"Blood Moon\",4)", ...
  decklist = decklist_str.split('\",\"')
  tuples = []
  for card in decklist:
    # Remove the leading and trailing parentheses
    card = card.replace('"(','').replace(')"','')

    if card.count(',') != 2 or ' ' in card:
      card = ((card.replace('{"','')[1:-1])
        # Replace quotes surrounding commas with a placeholder
        .replace(',\\"', '~,~')
        .replace('\\",', '~,~')
        .split('~,~'))

      if len(card) != 3:
        raise ValueError("Card tuple has unexpected number of elements: " + str(card))

      card[1] = (card[1]
        # Unescape single-quotes
        .replace("''", "'")
        # Unescape double-escaped quotes
        .replace('\\"\\"', '"'))
    else:
      card = card[1:-1].split(',')

    # Append the tuple to the list
    tuples.append(tuple(int(x) if x.isdigit() else x for x in card))

  # Consolidate multiple tuples for the same card name.
  consolidated = {}
  for card in tuples:
    name, quantity = card[1], card[2]
    consolidated[name] = consolidated.get(name, 0) + quantity

  return [{ 'name': name,
            'quantity': quantity } for name, quantity in consolidated.items()]


def hash_str(s: str) -> str:
  return md5(s.encode('utf-8')).hexdigest()


def hash_bytes(b: bytes) -> str:
  return md5(b).hexdigest()


__all__ = [
  'start_pool',
  'get_cursor',
  'parse_decklist',
  'hash_str',
  'hash_bytes',
]
