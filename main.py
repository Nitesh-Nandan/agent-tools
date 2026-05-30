"""
Entry point for the Agent Tools MCP server (memory + email).

Usage:
    uv run main.py                   # stdio mode (default, for Claude Desktop etc.)
    uv run main.py --transport sse   # SSE mode (for HTTP-based clients)
"""

import argparse

from src.config import config  # config.py calls load_dotenv() on import


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agent Tools MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default=config.mcp_host,
        help="Host for SSE transport (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.mcp_port,
        help="Port for SSE transport (default: 8000)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from src.server import mcp

    if args.transport == "sse":
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
