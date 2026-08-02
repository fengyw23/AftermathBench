from __future__ import annotations

import os
from http.server import ThreadingHTTPServer

from .remittance import DeliveryStore, make_handler


def main() -> None:
    database = os.environ.get(
        "AFTERMATH_WEBHOOK_SINK_DB",
        "/data/webhook-sink.sqlite3",
    )
    host = os.environ.get("AFTERMATH_WEBHOOK_SINK_HOST", "0.0.0.0")
    port = int(os.environ.get("AFTERMATH_WEBHOOK_SINK_PORT", "8080"))
    server = ThreadingHTTPServer(
        (host, port),
        make_handler(DeliveryStore(database)),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
