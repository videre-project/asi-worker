## @file
# Copyright (c) 2024, Cory Bennett. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
##
"""Cloudflare workers API router and FFI utilities."""

from js import Response, Headers
from json import dumps as json_dumps


class Router:
  """Simple router for handling request routes."""
  _routes = {}

  def __getattr__(self, method):
    def decorator(path):
      def wrapper(f):
        self._routes[(method.upper(), path)] = f
        return f
      return wrapper
    return decorator

  def match(self, method, path):
    return self._routes.get((method.upper(), path))

def JSONResponse(data: dict | list, status: int = 200) -> Response:
  headers = Headers.new({"content-type": "application/json"}.items())
  return Response.new(json_dumps(data), headers=headers, status=status)

def get_endpoint(url: str) -> str:
  """Extract the endpoint from the request url string."""
  return '/' + url.split('/', 3)[-1].split('?')[0]

def get_parameters(url: str) -> dict[str, str]:
  """Extract the query parameters from the request url string."""
  parameters: dict = {}
  try:
    query: str = url.split('?')[1]
    for param in query.split('&'):
      key = param.split('=')[0]
      value = param.split('=')[1]
      parameters[key] = value
  except IndexError:
    pass

  return parameters
