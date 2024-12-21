from fastapi import FastAPI
from fastapi.responses import JSONResponse

from asi import find_nearest_archetypes
from artifacts import *

async def on_fetch(request, env):
  # pylint: disable=import-error
  import asgi
  return await asgi.fetch(app, request, env)

app = FastAPI()

@app.post("/")
async def get_scores(request: list[str], format: str):
  bigrams: dict[str, int] = None
  match format:
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
      return JSONResponse(content={"error": "Invalid format"}, status_code=400)

  scores = find_nearest_archetypes(bigrams, request)
  return JSONResponse(content={ k: round(v, 4) for k, v in scores.items() })
