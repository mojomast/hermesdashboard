import asyncio
import os
import signal
import sys
from pathlib import Path

def _hermes_agent_path() -> Path:
    configured = os.getenv("HERMES_AGENT_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path(__file__).parent.parent / "hermes-agent").resolve()


HERMES_AGENT_PATH = _hermes_agent_path()
if str(HERMES_AGENT_PATH) not in sys.path:
    sys.path.insert(0, str(HERMES_AGENT_PATH))

try:
    from gateway.config import PlatformConfig
    from gateway.platforms.api_server import APIServerAdapter
except Exception as exc:
    raise SystemExit(
        "run_api_server_only.py requires a Hermes install that exposes "
        "gateway.config.PlatformConfig and gateway.platforms.api_server.APIServerAdapter. "
        "If your Hermes install does not provide those modules, start your Hermes API "
        "using your own runtime setup and point the dashboard at it with HERMES_API. "
        f"Original import error: {exc}"
    )


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
