## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
from cloudflare import Cloudflare
from datetime import datetime, timedelta
import json
from os import environ as env

# Since we aren't bundling this script, we can dynamically import src/ modules.
import sys; sys.path.append('src')

from asi import fetch_archetypes, compute_archetype_bigrams
from asi.postgres import start_pool

FORMATS = [
  'standard',
  'modern',
  'pioneer',
  'vintage',
  'legacy',
  'pauper',
]

MIN_DATE = (TIMESTAMP := datetime.now()) - timedelta(days=90)

# Start a PostgreSQL connection pool for the MTGO database.
start_pool()

# Setup a connection to the Cloudflare D1 API.
client = Cloudflare(
  api_key=env["CLOUDFLARE_API_KEY"],
  api_email=env["CLOUDFLARE_EMAIL"]
)
db = lambda query, **kwargs: client.d1.database.raw(
  database_id=env["CLOUDFLARE_DATABASE_ID"],
  account_id=env["CLOUDFLARE_ACCOUNT_ID"],
  sql=query,
  **kwargs
)

for format in FORMATS:
  # Create the table if it does not exist.
  # This doesn't consume any read/write operations if the table already exists.
  db(f"""
    CREATE TABLE IF NOT EXISTS {format} (
      card TEXT PRIMARY KEY,
      entry JSONB,
      hash TEXT DEFAULT MD5(entry),
      updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
  """)

  # Flatten bigrams into a single dictionary entry per card for better database
  # I/O efficiency. This reduces the n(n-1)/2 space complexity to just n.
  flattened_bigram: dict = {}
  bigrams = compute_archetype_bigrams(fetch_archetypes(format, MIN_DATE))
  for (card1, card2), value in bigrams.items():
    # Convert card names to lowercase for case-insensitive search.
    card1, card2 = card1.lower(), card2.lower()
    # Create nested dictionary entries for each card.
    if card1 not in flattened_bigram:
      flattened_bigram[card1] = {}
    flattened_bigram[card1][card2] = { k: round(v, 8) for k,v in value.items() }

  # Batch insert/update bigram entries in the database.
  # Allows for inserting 6,000 rows/minute (w/ 1200 requests every 5 minutes).
  batch_size = 50
  keys = list(flattened_bigram.keys())
  for i in range(0, len(keys), batch_size):
    batch_keys = keys[i:i + batch_size]
    batch: dict[str, dict] = { k: flattened_bigram[k] for k in batch_keys }
    res = db(f"""
      -- Insert or replace bigram entries into the database.
      INSERT OR REPLACE INTO {format} (card, entry, updated_at)
      SELECT value ->> 0 as card, value ->> 1 as entry, CURRENT_TIMESTAMP
      FROM json_each(?)
      -- Only insert new entries that do not already exist in the database.
      WHERE NOT EXISTS (
        SELECT 1 FROM {format}
        WHERE card = value ->> 0 AND hash = MD5(value ->> 1)
      )
      """,
      params=[json.dumps([[k, json.dumps(v)] for k, v in batch.items()])]
    )

  # Create an index on the updated_at column.
  db(f"CREATE INDEX IF NOT EXISTS {format}_updated_at ON {format} (updated_at)")
  
  # Delete old entries from the database (older than a month).
  db(f"DELETE FROM {format} WHERE updated_at < datetime('now', '-1 month')")
