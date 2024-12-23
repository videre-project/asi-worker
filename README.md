# asi-worker

Cloudflare worker for computing archetype similarity index (ASI) scores.

<a href="#overview">Overview</a> |
<a href="#project-structure">Project Structure</a> |
<a href="#asi-endpoint">`/asi` Endpoint</a> |
<a href="#setup-and-deployment">Setup and Deployment</a> |
<a href="#license">License</a>

## Overview

The [Archetype Similarity Index (ASI)](/SPECIFICATION.md) is designed to calculate the nearest archetypes to a given decklist based on the unique number of card-pairings (bigrams) they share. This project uses Cloudflare Workers to handle requests and compute the ASI.

## Project Structure

<!-- Create a file tree with comments -->
```sh
.
├── src/
│   ├── asi/ # ASI library for computing bigrams and ASI scores.
│   │   ├── __init__.py
│   │   ├── archetypes.py
│   │   ├── bigrams.py
│   │   └── postgres.py
│   ├── router.py # A zero-dependency request router.
│   └── worker.py # The main Cloudflare worker script.
├── .env-example
├── build.py # Build script for updating Cloudflare D1 bigrams.
├── pyproject.toml
└── wrangler.toml # Configuration file for Cloudflare Workers.
```

## `/asi` Endpoint

### Request

To calculate the nearest archetypes to a given decklist, send a POST request to the `/asi` endpoint with a JSON body containing an array of card names.

#### URL

```
POST https://ml.videreproject.com/asi?format=modern # or another format
```

#### Headers

```http
Content-Type: application/json
```

#### Body

The request body must be a valid JSON array containing a list of card names. The list must contain at least two cards to form bigrams.

For example:

```json
// The card names must be provided as strings and are case-sensitive.
[
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
```

### Response

The response will be a JSON object containing the nearest archetypes and their
similarity scores. These scores vary between 0 and 1, with scores below 0.5
being undecisive; only scores greater than 0.05 are included in the response.

#### Success Response

```json
{
  "meta": {
    // Indicates which database type was used. Currently, only D1 is supported.
    "database": "D1",
    // The Cloudflare worker backend used to process the request.
    "backend": "v3-prod",
    // The total SQL execution time in milliseconds.
    "exec-ms": 5.758,
    // The number of rows read/scanned by the query.
    "read_count": 2742,
  },
  // The ASI scores for each archetype.
  "data": {
    "Basking Broodscale Combo": 1,
    "Eldrazi": 0.6481133,
    "Hardened Scales": 0.32852826,
    "Breach": 0.25529937,
    "Affinity": 0.20222514,
    "The Rock": 0.14852764,
    "Grinding Station": 0.13885093,
    "Through the Breach": 0.12699843,
    "Eldrazi Ramp": 0.11773569,
    "Lantern": 0.08489789,
    "Gruul Aggro": 0.0651898,
    "Eldrazi Tron": 0.06422159,
    "Yawgmoth": 0.06139001,
    "Tron": 0.0536501
  }
}
```

### Error Response

#### Missing `format` parameter

When the `format` URL parameter is missing, the response will be:

```json
{
  "error": "Missing Parameter",
  "message": "The 'format' parameter is required."
}
```

If the `format` parameter provided is invalid, the response will be:

```json
{
  "error": "Invalid Parameter",
  "message": "The 'format' parameter '...' is not supported."
}
```

#### Invalid JSON

In cases where the request body is not a valid JSON array (e.g., the body is malformed or an object is provided instead), the response will be:

```json
{
  "error": "Invalid JSON",
  "message": "The request body must be a valid JSON array."
}
```

#### Insufficient Cards

If the request body contains fewer than two cards, the response will be:

```json
{
  "error": "Invalid JSON",
  "message": "The request body must contain at least two cards."
}
```

## Setup and Deployment

### Install Tools

1. **Install Wrangler**: Install the Wrangler CLI tool.

```bash
npm install -g @cloudflare/wrangler@^3.68.0
```

2. **Install UV CLI**: Install the UV CLI tool to manage dependencies.

```bash
npm install -g @cloudflare/uv@latest
```

### Configure and Set Up

1. **Configure Wrangler**: Update the [wrangler.toml](/wrangler.toml) file with your Cloudflare account details.

2. **Set Up Environment Variables**: Create a `.env` file in the root directory based on the provided `.env-example` file and fill in your Cloudflare credentials.

### Install Dependencies

Use the [UV CLI](https://docs.astral.sh/uv/getting-started/installation/) to install the required dependencies.

```bash
uv install
```

### Build and Deploy

1. **Build Bigrams**: Run the build script to update Cloudflare D1 with the latest bigrams for each format.

```bash
uv run build.py
```

2. **Local Development**: Test the worker locally using Wrangler.

```bash
npx wrangler dev
```

3. **Deploy**: Deploy the worker using Wrangler.

```bash
npx wrangler deploy
```

## License

This project is licensed under the Apache-2.0 License. See the [LICENSE](/LICENSE) file for more details.
