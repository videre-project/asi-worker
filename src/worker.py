## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""Cloudflare worker script for calculating the nearest archetypes with ASI."""

from pyodide.ffi import JsArray

from asi import find_nearest_archetypes
from artifacts import *

from router import Router, JSONResponse, get_endpoint, get_parameters


api = Router()

@api.post('/')
async def index(request, params, env):
  try:
    cards = await request.json()
    # The returned card object will be a `JsProxy` object, which we'll need to
    # probe to check the kind of JSON object returned to us.
    assert type(cards).__name__ == "JsProxy"
    assert cards.typeof == "object"
  except:
    return JSONResponse({
      "error": "Invalid JSON",
      "message": "The request body must be a valid JSON object."
    }, status=400)
  else:
    if not isinstance(cards, JsArray):
      return JSONResponse({
        "error": "Invalid JSON",
        "message": "The request body must be a valid JSON array. " +
                  f"to_py: {cards.to_py}" +
                  f"Got type '{str(dir(cards))}'."
      }, status=400)
    elif cards.length < 2:
      return JSONResponse({
        "error": "Invalid JSON",
        "message": "The request body must contain at least two cards."
      }, status=400)

  bigrams: dict[str, int] = None
  match (format := params.get("format", None)):
    case "standard":
      bigrams = standard_bigrams
    case "modern":
      bigrams = modern_bigrams
    case "pioneer":
      bigrams = pioneer_bigrams
    case "vintage":
      bigrams = vintage_bigrams
    case "legacy":
      bigrams = legacy_bigrams
    case "pauper":
      bigrams = pauper_bigrams
    case _:
      if format is None or len(format) == 0:
        return JSONResponse({
          "error": "Missing parameter",
          "message": "The 'format' parameter is required."
        }, status=400)

      return JSONResponse({
        "error": "Invalid format",
        "message": f"The 'format' parameter '{format}' is not supported."
      }, status=400)

  return JSONResponse(find_nearest_archetypes(bigrams, cards))

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
