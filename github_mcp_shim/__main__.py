import asyncio
import json
import os
import sys
import time

import jwt
import httpx


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
        with open(PRIVATE_KEY_PATH, 'r') as f:
            self.private_key = f.read()

    async def get_token(self):
        # Refresh if token is missing or expiring in less than 5 minutes
        if self.token and (time.time() < self.expiry - 300):
            return self.token

        # 1. Generate JWT (Valid for 10 mins)
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 600, "iss": CLIENT_ID}
        encoded_jwt = jwt.encode(payload, self.private_key, algorithm="RS256")

        # 2. Exchange JWT for Installation Access Token
        url = f"https://api.github.com/app/installations/{INSTALLATION_ID}/access_tokens"
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers={
                "Authorization": f"Bearer {encoded_jwt}",
                "Accept": "application/vnd.github+json"
            })
            resp.raise_for_status()
            data = resp.json()
            self.token = data["token"]
            self.expiry = time.time() + 3600
            return self.token

async def main():
    auth = GitHubAppAuth()

    # Process line-delimited JSON-RPC from stdin
    while True:
        line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
        if not line:
            break

        try:
            request_json = json.loads(line)
            token = await auth.get_token()

            async with httpx.AsyncClient() as client:
                # Forward to GitHub's Remote MCP
                response = await client.post(
                    REMOTE_MCP_URL,
                    json=request_json,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    },
                    timeout=30.0 # Increase timeout for complex agent tasks
                )

                # Write back the JSON-RPC response
                sys.stdout.write(json.dumps(response.json()) + "\n")
                sys.stdout.flush()

        except Exception as e:
            # Report internal errors as JSON-RPC errors so the client doesn't crash
            error_msg = {"jsonrpc": "2.0", "error": {"code": -32603, "message": str(e)}, "id": None}
            sys.stdout.write(json.dumps(error_msg) + "\n")
            sys.stdout.flush()


def main_entry():
    """Sync entry point for the console script"""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
