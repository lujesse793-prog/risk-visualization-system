"""
风控可视化系统 - 后端 API 服务器

提供 MCP 数据代理 + 妙想金融技能调度 + 底层数据注入接口。
前端通过此服务获取金融数据，数据文件由后端统一管理更新。
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS

from mcp.client import MCPClient, health_check as mcp_health_check
from mx_skills.dispatcher import execute_skill, list_skills

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

CORS(app, origins=os.environ.get("CORS_ORIGIN", "*"))

# ---- 数据缓存（启动加载，支持热重载）----

_data_cache: dict[str, str] = {}
DATA_FILES = {
    "projects": BASE_DIR / "data" / "projects.js",
    "ifind_risk_results": BASE_DIR / "data" / "ifind_risk_results.js",
    "china_map_paths": BASE_DIR / "data" / "china_map_paths.js",
}


def load_data_files():
    """加载全部数据文件到内存缓存"""
    global _data_cache
    for name, path in DATA_FILES.items():
        if path.exists():
            _data_cache[name] = path.read_text(encoding="utf-8")
    print(f"[数据] 已加载 {len(_data_cache)} 个数据文件")


load_data_files()


def get_injection_block() -> str:
    """生成注入到 HTML 的数据脚本块"""
    blocks = []
    for name in ["projects", "ifind_risk_results", "china_map_paths"]:
        if name in _data_cache:
            blocks.append(f"<script>\n{_data_cache[name]}\n</script>")
    return "\n    ".join(blocks)


# ---- 辅助 ----

def _run_async(coro):
    return asyncio.run(coro)


# ---- 静态文件 ----

@app.route("/")
def index():
    """提供前端页面，注入最新数据"""
    html_path = BASE_DIR / "index.html"
    html = html_path.read_text(encoding="utf-8")
    injection = get_injection_block()
    html = html.replace("<!-- SERVER_DATA_INJECTION -->", injection)
    return Response(html, mimetype="text/html")


@app.route("/index_standalone_backup.html")
def standalone_backup():
    """独立备份（内嵌全部数据，无需服务器）"""
    return send_from_directory(str(BASE_DIR), "index_standalone_backup.html")


# ---- 数据 API ----

@app.route("/api/data/projects")
def api_data_projects():
    """项目列表 JSON"""
    content = _data_cache.get("projects", "")
    m = re.search(r"window\.PROJECT_ROSTER\s*=\s*(\[[\s\S]*?\]);", content)
    if m:
        return Response(m.group(1), mimetype="application/json")
    return jsonify({"error": "数据解析失败"}), 500


@app.route("/api/data/alerts")
def api_data_alerts():
    """风险预警列表 JSON"""
    content = _data_cache.get("ifind_risk_results", "")
    m = re.search(r"window\.IFIND_RISK_ALERTS\s*=\s*(\[[\s\S]*?\]);", content)
    if m:
        return Response(m.group(1), mimetype="application/json")
    return jsonify({"error": "数据解析失败"}), 500


@app.route("/api/data/meta")
def api_data_meta():
    """运行元信息 JSON"""
    content = _data_cache.get("ifind_risk_results", "")
    m = re.search(r"window\.IFIND_RISK_RUN_META\s*=\s*(\{[\s\S]*?\});", content)
    if m:
        return Response(m.group(1), mimetype="application/json")
    return jsonify({"error": "数据解析失败"}), 500


@app.route("/api/data/regions")
def api_data_regions():
    """中国地图数据 JSON"""
    content = _data_cache.get("china_map_paths", "")
    maps_match = re.search(r"window\.REGION_MAPS\s*=\s*(\{[\s\S]*?\});", content)
    parents_match = re.search(r"window\.REGION_PARENTS\s*=\s*(\{[\s\S]*?\});", content)
    result = {}
    if maps_match:
        result["maps"] = json.loads(maps_match.group(1))
    if parents_match:
        result["parents"] = json.loads(parents_match.group(1))
    return jsonify(result)


@app.route("/api/data/reload", methods=["POST"])
def api_data_reload():
    """热重载数据文件（更新数据后调用）"""
    load_data_files()
    return jsonify({"status": "ok", "files": list(_data_cache.keys())})


# ---- 健康检查 ----

@app.route("/api/health")
def api_health():
    """综合健康检查"""
    result = {
        "status": "ok",
        "data": {"files": list(_data_cache.keys()), "loaded": len(_data_cache) > 0},
        "mcp": {},
        "skills": {"count": len(list_skills()), "names": [s["name"] for s in list_skills()]},
    }
    try:
        result["mcp"] = mcp_health_check()
    except Exception as e:
        result["mcp"] = {"error": str(e)}
    return jsonify(result)


# ---- MCP 代理 ----

@app.route("/api/news/search")
def api_search_news():
    query = request.args.get("q", "")
    if not query:
        return jsonify({"error": "缺少查询参数 q"}), 400
    try:
        client = MCPClient("news")
        result = client.call_tool("search_news", {"query": query})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stock/<code>")
def api_stock_info(code: str):
    try:
        client = MCPClient("stock")
        result = client.call_tool("get_stock_info", {"code": code})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/fund/<code>")
def api_fund_info(code: str):
    try:
        client = MCPClient("fund")
        result = client.call_tool("get_fund_info", {"code": code})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/edb/<indicator>")
def api_edb_data(indicator: str):
    try:
        client = MCPClient("edb")
        result = client.call_tool("get_edb_data", {"indicator": indicator})
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mcp/<server>/tools")
def api_list_tools(server: str):
    try:
        client = MCPClient(server)
        result = client.list_tools()
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mcp/<server>/call", methods=["POST"])
def api_call_tool(server: str):
    data = request.get_json(force=True)
    tool_name = data.get("tool")
    arguments = data.get("arguments", {})
    if not tool_name:
        return jsonify({"error": "缺少 tool 参数"}), 400
    try:
        client = MCPClient(server)
        result = client.call_tool(tool_name, arguments)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---- 妙想技能 ----

@app.route("/api/skills")
def api_list_skills():
    return jsonify({"skills": list_skills()})


@app.route("/api/skills/<skill_name>", methods=["POST"])
def api_execute_skill(skill_name: str):
    data = request.get_json(force=True, silent=True) or {}
    query = data.get("query") or request.args.get("q", "")
    if not query:
        return jsonify({"error": "缺少 query 参数"}), 400
    output_dir = data.get("output_dir")
    try:
        result = _run_async(execute_skill(skill_name, query, output_dir=output_dir))
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("SERVER_PORT", 8080))
    debug = os.environ.get("PRODUCTION", "false").lower() != "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
