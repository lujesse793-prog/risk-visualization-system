"""
妙想金融技能调度器 - 统一封装 14 个金融分析技能

每个技能通过自然语言问句触发，返回结构化结果（含文件路径）。
"""

import asyncio
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent

# 技能名称 → 模块路径 / 入口函数
SKILL_REGISTRY: dict[str, dict[str, Any]] = {
    "mx-finance-data": {
        "module": "mx-finance-data.scripts.get_data",
        "entry": "query_mx_finance_data_direct",
        "description": "全市场金融数据查询（A港美股、基金、债券）",
    },
    "mx-finance-search": {
        "module": "mx-finance-search.scripts.get_data",
        "entry": "query_financial_news",
        "description": "财经资讯/公告/研报搜索",
    },
    "mx-macro-data": {
        "module": "mx-macro-data.scripts.get_data",
        "entry": "query_mx_macro_data",
        "description": "全球宏观经济数据查询",
    },
    "mx-stocks-screener": {
        "module": "mx-stocks-screener.scripts.get_data",
        "entry": "query_mx_stocks_screener",
        "description": "智能选股筛选",
    },
    "stock-diagnosis": {
        "module": "stock-diagnosis.scripts.get_data",
        "entry": "_main",
        "kwargs": {"query_arg": "query"},
        "description": "A股单票综合诊断",
    },
    "fund-diagnosis": {
        "module": "fund-diagnosis.scripts.get_data",
        "entry": "_main",
        "kwargs": {"query_arg": "query"},
        "description": "公募基金综合诊断",
    },
    "industry-research-report": {
        "module": "industry-research-report.scripts.get_data",
        "entry": "_main",
        "kwargs": {"query_arg": "query"},
        "description": "行业深度研究报告",
    },
    "industry-stock-tracker": {
        "module": "industry-stock-tracker.scripts.generate_industry_stock_tracker_report",
        "entry": "_main",
        "description": "行业/个股跟踪报告",
    },
    "initiation-of-coverage": {
        "module": "initiation-of-coverage-or-deep-dive.scripts.generate_deep_research_report",
        "entry": "generate_report",
        "description": "首次覆盖/深度研究报告",
    },
    "stock-earnings-review": {
        "module": "stock-earnings-review.scripts.call_review_api",
        "entry": "_main",
        "description": "财报/业绩点评",
    },
    "mx-financial-assistant": {
        "module": "mx-financial-assistant.scripts.generate_answer",
        "entry": "_main",
        "description": "智能金融问答",
    },
    "topic-research-report": {
        "module": "topic-research-report.scripts.get_data",
        "entry": "generate_topic_research_report",
        "description": "专题研究报告",
    },
    "stock-market-hotspot": {
        "module": "stock-market-hotspot-discovery.scripts.get_data",
        "entry": "_main",
        "kwargs": {"query_arg": "query"},
        "description": "市场热点发现",
    },
    "comparable-company-analysis": {
        "module": "comparable-company-analysis.scripts.get_data",
        "entry": "fetch_comparable_company_data",
        "description": "可比公司分析",
    },
    "mx-personal-kb-search": {
        "module": "mx-personal-kb-search.scripts.get_data",
        "entry": "_main",
        "kwargs": {"query_arg": "query"},
        "description": "私域知识库检索",
    },
}


def _load_skill_module(module_path: str):
    """动态加载技能模块"""
    parts = module_path.split(".")
    file_path = BASE_DIR / Path(*parts).with_suffix(".py")
    
    if not file_path.exists():
        raise FileNotFoundError(f"技能模块不存在: {file_path}")
    
    module_name = f"mx_skills.{module_path}"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


async def execute_skill(
    skill_name: str,
    query: str,
    output_dir: str | None = None,
    api_base: str | None = None,
    **extra_kwargs,
) -> dict[str, Any]:
    """执行指定技能

    Args:
        skill_name: 技能名称 (如 mx-finance-data)
        query: 自然语言查询问句
        output_dir: 输出目录（默认 mx_skills/output/）
        api_base: API 地址（可选）

    Returns:
        包含 status, result, files, error 的字典
    """
    if skill_name not in SKILL_REGISTRY:
        return {
            "status": "error",
            "error": f"未知技能: {skill_name}。可用: {list(SKILL_REGISTRY.keys())}",
        }

    spec = SKILL_REGISTRY[skill_name]
    
    try:
        module = _load_skill_module(spec["module"])
        entry_func = getattr(module, spec["entry"], None)
        if not entry_func:
            return {"status": "error", "error": f"入口函数 {spec['entry']} 不存在"}

        output_path = Path(output_dir) if output_dir else BASE_DIR / "output" / skill_name
        output_path.mkdir(parents=True, exist_ok=True)

        # 构建调用参数 - 根据技能类型适配
        kwargs = {"output_dir": output_path}
        if api_base:
            kwargs["api_base"] = api_base

        # 处理不同的参数模式
        entry_name = spec["entry"]
        if entry_name == "_main":
            # run_cli 风格的技能 - 需要设置 sys.argv 模拟
            old_argv = sys.argv
            sys.argv = ["skill_runner", "--query", query]
            try:
                result = await entry_func()
            finally:
                sys.argv = old_argv
        elif entry_name == "query_mx_finance_data_direct":
            result = await entry_func(query=query, **kwargs)
        elif entry_name == "fetch_comparable_company_data":
            result = await entry_func(query, **kwargs)
        elif entry_name == "generate_report":
            result = await entry_func(query, output_path, **{k: v for k, v in kwargs.items() if k != "output_dir"})
        else:
            result = await entry_func(query=query, **kwargs)

        return {"status": "ok", "result": _serialize_result(result), "files": _list_output_files(output_path)}

    except Exception as e:
        return {"status": "error", "error": str(e), "skill": skill_name}


def _serialize_result(result: Any) -> dict:
    """将技能返回结果序列化为 JSON 兼容格式"""
    if isinstance(result, dict):
        return {k: str(v) if isinstance(v, Path) else v for k, v in result.items()}
    return {"raw": str(result)}


def _list_output_files(output_dir: Path) -> list[str]:
    """列出输出目录中的文件"""
    if not output_dir.exists():
        return []
    files = []
    for f in output_dir.iterdir():
        if f.is_file():
            files.append(str(f.relative_to(BASE_DIR.parent)))
    return files


def list_skills() -> list[dict[str, str]]:
    """列出所有可用技能"""
    return [
        {"name": name, "description": spec["description"]}
        for name, spec in SKILL_REGISTRY.items()
    ]


async def run_skill_cli(skill_name: str, query: str):
    """命令行直接运行技能"""
    result = await execute_skill(skill_name, query)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) < 3:
        print("用法: python dispatcher.py <技能名> <查询问句>")
        print(f"可用技能: {list(SKILL_REGISTRY.keys())}")
        _sys.exit(1)
    asyncio.run(run_skill_cli(_sys.argv[1], _sys.argv[2]))
