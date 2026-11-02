import os
import secrets
from typing import Annotated

from fastapi import Header, HTTPException


def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = os.environ.get("API_TOKEN", "")
    if len(expected) < 24:
        raise HTTPException(503, "Configure API_TOKEN with at least 24 characters")
    if not secrets.compare_digest(authorization or "", "Bearer " + expected):
        raise HTTPException(401, "Authentication required")
