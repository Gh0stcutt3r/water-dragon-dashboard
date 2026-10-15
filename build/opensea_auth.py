"""Portable OpenSea API authentication.

Tries the private credential helper first (this project's own environment),
then falls back to the OPENSEA_API_KEY environment variable (public use).

Usage:
    from opensea_auth import auth_request, read_json

    req = urllib.request.Request(url, headers={...})
    auth_request(req)                      # attaches the API key
    with urllib.request.urlopen(req) as r:
        data = read_json(r)

Get a free API key at https://docs.opensea.io/reference/api-keys
and export OPENSEA_API_KEY=<key> before running.
"""
import json
import os
import sys

HOST = "api.opensea.io"
ENV_VAR = "OPENSEA_API_KEY"

# Private helper, only present in this project's own environment.
_HAVE_PRIVATE = False
try:
    sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
    sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
    from dynamic_credentials import (  # noqa: E402
        add_surrogate_to_request as _add_surrogate,
        read_json_response as _read_json_response,
    )
    _HAVE_PRIVATE = True
except ImportError:
    pass


def auth_request(req, host=HOST):
    """Attach OpenSea auth to a urllib Request. Raises RuntimeError if no key."""
    if _HAVE_PRIVATE:
        try:
            _add_surrogate(req, "custom.opensea", allowed_hosts=[host])
            return req
        except Exception:
            pass  # fall through to env var
    key = os.environ.get(ENV_VAR)
    if not key:
        raise RuntimeError(
            f"No OpenSea API key found. Set the {ENV_VAR} environment variable "
            "(get one free at https://docs.opensea.io/reference/api-keys)."
        )
    req.add_header("X-API-Key", key)
    return req


def read_json(resp):
    """Parse a JSON HTTP response."""
    if _HAVE_PRIVATE:
        try:
            return _read_json_response(resp)
        except Exception:
            pass
    return json.loads(resp.read().decode("utf-8"))
