"""
iFinD MCP 客户端 - 通过 Streamable HTTP 连接同花顺 iFinD MCP 服务

支持的服务:
- stock:     A股数据查询
- fund:      基金数据查询
- edb:       经济数据库
- news:      资讯/公告搜索
- bond:      债券数据查询
- global:    港股/美股查询
- index:     指数数据查询
"""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent


class MCPConfig:
    """MCP 配置管理"""

    CONFIG_PATH = BASE_DIR / "mcp" / "config.json"

    def __init__(self):
        with open(self.CONFIG_PATH, "r", encoding="utf-8") as f:
            self._config = json.load(f)

    @property
    def auth_token(self) -> str:
        """从环境变量获取认证令牌"""
        return os.environ.get("IFIND_MCP_AUTH_TOKEN", "")

    def get_server(self, name: str) -> dict | None:
        """获取指定 MCP 服务器配置"""
        key = f"hexin-ifind-ds-{name}-mcp"
        return self._config.get("mcpServers", {}).get(key)

    def list_servers(self) -> list[str]:
        """列出所有可用的 MCP 服务器"""
        return list(self._config.get("mcpServers", {}).keys())  # type: ignore[arg-type]


class MCPClient:
    """iFinD MCP Streamable HTTP 客户端"""

    def __init__(self, server_name: str):
        self.config = MCPConfig()
        self.server = self.config.get_server(server_name)
        if not self.server:
            raise ValueError(f"MCP server '{server_name}' not found in config")

        self.url = self.server["url"]
        self.token = self.config.auth_token
        if not self.token:
            raise RuntimeError("IFIND_MCP_AUTH_TOKEN 环境变量未设置")

    def _make_request(self, method: str, params: dict | None = None) -> dict:
        """发送 JSON-RPC 请求到 MCP 服务器"""
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
        }
        if params:
            payload["params"] = params

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            self.url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": self.token,
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP HTTP {e.code}: {body}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"MCP 连接失败: {e.reason}") from e

    # ---- MCP 协议方法 ----

    def initialize(self) -> dict:
        """初始化 MCP 会话"""
        return self._make_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "risk-control-system", "version": "1.0.0"},
        })

    def list_tools(self) -> dict:
        """列出可用的工具"""
        return self._make_request("tools/list")

    def call_tool(self, tool_name: str, arguments: dict | None = None) -> dict:
        """调用指定的工具"""
        return self._make_request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })


# ---- 便捷函数 ----

def search_news(query: str, date_range: str = "近三个月") -> dict:
    """搜索财经资讯"""
    client = MCPClient("news")
    return client.call_tool("search_news", {"query": query, "dateRange": date_range})


def get_stock_info(code: str) -> dict:
    """查询A股股票信息"""
    client = MCPClient("stock")
    return client.call_tool("get_stock_info", {"code": code})


def get_fund_info(code: str) -> dict:
    """查询基金信息"""
    client = MCPClient("fund")
    return client.call_tool("get_fund_info", {"code": code})


def get_edb_data(indicator: str) -> dict:
    """查询宏观经济数据"""
    client = MCPClient("edb")
    return client.call_tool("get_edb_data", {"indicator": indicator})


def health_check() -> dict[str, bool]:
    """检查所有 MCP 服务可用性"""
    config = MCPConfig()
    results = {}
    for full_key in config.list_servers():
        short_name = full_key.replace("hexin-ifind-ds-", "").replace("-mcp", "")
        try:
            client = MCPClient(short_name)
            client.initialize()
            results[short_name] = True
        except Exception as e:
            results[short_name] = False
    return results


if __name__ == "__main__":
    print("iFinD MCP 服务健康检查:")
    print(json.dumps(health_check(), indent=2, ensure_ascii=False))
