## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""Cloudflare worker script for calculating the nearest archetypes with ASI."""

from json import dumps as json_dumps, loads as json_loads

from asi import find_nearest_archetypes
from router import Router, JSONResponse, get_endpoint, get_parameters


api = Router()

@api.post('/asi')
async def index(request, params, env):
  try:
    body: list[str] = (await request.json()).to_py()
    assert isinstance(body, list), "Received a non-array JSON object."
  except:
    return JSONResponse({
      "error": "Invalid JSON",
      "message": "The request body must be a valid JSON array."
    }, status=400)
  else:
    if len(body) < 2:
      return JSONResponse({
        "error": "Invalid JSON",
        "message": "The request body must contain at least two cards."
      }, status=400)

  format: str = params.get("format", None)
  if format is None or len(format) == 0:
    return JSONResponse({
      "error": "Missing parameter",
      "message": "The 'format' parameter is required."
    }, status=400)
  elif (format := format.lower()) not in [
    'standard', 'modern', 'pioneer', 'vintage', 'legacy', 'pauper',
  ]:
    return JSONResponse({
      "error": "Invalid format",
      "message": f"The 'format' parameter '{format}' is not supported."
    }, status=400)

  cards = [c.lower() for c in body]
  bigrams: dict[tuple[str, str], any] = {}
  try:
    d1_result = await env.D1.prepare(f"""
      SELECT card, entry FROM {format}
      JOIN (SELECT value FROM json_each(?)) ON card = value;
    """).bind(json_dumps(cards)).all()

    if not d1_result.success:
      raise Exception(d1_result.error)
    elif d1_result.results.length == 0:
      raise Exception("No matching cards found in the database.")
    else:
      d1_meta = d1_result.meta.to_py()

    bigram_entries = d1_result.results.to_py()
    for row in bigram_entries:
      card1, jsonb = row.values()
      for card2, entry in json_loads(jsonb).items():
        if card2 in cards:
          bigrams[(card1, card2)] = entry

  except Exception as e:
    return JSONResponse({
      "error": "Query error",
      "message": str(e)
    }, status=500)

  matches = find_nearest_archetypes(bigrams, cards)
  return JSONResponse({
    "meta": {
      "database": "D1",
      "backend": d1_meta["served_by"],
      "exec_ms": d1_meta["duration"],
      "read_count": d1_meta["rows_read"],
    },
    "data": { archetype: round(score, 8) for archetype, score in matches.items()
                                         if score > 0.05 }
  })

async def on_fetch(request, env):
  method: str = request.method
  endpoint = get_endpoint(request.url)
  params = get_parameters(request.url)

  if (handler := api.match(method, endpoint)):
    return await handler(request, params, env)
  else:
    return JSONResponse({
      'error': 'Invalid request method',
      'message': 'Did not match any request route handlers.'
    }, status=405)
