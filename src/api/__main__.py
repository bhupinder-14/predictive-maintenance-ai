"""Run the API using ``python -m src.api``."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("src.api.main:app", host="127.0.0.1", port=8000, reload=False)
