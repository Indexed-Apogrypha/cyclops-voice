from __future__ import annotations
from .client import CyclopsClient
from .config import load_config


def _client() -> CyclopsClient:
    cfg = load_config(None)
    return CyclopsClient(base_url=f"http://{cfg.service.host}:{cfg.service.port}",
                         token=cfg.service.auth_token)


def do_speak(client: CyclopsClient, text: str, preset: str | None) -> str:
    if not client.is_up():
        return "Cyclops daemon is not running. Start it with: cyclops daemon"
    out = client.speak(text, preset=preset)
    return f"Speaking ({out.get('state')}), job {out.get('job_id')}."


def do_stop(client: CyclopsClient) -> str:
    if not client.is_up():
        return "Cyclops daemon is not running."
    return f"Stopped. State: {client.stop().get('state')}."


def do_status(client: CyclopsClient) -> str:
    if not client.is_up():
        return "Cyclops daemon is not running."
    return str(client.status())


def main() -> None:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("cyclops-voice")
    client = _client()

    @mcp.tool()
    def speak(text: str, preset: str | None = None) -> str:
        """Read the given text aloud in the Cyclops submarine voice."""
        return do_speak(client, text, preset)

    @mcp.tool()
    def stop() -> str:
        """Stop any current Cyclops speech immediately."""
        return do_stop(client)

    @mcp.tool()
    def status() -> str:
        """Report the Cyclops voice service status."""
        return do_status(client)

    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
