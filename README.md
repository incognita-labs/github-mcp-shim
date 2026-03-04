# GitHub MCP App Shim

A lightweight **stdio-to-http** relay that enables the [GitHub MCP Server](https://github.com) to authenticate using a **GitHub App** instead of a Personal Access Token (PAT).

## Why use this?
The official GitHub MCP server typically requires a static PAT. This shim allows your AI agent to use a **GitHub App's** fine-grained permissions and short-lived tokens, which is more secure for organizational use and avoids the 1-year expiration limit of standard tokens.

## Features
- **Auto-Refresh**: Automatically exchanges your App's Private Key for a fresh Installation Access Token every 50 minutes.
- **Stdio Bridge**: Acts as a local `stdio` server for AI clients (like Claude Desktop) while communicating with GitHub's remote MCP endpoint over `https`.
- **Environment Driven**: No secrets are hardcoded; all identifiers are passed via environment variables.

## Prerequisites
- **Python 3.9+**
- A **GitHub App** registered in your organization with the necessary permissions (e.g., `Contents: Read/Write`, `Metadata: Read-only`).
- The App must be **installed** on the target organization or repositories.

## Installation

1. **Clone or copy** the `github_shim.py` and `pyproject.toml` into a folder.
2. **Install the dependencies**:
   ```bash
   pip install .

## Finding Your Credentials


| Identifier | Where to find it |
| :--- | :--- |
| **Client ID** | Found on the **General** settings page of your GitHub App (e.g., `Iv23liABC123`). |
| **Private Key** | Generate and download the `.pem` file from the **General** settings page. |
| **Installation ID** | Navigate to your Org Settings > **Installed GitHub Apps** > Click **Configure** next to your app. The ID is the **numeric string at the end of the URL** (e.g., `.../installations/12345678`). |

## Configuration

### Claude Desktop
Add the following to your `claude_desktop_config.json` (found at `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "github-app-agent": {
      "command": "github-mcp-shim",
      "env": {
        "GH_CLIENT_ID": "YOUR_CLIENT_ID",
        "GH_INSTALLATION_ID": "YOUR_INSTALL_ID",
        "GH_PRIVATE_KEY_PATH": "/absolute/path/to/your-app.private-key.pem",
        "GH_REMOTE_MCP_URL": "https://api.githubcopilot.com/mcp"  // optional
      }
    }
  }
}
```

### Security Note
Keep your .pem private key file secure. Anyone with access to this file and your Client ID can impersonate your agent and access the repositories authorized during the app installation.

