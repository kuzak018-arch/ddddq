"""Run the API: python -m drafter.api [--port 47900] [--token ...]
The Tauri shell starts this as a sidecar with a random token; for development no token is needed."""

import argparse
import os

import uvicorn


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=47900)
    ap.add_argument("--token", default=os.environ.get("DRAFTER_TOKEN"))
    args = ap.parse_args()
    if args.token:
        os.environ["DRAFTER_TOKEN"] = args.token
    uvicorn.run("drafter.api.app:app", host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
