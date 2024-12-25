## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""PostgreSQL utilities for the ASI project."""

from atexit import register as on_exit
from hashlib import md5
from os import environ as env

from psycopg2 import pool
from psycopg2.extensions import QuotedString, cursor

# Load environment variables from a .env file if available
try:
  from dotenv import load_dotenv
  load_dotenv()
except ImportError:
  pass


# Create a global connection pool
connection_pool: pool.SimpleConnectionPool = None
connection_count: int = 0

def start_pool(minconn: int = 1,
               maxconn: int = 10,
               url: str=env['DATABASE_URL']) -> None:
  """Start the connection pool

  Args:
    minconn (int, optional): The minimum number of connections to keep in the
      pool. Defaults to 1.
    maxconn (int, optional): The maximum number of connections to keep in the
      pool. Defaults to 10.
    url (str, optional): The URL of the database to connect to. Defaults to
      the value of the DATABASE_URL environment variable.

  Raises:
    ValueError: If the connection pool has already been started.
  """

  # Check if the connection pool has already been started
  global connection_pool
  if connection_pool is not None:
    return

  # Check if there is a database URL in the environment
  if 'DATABASE_URL' not in env:
    raise ValueError("No DATABASE_URL in environment")

  connection_pool = pool.SimpleConnectionPool(minconn, maxconn, url,
                                              connect_timeout=600)
  
def close_pool():
  """Close all connections in the connection pool"""
  global connection_pool, connection_count
  if connection_pool is not None and connection_count == 0:
    connection_pool.closeall()
    connection_pool = None

def get_cursor() -> cursor:
  """Get a cursor to a database connection from the connection pool"""

  global connection_pool, connection_count
  start_pool()

  # Get a connection from the connection pool
  conn = connection_pool.getconn()
  connection_count += 1
  cur = conn.cursor()

  def cleanup():
    """Close the cursor and return the connection to the pool."""
    global connection_pool, connection_count
    cur.close()
    connection_pool.putconn(conn)
    connection_count -= 1

  # Register the cleanup function to be run when the program exits
  on_exit(cleanup)
  on_exit(close_pool)

  return cur

def parse_decklist(decklist_str: str) -> list[dict[str, int]]:
  """Parse a decklist string from a JSON blob into a list of card dictionaries.

  Args:
    decklist_str (str): A string representation of a decklist

  Returns:
    list[dict[str, int]]: A list of card dictionaries, each containing entries
      for the card name and quantity.
  """

  # Unescape postgresql string literals
  decklist_str = QuotedString(decklist_str)\
    .getquoted()\
    .decode('iso-8859-1')[1:-1]
  
  # If the decklist is empty, return an empty list
  if decklist_str == '{}': return []

  # Here, we're left with a string containing a bunch of tuples, e.g.
  # "(67210,\"Simian Spirit Guide\",4)","(22775,\"Blood Moon\",4)", ...
  # Where the first number is the card ID, the second is the card name, and the third is the quantity.
  # We can split this string into a list of tuples by splitting on '","'
  decklist = decklist_str.split('","')
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
  
  # Now we only care about the card name and quantity, and since the tuples are
  # separated by card ID, it's possible we have multiple tuples for the same card.
  # We can consolidate these by summing the quantities.
  consolidated = {}
  for card in tuples:
    name, quantity = card[1], card[2]
    consolidated[name] = consolidated.get(name, 0) + quantity

  # Finally, we return the decklist as 
  return [{ 'name': name,
            'quantity': quantity } for name, quantity in consolidated.items()]

def hash(e: str) -> str:
  """Hash a string using the MD5 algorithm.

  Args:
    e (str): The string to hash

  Returns:
    str: The hexadecimal representation of the MD5 hash of the input string.
  """
  return md5(e.encode('utf-8')).hexdigest()


__all__ = [
  # Functions (3)
  'start_pool',
  'get_cursor',
  'parse_decklist'
]
