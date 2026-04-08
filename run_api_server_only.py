import asyncio
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "hermes-agent"))

from gateway.config import PlatformConfig
from gateway.platforms.api_server import APIServerAdapter


async def main() -> None:
    config = PlatformConfig(enabled=True)
    config.extra = {
        "host": os.getenv("API_SERVER_HOST", "127.0.0.1"),
        "port": int(os.getenv("API_SERVER_PORT", "8642")),
        "key": os.getenv("API_SERVER_KEY", ""),
    }

    adapter = APIServerAdapter(config)
    ok = await adapter.connect()
    if not ok:
        raise SystemExit(1)

    stop_event = asyncio.Event()

    def _stop(*_args):
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _stop)

    await stop_event.wait()
    await adapter.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
