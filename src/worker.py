from fastapi import FastAPI
from fastapi.responses import JSONResponse

from asi import find_nearest_archetypes
from artifacts import *

async def on_fetch(request, env):
  # pylint: disable=import-error
  import asgi
  return await asgi.fetch(app, request, env)

app = FastAPI()


cardnames = [
  "Agatha's Soul Cauldron",
  "Ancient Stirrings",
  "Basking Broodscale",
  "Blade of the Bloodchief",
  "Boseiju, Who Endures",
  "Darksteel Citadel",
  "Eldrazi Temple",
  "Forest",
  "Gemstone Caverns",
  "Glaring Fleshraker",
  "Grove of the Burnwillows",
  "Haywire Mite",
  "Kozilek's Command",
  "Malevolent Rumble",
  "Mishra's Bauble",
  "Mox Opal",
  "Shadowspear",
  "Springleaf Drum",
  "Urza's Saga",
  "Walking Ballista"
]

@app.get("/")
async def get_scores(format: str):
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

  return JSONResponse(content=find_nearest_archetypes(bigrams, cardnames))
