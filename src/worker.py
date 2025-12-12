## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""Cloudflare worker script for classifying archetypes with NBAC."""

from json import dumps as json_dumps

from nbac import decode_meta, explain_deck, score_deck
from router import Router, JSONResponse, get_endpoint, get_parameters


api = Router()

@api.post('/nbac')
async def index(request, params, env):
  try:
    body = (await request.json()).to_py()
    assert isinstance(body, list), "Received a non-array JSON object."
  except:
    return JSONResponse({
      "error": "Invalid JSON",
      "message": "The request body must be a valid JSON array."
    }, status=400)
  if len(body) == 0:
    return JSONResponse({
      "error": "Invalid JSON",
      "message": "The request body must contain at least one card."
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

  model_kind = None
  deck_counts: dict[str, int] = {}
  # Payload can be:
  # - ["Card Name", ...]                     -> presence model (k_c = 1)
  # - [{"name": "Card", "quantity": 4}, ...] -> counts model
  try:
    if all(isinstance(x, str) for x in body):
      model_kind = "presence"
      for name in body:
        if not isinstance(name, str) or len(name) == 0:
          continue
        deck_counts[name] = 1
    elif all(isinstance(x, dict) for x in body):
      model_kind = "counts"
      for obj in body:
        name = obj.get("name", None)
        qty = obj.get("quantity", None)
        if not isinstance(name, str) or len(name) == 0:
          continue
        if not isinstance(qty, int):
          raise ValueError("quantity must be an integer")
        if qty <= 0:
          continue
        # Clip per spec.
        deck_counts[name] = min(4, deck_counts.get(name, 0) + qty)
    else:
      raise ValueError("Mixed or unsupported array element types")
  except Exception as e:
    return JSONResponse({
      "error": "Invalid JSON",
      "message": str(e)
    }, status=400)

  if len(deck_counts) == 0:
    return JSONResponse({
      "error": "Invalid JSON",
      "message": "The request body must contain at least one valid card."
    }, status=400)

  cards = list(deck_counts.keys())

  # Optional explainability output.
  explain = params.get("explain", "0") in ["1", "true", "True", "yes", "on"]
  explain_top = 1
  explain_n = 12
  explain_method = str(params.get("explain_method", "lift")).lower()
  if explain_method not in ["lift", "contrib"]:
    explain_method = "lift"
  try:
    if "explain_top" in params:
      explain_top = int(params.get("explain_top"))
    if "explain_n" in params:
      explain_n = int(params.get("explain_n"))
  except:
    return JSONResponse({
      "error": "Invalid parameter",
      "message": "The 'explain_top' and 'explain_n' parameters must be integers."
    }, status=400)

  if explain_top < 1:
    explain_top = 1
  if explain_top > 25:
    explain_top = 25

  if explain_n < 1:
    explain_n = 1
  if explain_n > 25:
    explain_n = 25

  try:
    cards_table = f"{format}_nbac_cards"
    meta_table = f"{format}_nbac_meta"

    meta_result = await env.D1.prepare(f"""
      SELECT entry FROM {meta_table} WHERE key = 'meta';
    """).all()

    if not meta_result.success:
      raise Exception(meta_result.error)
    if meta_result.results.length == 0:
      raise Exception("Missing NBAC meta for this format.")

    meta_entry = meta_result.results.to_py()[0]["entry"]
    meta = decode_meta(meta_entry)

    d1_result = await env.D1.prepare(f"""
      SELECT card, entry FROM {cards_table}
      JOIN (SELECT value FROM json_each(?)) ON card = value;
    """).bind(json_dumps(cards)).all()

    if not d1_result.success:
      raise Exception(d1_result.error)

    d1_meta = d1_result.meta.to_py()

    card_entries = {}
    for row in d1_result.results.to_py():
      card = row.get("card")
      entry = row.get("entry")
      if isinstance(card, str):
        card_entries[card] = entry

  except Exception as e:
    return JSONResponse({
      "error": "Query error",
      "message": str(e)
    }, status=500)

  probs = score_deck(
    meta,
    deck_counts=deck_counts,
    model_kind=model_kind,
    card_blobs=card_entries,
  )

  # Filter to archetypes with probability > 0.05 and return top-k.
  MIN_PROB = 0.05
  ranked = sorted(
    [(a, p) for a, p in probs.items() if p > MIN_PROB],
    key=lambda kv: kv[1],
    reverse=True
  )[:25]

  response = {
    "meta": {
      "database": "D1",
      "backend": d1_meta["served_by"],
      "exec_ms": d1_meta["duration"],
      "read_count": d1_meta["rows_read"],
      "model": model_kind,
    },
    "data": { archetype: round(score, 8) for archetype, score in ranked }

  }

  if explain:
    # Prefer lift if available; otherwise fall back to contrib.
    supports_lift = False
    for card, blob in card_entries.items():
      if blob is None:
        continue
      try:
        from nbac.binary import decode_card_entry
        _, _, log_q_counts, log_q_presence = decode_card_entry(blob)
        log_q = log_q_counts if model_kind == "counts" else log_q_presence
        if log_q is not None:
          supports_lift = True
          break
      except:
        continue

    use_lift = explain_method == "lift" and supports_lift
    method_used = "lift" if use_lift else "contrib"

    explain_arch = {}
    for archetype, _ in ranked[:explain_top]:
      evidence = explain_deck(
        meta,
        deck_counts=deck_counts,
        model_kind=model_kind,
        card_blobs=card_entries,
        archetype=archetype,
        top_n=explain_n,
        use_lift=use_lift,
      )
      explain_arch[archetype] = [
        {
          "card": card,
          "quantity": int(deck_counts.get(card, 0)),
          "score": round(float(score), 8),
        }
        for card, score in evidence
      ]

    response["explain"] = {
      "method": method_used,
      "top": explain_top,
      "n": explain_n,
      "archetypes": explain_arch,
    }

  return JSONResponse(response)

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
