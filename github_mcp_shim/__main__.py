import asyncio
import json
import logging
import os
import sys
import time

import httpx
import jwt

log = logging.getLogger("github-mcp-shim")

# Load configuration from environment
CLIENT_ID = os.getenv("GH_CLIENT_ID")
INSTALLATION_ID = os.getenv("GH_INSTALLATION_ID")
PRIVATE_KEY_PATH = os.getenv("GH_PRIVATE_KEY_PATH")
REMOTE_MCP_URL = os.getenv("GH_REMOTE_MCP_URL", "https://api.githubcopilot.com/mcp")


class GitHubAppAuth:
    def __init__(self):
        self.token = None
        self.expiry = 0
        if not PRIVATE_KEY_PATH or not os.path.exists(PRIVATE_KEY_PATH):
            raise ValueError(f"Private key not found at: {PRIVATE_KEY_PATH}")
        with open(PRIVATE_KEY_PATH, "r") as f:
            self.private_key = f.read()

    async def get_token(self):
        # Refresh if token is missing or expiring in less than 5 minutes
        if self.token and (time.time() < self.expiry - 300):
            return self.token

        # 1. Generate JWT (Valid for 10 mins)
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 600, "iss": CLIENT_ID}
        encoded_jwt = jwt.encode(payload, self.private_key, algorithm="RS256")
        log.debug("generated JWT for client_id=%s", CLIENT_ID)

        # 2. Exchange JWT for Installation Access Token
        url = f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {encoded_jwt}",
                    "Accept": "application/vnd.github+json",
                },
            )
            log.debug(
                "token exchange: status=%d body=%s", resp.status_code, resp.text[:200]
            )
            resp.raise_for_status()
            data = resp.json()
            self.token = data["token"]
            self.expiry = time.time() + 3600
            log.info("obtained installation access token, expires in 1h")
            return self.token


class MCPSession:
    def __init__(self):
        self.session_id = None

    def build_headers(self, token):
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        return headers

    def update_from_response(self, response):
        session_id = response.headers.get("mcp-session-id")
        if session_id and session_id != self.session_id:
            self.session_id = session_id
            log.info("using MCP session_id=%s", session_id)


def parse_sse_messages(text):
    """Parse SSE text into a list of data strings."""
    messages = []
    data_lines = []
    for line in text.splitlines():
        if line.startswith("data: "):
            data_lines.append(line[6:])
        elif line == "" and data_lines:
            messages.append("\n".join(data_lines))
            data_lines = []
    # Flush any remaining data
    if data_lines:
        messages.append("\n".join(data_lines))
    return messages


async def main():
    auth = GitHubAppAuth()
    mcp_session = MCPSession()
    log.info(
        "started: client_id=%s installation_id=%s mcp_url=%s",
        CLIENT_ID,
        INSTALLATION_ID,
        REMOTE_MCP_URL,
    )

    # Process line-delimited JSON-RPC from stdin
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break

        try:
            request_json = json.loads(line)
            log.debug("request: %s", json.dumps(request_json)[:200])
            token = await auth.get_token()

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    REMOTE_MCP_URL,
                    json=request_json,
                    headers=mcp_session.build_headers(token),
                    timeout=30.0,
                )

                content_type = response.headers.get("content-type", "")
                mcp_session.update_from_response(response)
                log.debug(
                    "response: status=%d content-type=%s",
                    response.status_code,
                    content_type,
                )

                if response.status_code >= 400:
                    error_msg = {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": f"MCP upstream error {response.status_code}: {response.text}",
                        },
                        "id": request_json.get("id"),
                    }
                    sys.stdout.write(json.dumps(error_msg) + "\n")
                elif "text/event-stream" in content_type:
                    for data in parse_sse_messages(response.text):
                        log.debug("SSE data: %s", data[:200])
                        sys.stdout.write(data + "\n")
                else:
                    if response.content:
                        sys.stdout.write(json.dumps(response.json()) + "\n")
                    elif request_json.get("id") is not None:
                        error_msg = {
                            "jsonrpc": "2.0",
                            "error": {
                                "code": -32603,
                                "message": f"MCP upstream returned empty body for request id {request_json['id']}",
                            },
                            "id": request_json["id"],
                        }
                        sys.stdout.write(json.dumps(error_msg) + "\n")
                sys.stdout.flush()

        except Exception as e:
            log.error("%s: %s", type(e).__name__, e)
            if request_json.get("id") is not None:
                error_msg = {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": str(e)},
                    "id": request_json["id"],
                }
                sys.stdout.write(json.dumps(error_msg) + "\n")
                sys.stdout.flush()


def main_entry():
    """Sync entry point for the console script"""
    logging.basicConfig(
        stream=sys.stderr,
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
