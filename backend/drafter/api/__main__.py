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
    # first start of the installed app: seed data must be on disk before modules read it
    from drafter import config
    config.ensure_seed()
    # import the app object directly (not by string): in the bundled exe a failing import then
    # shows its real traceback instead of uvicorn's generic "could not import module"
    from drafter.api.app import app
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
