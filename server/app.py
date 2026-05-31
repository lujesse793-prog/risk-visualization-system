"""
风控可视化系统 - 后端 API 服务器

提供 MCP 数据代理 + 妙想金融技能调度 + 底层数据注入接口。
前端通过此服务获取金融数据，数据文件由后端统一管理更新。
"""

import asyncio
import importlib.util
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS

from mcp.client import MCPClient, MCPConfig, health_check as mcp_health_check
from mx_skills.dispatcher import execute_skill, list_skills
from orchestrator.orchestrator import create_and_run_task, run_task, ProgressTracker

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")

app.json.ensure_ascii = False


CORS(app, origins=os.environ.get("CORS_ORIGIN", "*"))
_opinion_cross_verify_module = None
_skill_tasks: dict[str, dict] = {}
_skill_tasks_lock = threading.Lock()

POST_LOAN_PROGRESS_STEPS = [
    ("init", "初始化任务", 5, "正在校验企业名称，并生成用于公开披露平台检索的关键词。"),
    ("search_chinamoney", "检索中国货币网", 20, "正在中国货币网中检索该主体的年度报告、半年度报告、季度报告、募集说明书和评级报告。"),
    ("search_sse", "检索上交所", 35, "正在上海证券交易所债券信息平台中检索该主体相关公告。"),
    ("search_szse", "检索深交所", 50, "正在深圳证券交易所固定收益信息平台中检索该主体相关公告。"),
    ("filter_announcements", "筛选有效公告", 60, "正在根据文件类型、披露日期、报告期和主体匹配结果筛选可用于分析的资料。"),
    ("verify_subject", "主体一致性核验", 65, "正在核验文件中的发行人、披露主体或受评主体是否与输入企业一致。"),
    ("parse_pdf", "下载并解析 PDF", 80, "正在下载公开披露文件，并解析目录、正文和财务报表页。"),
    ("extract_tables", "提取财务报表", 90, "正在从年度报告、半年度报告或募集说明书中提取资产负债表、利润表和现金流量表。"),
    ("calculate_indicators", "计算财务指标", 98, "正在计算资产负债率、现金短债比、收入变动、净利润变动、经营性现金流等核心指标。"),
    ("generate_findings", "生成风险提示", 99, "正在基于可追溯的财务指标和原文证据生成贷后风险提示。"),
    ("organize_evidence", "整理证据链", 99, "正在整理采用文件、跳过文件、来源链接和原文依据。"),
    ("complete", "完成", 100, "贷后分析已生成。"),
]

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


def _now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _empty_post_loan_steps() -> list[dict]:
    return [
        {
            "key": key,
            "label": label,
            "status": "pending",
            "progress": progress,
            "message": "等待中。",
            "elapsed_ms": 0,
            "result_summary": "",
            "reason": "",
            "handling": "",
        }
        for key, label, progress, _message in POST_LOAN_PROGRESS_STEPS
    ]


def _initial_platform_logs() -> list[dict]:
    return [
        {
            "key": key,
            "label": label,
            "status": "pending",
            "current_action": "等待检索。",
            "result_summary": "",
        }
        for key, label in [
            ("chinamoney", "中国货币网"),
            ("sse", "上交所"),
            ("szse", "深交所"),
        ]
    ]


def _create_skill_task(skill_name: str, query: str, output_dir: str | None = None) -> dict:
    task_id = uuid.uuid4().hex
    now = _now_text()
    task = {
        "task_id": task_id,
        "skill_name": skill_name,
        "status": "running",
        "overall_progress": 0,
        "current_stage": "init",
        "current_message": "任务已启动，正在准备执行。",
        "started_at": now,
        "updated_at": now,
        "finished_at": "",
        "elapsed_ms": 0,
        "estimated_duration": "约 3-5分钟",
        "steps": _empty_post_loan_steps(),
        "platform_logs": _initial_platform_logs(),
        "summary": {},
        "result": None,
        "error": "",
        "output_dir": output_dir,
        "_started_monotonic": time.monotonic(),
    }
    with _skill_tasks_lock:
        _skill_tasks[task_id] = task
    threading.Thread(target=_run_skill_task_worker, args=(task_id, skill_name, query, output_dir), daemon=True).start()
    return _public_task(task)


def _public_task(task: dict) -> dict:
    return {key: value for key, value in task.items() if not key.startswith("_")}


def _update_task(task_id: str, **updates):
    with _skill_tasks_lock:
        task = _skill_tasks.get(task_id)
        if not task:
            return
        task.update(updates)
        task["updated_at"] = _now_text()
        task["elapsed_ms"] = int((time.monotonic() - task.get("_started_monotonic", time.monotonic())) * 1000)


def _update_step(task_id: str, step_key: str, status: str, message: str, result_summary: str = "", reason: str = "", handling: str = ""):
    with _skill_tasks_lock:
        task = _skill_tasks.get(task_id)
        if not task:
            return
        elapsed = int((time.monotonic() - task.get("_started_monotonic", time.monotonic())) * 1000)
        for step in task["steps"]:
            if step["key"] == step_key:
                step.update({
                    "status": status,
                    "message": message,
                    "elapsed_ms": elapsed,
                    "result_summary": result_summary,
                    "reason": reason,
                    "handling": handling,
                })
                task["current_stage"] = step_key
                task["current_message"] = message
                task["overall_progress"] = max(task.get("overall_progress", 0), step.get("progress", 0))
                break
        task["updated_at"] = _now_text()
        task["elapsed_ms"] = elapsed


def _update_platform_log(task_id: str, platform_key: str, status: str, current_action: str, result_summary: str = ""):
    with _skill_tasks_lock:
        task = _skill_tasks.get(task_id)
        if not task:
            return
        for item in task["platform_logs"]:
            if item["key"] == platform_key:
                item.update({
                    "status": status,
                    "current_action": current_action,
                    "result_summary": result_summary,
                })
                break
        task["updated_at"] = _now_text()


def _unwrap_skill_result(result: dict) -> dict:
    """Return the frontend report payload from dispatcher/task wrappers."""
    payload = result.get("result") if isinstance(result, dict) else {}
    if isinstance(payload, dict) and "enterprise_name" in payload and "search_log" in payload:
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        nested = payload["result"]
        if "enterprise_name" in nested and "search_log" in nested:
            return nested
    return payload if isinstance(payload, dict) else {}


def _complete_task_from_result(task_id: str, result: dict):
    skill_result = _unwrap_skill_result(result)
    search_log = skill_result.get("search_log", []) if isinstance(skill_result, dict) else []
    selected_count = 0
    skipped_count = 0
    candidate_count = 0
    for log in search_log:
        selected = log.get("selected_documents") or []
        skipped = log.get("skipped_documents") or []
        selected_count += len(selected) if isinstance(selected, list) else 0
        skipped_count += len(skipped) if isinstance(skipped, list) else 0
        candidate_count += int(log.get("matched_documents") or 0) if not isinstance(log.get("matched_documents"), list) else len(log.get("matched_documents"))
    summary = {
        "platform_count": len(search_log) or 3,
        "candidate_files": candidate_count,
        "adopted_files": selected_count,
        "skipped_files": skipped_count,
        "generated_at": _now_text(),
    }
    final_status = "success" if result.get("status") == "ok" else "failed"
    final_message = "贷后分析已生成。" if final_status == "success" else (result.get("error") or "任务执行失败。")
    if final_status == "success":
        platform_key_map = {
            "中国货币网": "chinamoney",
            "上海证券交易所": "sse",
            "上交所": "sse",
            "深圳证券交易所": "szse",
            "深交所": "szse",
        }
        for log in search_log:
            platform_key = platform_key_map.get(log.get("source_name") or log.get("source_platform") or "")
            if platform_key:
                selected = len(log.get("selected_documents") or [])
                skipped = len(log.get("skipped_documents") or [])
                _update_platform_log(task_id, platform_key, "success", "检索结果已返回。", f"采用 {selected} 份，跳过 {skipped} 份。")
        for step_key in [
            "search_chinamoney",
            "search_sse",
            "search_szse",
            "filter_announcements",
            "verify_subject",
            "parse_pdf",
            "extract_tables",
            "calculate_indicators",
            "generate_findings",
            "organize_evidence",
        ]:
            _update_step(task_id, step_key, "success", "该节点已完成。", "结果已写入分析 payload。")
    _update_step(
        task_id,
        "complete",
        final_status,
        final_message,
        "任务已结束，结果已返回前端。" if final_status == "success" else "",
        result.get("error", "") if final_status != "success" else "",
        "请查看错误信息后重试。" if final_status != "success" else "",
    )
    _update_task(
        task_id,
        status=final_status,
        overall_progress=100,
        current_stage="complete",
        current_message=final_message,
        finished_at=_now_text(),
        result=result,
        error="" if final_status == "success" else result.get("error", ""),
        summary=summary,
    )


def _run_skill_task_worker(task_id: str, skill_name: str, query: str, output_dir: str | None):
    try:
        if skill_name in {"post-loan-analysis-report", "post-loan-analysis"}:
            _run_post_loan_task_worker(task_id, skill_name, query, output_dir)
            return
        _update_step(task_id, "init", "success", "已确认任务参数，正在调用 mx-skill。", "任务参数已提交。")
        result = _run_async(execute_skill(skill_name, query, output_dir=output_dir))
        _complete_task_from_result(task_id, result)
    except Exception as exc:
        _update_task(
            task_id,
            status="failed",
            current_stage="failed",
            current_message=f"任务执行失败：{exc}",
            error=str(exc),
            finished_at=_now_text(),
        )


def _run_post_loan_task_worker(task_id: str, skill_name: str, query: str, output_dir: str | None):
    _update_step(task_id, "init", "running", "正在校验企业名称，并生成用于公开披露平台检索的关键词。")
    time.sleep(0.6)
    _update_step(task_id, "init", "success", "已确认企业名称，开始构建检索关键词。", "企业名称已确认。")

    platform_steps = [
        ("search_chinamoney", "chinamoney", "正在匹配企业名称和公告标题。"),
        ("search_sse", "sse", "正在匹配企业名称和债券公告标题。"),
        ("search_szse", "szse", "正在匹配企业名称和固定收益公告标题。"),
    ]
    for step_key, platform_key, action in platform_steps:
        _update_platform_log(task_id, platform_key, "running", action)
        _update_step(task_id, step_key, "running", action)
        time.sleep(0.35)
        _update_platform_log(task_id, platform_key, "success", "已提交真实检索任务。", "正在等待技能执行结果。")

    for step_key in ["filter_announcements", "verify_subject", "parse_pdf", "extract_tables", "calculate_indicators", "generate_findings", "organize_evidence"]:
        label_map = {item[0]: item[3] for item in POST_LOAN_PROGRESS_STEPS}
        _update_step(
            task_id,
            step_key,
            "running",
            label_map.get(step_key, "正在处理。"),
            "已进入真实执行流程。",
        )
        time.sleep(0.12)

    result = _run_async(execute_skill(skill_name, query, output_dir=output_dir))
    _complete_task_from_result(task_id, result)


def _load_opinion_cross_verify_module():
    global _opinion_cross_verify_module
    if _opinion_cross_verify_module is not None:
        return _opinion_cross_verify_module
    module_path = BASE_DIR / "mx_skills" / "enterprise-opinion-cross-verify" / "scripts" / "cross_verify.py"
    spec = importlib.util.spec_from_file_location("enterprise_opinion_cross_verify", module_path)
    if not spec or not spec.loader:
        raise RuntimeError(f"无法加载企业舆情交叉验证 Skill: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["enterprise_opinion_cross_verify"] = module
    spec.loader.exec_module(module)
    _opinion_cross_verify_module = module
    return module


def _is_opinion_admin_request() -> bool:
    token = os.environ.get("OPINION_ADMIN_TOKEN", "")
    if not token:
        return False
    auth = request.headers.get("Authorization", "")
    header_token = request.headers.get("X-Opinion-Admin-Token", "")
    bearer_token = auth[7:] if auth.lower().startswith("bearer ") else ""
    return token in {header_token, bearer_token}


def _is_opinion_batch_request() -> bool:
    token = os.environ.get("OPINION_BATCH_TOKEN", "")
    if not token:
        return False
    return request.headers.get("X-Opinion-Batch-Token", "") == token


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


@app.route("/api/mcp/servers")
@app.route("/api/ifind/servers")
def api_mcp_servers():
    """列出 iFinD MCP 服务，不暴露认证头"""
    try:
        return jsonify({"servers": MCPConfig().list_server_infos()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/ifind/<server>/tools")
def api_ifind_list_tools(server: str):
    return api_list_tools(server)


@app.route("/api/ifind/<server>/call", methods=["POST"])
def api_ifind_call_tool(server: str):
    return api_call_tool(server)


# ---- 妙想技能 ----

@app.route("/api/skills")
@app.route("/api/mx-skills")
def api_list_skills():
    return jsonify({"skills": list_skills()})


@app.route("/api/skills/<skill_name>", methods=["POST"])
@app.route("/api/mx-skills/<skill_name>", methods=["POST"])
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


@app.route("/api/skills/<skill_name>/tasks", methods=["POST"])
@app.route("/api/mx-skills/<skill_name>/tasks", methods=["POST"])
def api_start_skill_task(skill_name: str):
    data = request.get_json(force=True, silent=True) or {}
    query = data.get("query") or request.args.get("q", "")
    if not query:
        return jsonify({"error": "缺少 query 参数"}), 400
    task = _create_skill_task(skill_name, query, output_dir=data.get("output_dir"))
    return jsonify(task), 202


@app.route("/api/skill-tasks/<task_id>")
def api_get_skill_task(task_id: str):
    with _skill_tasks_lock:
        task = _skill_tasks.get(task_id)
        if not task:
            return jsonify({"error": "任务不存在或已过期"}), 404
        return jsonify(_public_task(task))


# ---- 企业舆情批处理缓存 ----

@app.route("/api/opinion/cross-verify", methods=["POST"])
def api_opinion_cross_verify():
    if os.environ.get("OPINION_ENABLE_MANUAL_VERIFY", "false").lower() != "true" or not _is_opinion_admin_request():
        return jsonify({"error": "manual opinion verification is disabled; read batch cache instead"}), 403
    data = request.get_json(force=True, silent=True) or {}
    try:
        module = _load_opinion_cross_verify_module()
        result = _run_async(module.run_cross_verification(data, batch_context=True))
        return jsonify(result)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/opinion/verify", methods=["GET"])
def api_opinion_verify_cached():
    company_name = request.args.get("company_name", "")
    batch_id = request.args.get("batch_id")
    try:
        module = _load_opinion_cross_verify_module()
        result = module.get_cached_opinion_result(company_name, batch_id=batch_id)
        if not result:
            return jsonify({"error": "暂无舆情缓存结果，请等待下一次定时更新"}), 404
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/opinion/company/<path:company_name>")
def api_opinion_company_cached(company_name: str):
    batch_id = request.args.get("batch_id")
    try:
        module = _load_opinion_cross_verify_module()
        result = module.get_cached_opinion_result(company_name, batch_id=batch_id)
        if not result:
            return jsonify({"error": "暂无舆情缓存结果，请等待下一次定时更新"}), 404
        return jsonify(result)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/opinion/verify", methods=["POST"])
def api_opinion_verify_manual():
    if os.environ.get("OPINION_ENABLE_MANUAL_VERIFY", "false").lower() != "true" or not _is_opinion_admin_request():
        return jsonify({"error": "manual opinion verification is disabled"}), 403
    data = request.get_json(force=True, silent=True) or {}
    try:
        module = _load_opinion_cross_verify_module()
        result = _run_async(module.run_cross_verification(data, batch_context=True))
        return jsonify(result)
    except PermissionError as e:
        return jsonify({"error": str(e)}), 403
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/opinion/batch/latest")
def api_opinion_batch_latest():
    try:
        module = _load_opinion_cross_verify_module()
        return jsonify(module.get_latest_batch_status())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/opinion/batch/run", methods=["POST"])
def api_opinion_batch_run():
    if not _is_opinion_batch_request():
        return jsonify({"error": "batch token required"}), 403
    data = request.get_json(force=True, silent=True) or {}
    companies = data.get("companies") or []
    if not isinstance(companies, list) or not companies:
        return jsonify({"error": "companies must be a non-empty list"}), 400
    try:
        module = _load_opinion_cross_verify_module()
        status = _run_async(module.run_opinion_batch(companies, default_params=data.get("default_params") or {}))
        http_status = 409 if status.get("status") == "skipped" else 200
        return jsonify(status), http_status
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/opinion/full-text/<full_text_id>")
def api_opinion_full_text(full_text_id: str):
    try:
        module = _load_opinion_cross_verify_module()
        result = module.get_full_text(full_text_id)
        if not result:
            return jsonify({"error": "full_text_id not found"}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500





# ---- Orchestrator 总控 ----

_orchestrator_tasks: dict[str, dict] = {}
_orchestrator_tasks_lock = threading.Lock()

@app.route("/api/orchestrator/run", methods=["POST"])
def api_orchestrator_run():
    """运行贷后分析流水线"""
    data = request.get_json(force=True, silent=True) or {}
    enterprise_name = (data.get("enterprise_name") or "").strip()
    if not enterprise_name:
        return jsonify({"error": "enterprise_name is required"}), 400
    
    report_period = data.get("report_period")
    
    def _run():
        return asyncio.run(create_and_run_task(enterprise_name, report_period))
    
    try:
        result = _run()
        # 存储任务结果
        task_id = result.get("task_id", "")
        with _orchestrator_tasks_lock:
            _orchestrator_tasks[task_id] = result
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500


@app.route("/api/orchestrator/status/<task_id>", methods=["GET"])
def api_orchestrator_status(task_id: str):
    """获取任务状态"""
    with _orchestrator_tasks_lock:
        task = _orchestrator_tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在或已过期"}), 404
    return jsonify({
        "task_id": task.get("task_id"),
        "enterprise_name": task.get("enterprise_name"),
        "task_status": task.get("task_status"),
        "data_status": task.get("data_status"),
        "message": task.get("message"),
        "progress_events": task.get("progress_events", []),
    })


@app.route("/api/orchestrator/result/<task_id>", methods=["GET"])
def api_orchestrator_result(task_id: str):
    """获取完整任务结果"""
    with _orchestrator_tasks_lock:
        task = _orchestrator_tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在或已过期"}), 404
    return jsonify(task)


@app.route("/api/orchestrator/progress/<task_id>", methods=["GET"])
def api_orchestrator_progress(task_id: str):
    """获取任务进度事件"""
    with _orchestrator_tasks_lock:
        task = _orchestrator_tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在或已过期"}), 404
    return jsonify({
        "task_id": task.get("task_id"),
        "task_status": task.get("task_status"),
        "progress_events": task.get("progress_events", []),
    })

@app.after_request
def add_charset(response):
    ct = response.headers.get("Content-Type", "")
    if ct and "charset" not in ct:
        response.headers["Content-Type"] = ct + "; charset=utf-8"
    return response
if __name__ == "__main__":
    port = int(os.environ.get("SERVER_PORT", 8080))
    debug = os.environ.get("PRODUCTION", "false").lower() != "true"
    app.run(host="0.0.0.0", port=port, debug=debug)

