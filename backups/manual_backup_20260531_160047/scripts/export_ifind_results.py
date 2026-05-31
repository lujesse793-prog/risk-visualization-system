#!/usr/bin/env python3
"""
export_ifind_results.py v2 - Refactored data export pipeline
Principle: Preserve full raw data, no truncation; tiered evidence marking.
"""

import json
import re
import importlib.util
from datetime import date
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
OUTPUT_JS = WORKSPACE / "data" / "ifind_risk_results.js"
RAW_DIR = WORKSPACE / "ifind_runs" / "raw"


def load_runner():
    spec = importlib.util.spec_from_file_location(
        "runner", WORKSPACE / "scripts" / "run_ifind_subjects.py"
    )
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


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


def determine_risk_conclusion(level, exact_match, has_full_text=False):
    if level == "\u65e0":
        return "\u65e0\u98ce\u9669\u4fe1\u53f7"
    if not exact_match:
        return "\u4ec5\u7ebf\u7d22"
    if level == "\u4e25\u91cd" and exact_match:
        return "\u5df2\u6838\u5b9e"
    if level == "\u8f83\u91cd" and exact_match:
        return "\u7591\u4f3c"
    if level == "\u5173\u6ce8" and exact_match:
        return "\u5f85\u6838\u9a8c"
    return "\u4ec5\u7ebf\u7d22"


def build_alerts():
    runner = load_runner()
    run_files = sorted(WORKSPACE.glob("ifind_runs/ifind_full_run_*.json"), reverse=True)
    if not run_files:
        raise FileNotFoundError("No ifind run JSON found")
    run_path = run_files[0]
    print(f"Using run: {run_path}")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    alerts = []

    for row in run["rows"]:
        entity = row["entity"]
        classification = row["classification"]
        level = classification["level"]
        raw_path = Path(row["raw_path"])
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        raw_text = runner.extract_text(raw)
        full_raw_text = raw_text
        items = relevant_items(runner, raw_text, entity["name"])

        has_precise_match = bool(classification.get("exactMatch"))
        risk_conclusion = determine_risk_conclusion(level, has_precise_match)

        if level == "\u65e0":
            title = "\u672a\u53d1\u73b0\u4e3b\u4f53\u7cbe\u786e\u5339\u914d\u91cd\u5927\u8d1f\u9762\u8206\u60c5"
            summary = "\u8fd1\u4e09\u4e2a\u6708 iFind \u8d44\u8baf\u68c0\u7d22\u672a\u53d1\u73b0\u4e0e\u4e3b\u4f53\u5168\u79f0\u7cbe\u786e\u5339\u914d\u7684\u91cd\u5927\u8d1f\u9762\u98ce\u9669\u4e8b\u4ef6\u3002"
            impact = "\u7ef4\u6301\u5e38\u89c4\u76d1\u6d4b\uff0c\u540e\u7eed\u5982\u51fa\u73b0\u5931\u4fe1\u3001\u88ab\u6267\u884c\u3001\u8fdd\u7ea6\u3001\u8bc4\u7ea7\u8c03\u6574\u7b49\u4e8b\u9879\u518d\u8fdb\u5165\u9884\u8b66\u5de5\u4f5c\u53f0\u3002"
        else:
            title_tpl = classification.get("eventType", "\u98ce\u9669")
            title = f"{title_tpl}\u98ce\u9669\u4fe1\u53f7"
            keywords = "\u3001".join(classification.get("keywords") or [])
            note = "\u3010\u6ce8\u610f\u3011iFinD MCP \u4ec5\u8fd4\u56de\u8d44\u8baf\u7247\u6bb5\uff0c\u975e\u5168\u6587\u3002"
            summary = f"{note} iFinD \u8fd1\u4e09\u4e2a\u6708\u8d44\u8baf\u547d\u4e2d{title_tpl}\u76f8\u5173\u5173\u952e\u8bcd\uff1a{keywords or '\u65e0'}\u3002\u5efa\u8bae\u7ed3\u5408\u539f\u59cb URL \u8fdb\u884c\u5168\u6587\u6838\u9a8c\u3002"
            impact = "\u5df2\u6309\u65e2\u5b9a\u89c4\u5219\u8fdb\u5165\u98ce\u9669\u5206\u7ea7\u5c55\u793a\uff0c\u5efa\u8bae\u7ed3\u5408\u539f\u59cb\u8d44\u8baf\u548c\u9879\u76ee\u655e\u53e3\u7ee7\u7eed\u590d\u6838\u3002"

        evidence = []
        for index, item in enumerate(items[:6], start=1):
            raw_title = item.get("\u8d44\u8baf\u6807\u9898") or item.get("title") or ""
            raw_content = (
                item.get("\u8d44\u8baf\u5185\u5bb9")
                or item.get("content")
                or item.get("\u6458\u8981")
                or ""
            )
            raw_url = item.get("URL") or item.get("url") or item.get("jumpUrl", "")
            raw_date = item.get("\u65e5\u671f") or item.get("date") or item.get("time", "")

            full_raw_text_item = json.dumps(item, ensure_ascii=False)

            display_title = raw_title[:33] + "..." if raw_title and len(raw_title) > 36 else (raw_title or "iFinD \u8d44\u8baf\u7247\u6bb5")
            card_summary = raw_content[:117] + "..." if raw_content and len(raw_content) > 120 else (raw_content or "\u65e0\u5185\u5bb9")
            risk_summary = raw_content[:300] if raw_content else ""

            evidence.append({
                "evidenceId": f"ev_ifind_{index}_{entity['name'][:6]}",
                "evidenceType": "ifind_snippet",
                "evidenceCategory": "\u5f85\u6838\u9a8c\u7ebf\u7d22",
                "subjectMatched": True,
                "matchedSubjectName": entity["name"],
                "accessLevel": "snippet_only",
                "sourceReliability": "reliable",
                "title": raw_title or "iFinD \u8d44\u8baf\u7247\u6bb5",
                "displayTitle": display_title,
                "riskSummary": risk_summary,
                "cardSummary": card_summary,
                "matchedExcerpt": raw_content,
                "sourceFullText": raw_content,
                "fullRawText": full_raw_text_item,
                "isTruncatedBySource": True,
                "parseStatus": "ok",
                "warning": "\u8be5\u6765\u6e90\u4ec5\u83b7\u53d6\u5230\u6458\u8981\uff0c\u672a\u83b7\u53d6\u5b8c\u6574\u539f\u6587\uff0c\u5efa\u8bae\u70b9\u51fb\u6765\u6e90URL\u6838\u9a8c\u3002",
                "publishDate": raw_date,
                "hitDate": row.get("time", ""),
                "publisher": "iFinD",
                "dataSource": "iFinD MCP",
                "channel": "\u540c\u82b1\u987aiFinD",
                "url": raw_url,
                "tags": classification.get("keywords") or [],
            })

        if not evidence and level != "\u65e0":
            evidence.append({
                "evidenceId": f"ev_raw_{entity['name'][:6]}",
                "evidenceType": "raw_mcp_response",
                "evidenceCategory": "\u5f85\u6838\u9a8c\u7ebf\u7d22",
                "subjectMatched": False,
                "matchedSubjectName": "",
                "accessLevel": "snippet_only",
                "sourceReliability": "reliable",
                "title": "iFinD MCP \u539f\u59cb\u8fd4\u56de",
                "displayTitle": "iFinD MCP \u539f\u59cb\u8fd4\u56de",
                "riskSummary": "",
                "cardSummary": "MCP\u539f\u59cb\u8fd4\u56de\u6570\u636e\uff0c\u672a\u547d\u4e2d\u4e3b\u4f53\u7cbe\u786e\u5339\u914d\u3002",
                "matchedExcerpt": "",
                "sourceFullText": raw_text,
                "fullRawText": full_raw_text,
                "isTruncatedBySource": True,
                "parseStatus": "no_match",
                "warning": "\u8be5\u6765\u6e90\u4ec5\u83b7\u53d6\u5230\u6458\u8981\uff0c\u672a\u547d\u4e2d\u4e3b\u4f53\u7cbe\u786e\u5339\u914d\uff0c\u5efa\u8bae\u70b9\u51fb\u6765\u6e90\u6838\u9a8c\u3002",
                "publishDate": "",
                "hitDate": row.get("time", ""),
                "publisher": "iFinD",
                "dataSource": "iFinD MCP",
                "channel": "\u540c\u82b1\u987aiFinD",
                "url": "",
                "tags": [],
            })

        projects = entity.get("projects") or [""]
        alerts.append({
            "level": level,
            "riskConclusionType": risk_conclusion,
            "project": projects[0] if projects else "",
            "projects": projects[:8],
            "entity": entity["name"],
            "role": ",".join(entity.get("roles") or []),
            "title": title,
            "summary": summary,
            "impact": impact,
            "sources": ["\u540c\u82b1\u987aiFinD"],
            "sourceType": "iFinD MCP / snippet_only",
            "time": str(date.today()),
            "highRelevance": bool(classification.get("highRelevance")),
            "keywords": classification.get("keywords") or [],
            "eventType": classification.get("eventType"),
            "score": classification.get("score"),
            "exactMatch": bool(classification.get("exactMatch")),
            "evidence": evidence,
            "rawResponsePath": str(raw_path),
            "rawResponseLength": len(raw_text),
        })

    meta = {
        "generatedAt": run["generated_at"],
        "runSource": str(run_path),
        "projectCount": run["project_count"],
        "borrowerRecords": run["borrower_records"],
        "guarantorRecords": run["guarantor_records"],
        "entityCount": len(alerts),
        "source": "hexin-ifind-ds-news-mcp/search_news",
        "rateLimit": "<=2 req/s",
        "dataIntegrity": "snippet_only - MCP\u4ec5\u8fd4\u56de\u8d44\u8baf\u7247\u6bb5\uff0c\u975e\u5168\u6587",
        "evidenceCategories": ["\u5df2\u6838\u9a8c\u8bc1\u636e", "\u8f85\u52a9\u9a8c\u8bc1", "\u5f85\u6838\u9a8c\u7ebf\u7d22"],
    }
    return meta, alerts


def main():
    meta, alerts = build_alerts()
    count_by_level = {}
    for a in alerts:
        lvl = a.get("level", "\u672a\u77e5")
        count_by_level[lvl] = count_by_level.get(lvl, 0) + 1
    js_body = (
        "window.IFIND_RISK_RUN_META = "
        + json.dumps(meta, ensure_ascii=False, indent=2)
        + ";\nwindow.IFIND_RISK_ALERTS = "
        + json.dumps(alerts, ensure_ascii=False, indent=2)
        + ";\n"
    )
    OUTPUT_JS.write_text(js_body, encoding="utf-8")
    print(f"Wrote {OUTPUT_JS} with {len(alerts)} alerts")
    print(f"Level distribution: {count_by_level}")
    evidence_alerts = [a for a in alerts if a.get("evidence")]
    snippet_count = sum(1 for a in evidence_alerts for e in a["evidence"] if e.get("accessLevel") == "snippet_only")
    print(f"Alerts with evidence: {len(evidence_alerts)}")
    print(f"Total evidence items: {sum(len(a['evidence']) for a in evidence_alerts)}")
    print(f"Snippet-only items: {snippet_count}")


if __name__ == "__main__":
    main()
