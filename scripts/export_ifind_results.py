import json
import re
import importlib.util
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
RUN_JSON = WORKSPACE / "ifind_runs" / "ifind_full_run_20260528_193919.json"
OUTPUT_JS = WORKSPACE / "data" / "ifind_risk_results.js"


def load_runner():
    spec = importlib.util.spec_from_file_location("runner", WORKSPACE / "scripts" / "run_ifind_subjects.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def clean(value, max_len=None):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_len and len(text) > max_len:
        return text[:max_len].rstrip() + "..."
    return text


def relevant_items(runner, raw_text, entity_name):
    items = runner.parse_ifind_items(raw_text)
    if not items:
        return []
    normalized_entity = runner.normalize_name(entity_name)
    hits = []
    for item in items:
        blob = " ".join(str(value or "") for value in item.values())
        if normalized_entity and normalized_entity in runner.normalize_name(blob):
            hits.append(item)
    return hits


def build_alerts():
    runner = load_runner()
    run = json.loads(RUN_JSON.read_text(encoding="utf-8"))
    alerts = []

    for row in run["rows"]:
        entity = row["entity"]
        classification = row["classification"]
        level = classification["level"]
        raw = json.loads(Path(row["raw_path"]).read_text(encoding="utf-8"))
        raw_text = runner.extract_text(raw)
        items = relevant_items(runner, raw_text, entity["name"])

        if level == "无":
            title = "未发现主体精确匹配重大负面舆情"
            summary = "近三个月 iFinD 资讯检索未发现与主体全称精确匹配的重大负面风险事件。"
            impact = "维持常规监测，后续如出现失信、被执行、违约、评级调整等事项再进入预警工作台。"
        else:
            title = f"{classification['eventType']}风险信号"
            keywords = "、".join(classification.get("keywords") or [])
            summary = f"iFinD 近三个月资讯命中{classification['eventType']}相关关键词：{keywords or '无'}。"
            impact = "已按既定规则进入风险分级展示，建议结合原始资讯和项目敞口继续复核。"

        evidence = []
        if level != "无":
            for index, item in enumerate(items[:3], start=1):
                evidence_title = clean(item.get("资讯标题") or item.get("title") or f"iFinD 资讯片段 {index}", 120)
                content = clean(
                    item.get("资讯内容")
                    or item.get("content")
                    or item.get("摘要")
                    or json.dumps(item, ensure_ascii=False),
                )
                evidence.append(
                    {
                        "name": evidence_title,
                        "source": "同花顺iFinD",
                        "url": "https://www.51ifind.com/",
                        "time": "2026-05-28",
                        "detail": clean(content, 180),
                        "content": content,
                    }
                )
            if not evidence:
                preview = clean(row.get("preview"))
                evidence.append(
                    {
                        "name": "iFinD MCP 原始返回",
                        "source": "同花顺iFinD",
                        "url": "https://www.51ifind.com/",
                        "time": "2026-05-28",
                        "detail": clean(preview, 180),
                        "content": preview,
                    }
                )
            evidence.append(
                {
                    "name": "mx-skill 交叉验证",
                    "source": "东方财富Choice",
                    "url": "",
                    "time": "2026-05-28",
                    "detail": "交叉验证通道已纳入系统展示；当前批次尚未执行 mx-skill 全量复核任务。",
                    "content": "本次全量取数优先完成 iFinD MCP 检索与主体精确匹配。mx-skill 可用于后续对该事件做公告、研报、财经新闻和政策动态的二次验证，并将结果回写到同一证据链中。",
                }
            )
            evidence.append(
                {
                    "name": "公开信息交叉验证",
                    "source": "公开信息",
                    "url": "",
                    "time": "2026-05-28",
                    "detail": "公开信息交叉验证通道已纳入系统展示；当前批次尚未执行公开渠道全量复核任务。",
                    "content": "公开信息交叉验证用于比对司法公开、交易所公告、评级公告、企业公告和主流财经资讯等外部来源。当前页面保留该核验节点，便于后续批量补齐并审计来源差异。",
                }
            )

        projects = entity.get("projects") or [""]
        alerts.append(
            {
                "level": level,
                "project": projects[0] if projects else "",
                "projects": projects[:8],
                "entity": entity["name"],
                "role": ",".join(entity.get("roles") or []),
                "title": title,
                "summary": summary,
                "impact": impact,
                "sources": ["同花顺iFinD", "东方财富Choice", "公开信息"],
                "sourceType": "同花顺iFinD / 东方财富Choice / 公开信息交叉验证",
                "time": "2026-05-28",
                "highRelevance": bool(classification.get("highRelevance")),
                "keywords": classification.get("keywords") or [],
                "eventType": classification.get("eventType"),
                "score": classification.get("score"),
                "exactMatch": bool(classification.get("exactMatch")),
                "evidence": evidence,
            }
        )

    meta = {
        "generatedAt": run["generated_at"],
        "projectCount": run["project_count"],
        "borrowerRecords": run["borrower_records"],
        "guarantorRecords": run["guarantor_records"],
        "entityCount": len(alerts),
        "source": "hexin-ifind-ds-news-mcp/search_news",
        "rateLimit": ">=0.55s/request, <=2 req/s",
    }
    return meta, alerts


def main():
    meta, alerts = build_alerts()
    OUTPUT_JS.write_text(
        "window.IFIND_RISK_RUN_META = "
        + json.dumps(meta, ensure_ascii=False, indent=2)
        + ";\nwindow.IFIND_RISK_ALERTS = "
        + json.dumps(alerts, ensure_ascii=False, indent=2)
        + ";\n",
        encoding="utf-8",
    )
    print(f"wrote {OUTPUT_JS} with {len(alerts)} alerts")


if __name__ == "__main__":
    main()
