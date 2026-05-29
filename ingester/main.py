#!/usr/bin/env python3
"""Flight ingester service entrypoint."""

from etl.ingestion import run_forever

if __name__ == "__main__":
    run_forever()
