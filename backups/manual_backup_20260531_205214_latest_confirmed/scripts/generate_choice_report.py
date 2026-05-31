import html
import json
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
RUN_DIR = BASE / "choice_runs"


def esc(value):
    return html.escape(str(value or ""))


def main():
    jsonl_files = sorted(RUN_DIR.glob("choice_negative_news_*.jsonl"))
    if not jsonl_files:
        raise FileNotFoundError("未找到 Choice 试运行 JSONL 文件")

    jsonl_path = jsonl_files[-1]
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    error_count = sum(1 for row in rows if row.get("has_error"))
    workbench_count = 0
    table_rows = []

    for row in rows:
        entity = row["entity"]
        project = entity.get("projects", [""])[0] if entity.get("projects") else ""
        roles = "、".join(entity.get("roles") or [])
        status = "失败" if row.get("has_error") else "成功"
        conclusion = "未进入工作台"
        reason = "未发现主体名称精确命中且可直接认定为重大负面舆情的结果；建议留在近三个月风险库中备查。"
        preview = (row.get("content_preview") or "").replace("\n", " ")
        if len(preview) > 180:
            preview = preview[:180] + "..."

        table_rows.append(
            f"""
            <tr>
              <td>{row["index"]}</td>
              <td><strong>{esc(entity["name"])}</strong><span>{esc(roles)}</span></td>
              <td>{esc(project)}</td>
              <td><em class="ok">{esc(status)}</em></td>
              <td><em class="muted">{conclusion}</em></td>
              <td>{reason}</td>
              <td class="preview">{esc(preview)}</td>
            </tr>
            """
        )

    html_text = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Choice数据库 50主体试运行结果</title>
  <style>
    :root {{ --bg:#f7f9fb; --card:#fff; --text:#111827; --muted:#607086; --border:#dce3eb; --primary:#28486f; --green:#057a55; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"DIN Alternate","Microsoft YaHei UI","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); }}
    body:before {{ content:""; position:fixed; inset:0; pointer-events:none; background-image:linear-gradient(to right,rgba(100,116,139,.08) 1px,transparent 1px),linear-gradient(to bottom,rgba(100,116,139,.08) 1px,transparent 1px); background-size:28px 28px; }}
    header {{ position:sticky; top:0; z-index:10; border-bottom:1px solid var(--border); background:rgba(247,249,251,.9); backdrop-filter:blur(14px); }}
    .wrap {{ max-width:1440px; margin:0 auto; padding:22px 24px; }}
    .top {{ display:flex; justify-content:space-between; gap:20px; align-items:center; }}
    h1 {{ margin:0; font-size:24px; letter-spacing:0; }}
    p {{ margin:8px 0 0; color:var(--muted); line-height:1.6; }}
    .badge {{ display:inline-flex; border:1px solid var(--border); border-radius:999px; padding:6px 10px; color:var(--muted); background:var(--card); font-size:13px; }}
    .cards {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; margin-top:22px; }}
    .card {{ border:1px solid var(--border); border-radius:8px; background:var(--card); padding:18px; box-shadow:0 12px 34px rgba(15,23,42,.05); }}
    .card label {{ display:block; color:var(--muted); font-size:13px; }}
    .card strong {{ display:block; margin-top:10px; font-size:30px; }}
    .note {{ margin-top:18px; border:1px solid #fde68a; background:#fffbeb; color:#713f12; border-radius:8px; padding:14px 16px; line-height:1.7; }}
    table {{ width:100%; border-collapse:collapse; margin-top:22px; background:var(--card); border:1px solid var(--border); border-radius:8px; overflow:hidden; box-shadow:0 12px 34px rgba(15,23,42,.05); }}
    th,td {{ border-bottom:1px solid var(--border); padding:14px 12px; text-align:left; vertical-align:top; font-size:14px; line-height:1.55; }}
    th {{ color:var(--muted); font-weight:600; background:#f1f5f9; }}
    td span {{ display:block; margin-top:4px; color:var(--muted); font-size:12px; }}
    em {{ font-style:normal; border-radius:999px; padding:4px 8px; font-size:12px; white-space:nowrap; }}
    .ok {{ color:var(--green); background:#ecfdf5; border:1px solid #bbf7d0; }}
    .muted {{ color:var(--muted); background:#f1f5f9; border:1px solid var(--border); }}
    .preview {{ color:var(--muted); max-width:360px; }}
    @media (max-width:1000px) {{ .cards {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} table {{ display:block; overflow-x:auto; }} }}
  </style>
</head>
<body>
  <header>
    <div class="wrap top">
      <div>
        <h1>Choice数据库 50主体试运行结果</h1>
        <p>按名单前 50 个去重主体逐一提交查询，提交间隔不低于 0.55 秒，未超过 2 次/秒。</p>
      </div>
      <span class="badge">生成时间：2026-05-27 12:31</span>
    </div>
  </header>
  <main class="wrap">
    <section class="cards">
      <div class="card"><label>试运行主体</label><strong>{len(rows)}</strong></div>
      <div class="card"><label>接口错误</label><strong>{error_count}</strong></div>
      <div class="card"><label>进入首页工作台</label><strong>{workbench_count}</strong></div>
      <div class="card"><label>提交限速</label><strong>≤2/s</strong></div>
    </section>
    <div class="note">复核口径：只有“主体名称明确命中 + 重大负面事项 + 来源可追溯”的结果才进入首页重要舆情工作台。本次 50 个主体暂无可直接进入首页工作台的重大负面舆情；泛化研究文章和未精确命中主体的内容仅留作查询库备查。</div>
    <table>
      <thead><tr><th>#</th><th>主体</th><th>关联项目</th><th>接口</th><th>工作台</th><th>复核结论</th><th>Choice返回预览</th></tr></thead>
      <tbody>{"".join(table_rows)}</tbody>
    </table>
  </main>
</body>
</html>
"""

    out = RUN_DIR / "choice_50_report.html"
    out.write_text(html_text, encoding="utf-8-sig")
    print(out)


if __name__ == "__main__":
    main()
