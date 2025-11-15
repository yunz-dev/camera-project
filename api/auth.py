import os
from fastapi import Header, HTTPException

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")


async def require_api_key(x_api_key: str = Header(None)):
    if ADMIN_API_KEY is None:
        raise HTTPException(
            status_code=500, detail="Server missing ADMIN_API_KEY env variable"
        )

    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
