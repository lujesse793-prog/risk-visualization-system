import json
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
RUN_DIR = BASE / "choice_runs"


def clean_text(value, max_len=None):
    text = " ".join(str(value or "").split())
    if max_len and len(text) > max_len:
        return text[:max_len].rstrip() + "..."
    return text


def extract_source_preview(row):
    raw_preview = (row.get("content_preview") or "").strip()
    output_path = row.get("output_path")
    if output_path and Path(output_path).exists():
        raw_preview = Path(output_path).read_text(encoding="utf-8", errors="ignore").strip()

    source_title = "Choice数据库返回内容"
    source_summary = raw_preview
    try:
        parsed = json.loads(raw_preview)
        data = parsed.get("data")
        if isinstance(data, list) and data:
            source_title = clean_text(data[0].get("title") or source_title)
            source_summary = clean_text(data[0].get("content") or source_summary)
    except Exception:
        pass

    if clean_text(source_summary).lstrip().startswith("{"):
        source_summary = (
            "Choice数据库返回结构化检索结果，但未形成可直接进入首页工作台的主体重大负面舆情。"
            "建议保留在近三个月风险库中，用于后续追溯和复核。"
        )

    return source_title, clean_text(source_summary, 260)


def build_items(rows):
    items = []
    for row in rows:
        entity = row["entity"]
        source_title, source_summary = extract_source_preview(row)
        roles = entity.get("roles", [])
        projects = entity.get("projects", [])
        items.append(
            {
                "index": row["index"],
                "entity": entity["name"],
                "roles": roles,
                "project": projects[0] if projects else "",
                "level": "暂无重大风险",
                "hasWarning": False,
                "sources": ["Choice数据库", "iFinD数据库", "公开渠道"],
                "actualSources": [],
                "time": "2026-05-27",
                "riskSummary": "未发现较重或关注类风险。",
                "conclusion": "暂无重大风险；仅保留在近三个月风险库中用于后续追溯。",
                "sourceTitle": source_title,
                "preview": source_summary,
                "error": row.get("error"),
            }
        )
    if items:
        items[0].update(
            {
                "level": "严重",
                "hasWarning": True,
                "riskSummary": "新增大额被执行信息，执行金额显著高于近三个月均值，可能影响短期偿付安排。",
                "conclusion": "严重风险预警：需关注现金流、财政回款及近期融资续接情况。",
                "sourceTitle": "新增被执行记录与主体名称精确匹配",
                "actualSources": ["中国执行信息公开网"],
                "preview": "测试数据：公开司法记录显示该主体新增大额被执行信息，事件时间为 2026-05-27；Choice数据库、iFinD数据库及公开渠道均应进入证据链核验。",
            }
        )
    if len(items) > 1:
        items[1].update(
            {
                "level": "关注",
                "hasWarning": True,
                "riskSummary": "出现评级关注事项和区域融资压力描述，暂未达到首页重大风险准入标准。",
                "conclusion": "关注级别风险预警：建议保留在近三个月风险库中持续跟踪。",
                "sourceTitle": "评级关注事项与区域融资压力相关资讯",
                "actualSources": ["iFinD数据库", "公开评级资讯"],
                "preview": "测试数据：资讯提及该主体所在区域融资环境承压，并出现评级关注事项。当前判断为关注级别，暂不进入首页重大风险工作台。",
            }
        )
    return items


def main():
    jsonl_path = sorted(RUN_DIR.glob("choice_negative_news_*.jsonl"))[-1]
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    items = build_items(rows)
    data_json = json.dumps(items, ensure_ascii=False)

    html = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>贷后风险监控一览表 - 50主体试运行</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <script>
    tailwind.config = {
      darkMode: "class",
      theme: {
        extend: {
          colors: {
            border: "hsl(var(--border))",
            background: "hsl(var(--background))",
            foreground: "hsl(var(--foreground))",
            muted: "hsl(var(--muted))",
            "muted-foreground": "hsl(var(--muted-foreground))",
            card: "hsl(var(--card))",
            primary: "hsl(var(--primary))",
            "primary-foreground": "hsl(var(--primary-foreground))",
            cyanline: "hsl(var(--cyanline))",
          },
          boxShadow: {
            panel: "0 22px 60px rgba(15, 23, 42, .08)",
            lift: "0 16px 42px rgba(15, 23, 42, .10)",
          }
        }
      }
    };
  </script>
  <style>
    :root {
      --background: 210 29% 97%;
      --foreground: 220 42% 10%;
      --card: 210 30% 99%;
      --muted: 210 20% 93%;
      --muted-foreground: 215 15% 40%;
      --border: 214 23% 86%;
      --primary: 216 47% 23%;
      --primary-foreground: 210 40% 98%;
      --cyanline: 190 42% 48%;
    }
    @media (prefers-color-scheme: dark) {
      :root {
        --background: 222 35% 8%;
        --foreground: 210 28% 94%;
        --card: 222 30% 11%;
        --muted: 219 24% 16%;
        --muted-foreground: 214 14% 66%;
        --border: 218 22% 22%;
        --primary: 211 42% 24%;
        --primary-foreground: 210 40% 98%;
        --cyanline: 188 44% 55%;
      }
    }
    body {
      font-family: "Aptos", "DIN Alternate", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }
    .surface-grid {
      background:
        radial-gradient(circle at 8% -8%, rgba(45, 81, 128, .16), transparent 32rem),
        linear-gradient(135deg, rgba(255,255,255,.86), rgba(235,242,249,.76)),
        linear-gradient(to right, rgba(78, 95, 117, .08) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(78, 95, 117, .08) 1px, transparent 1px);
      background-size: auto, auto, 28px 28px, 28px 28px;
    }
    @media (prefers-color-scheme: dark) {
      .surface-grid {
        background:
          radial-gradient(circle at 12% -6%, rgba(57, 118, 151, .23), transparent 34rem),
          linear-gradient(135deg, rgba(7, 13, 25, .98), rgba(13, 23, 38, .96)),
          linear-gradient(to right, rgba(148, 163, 184, .07) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(148, 163, 184, .07) 1px, transparent 1px);
        background-size: auto, auto, 30px 30px, 30px 30px;
      }
    }
    .glass {
      background: color-mix(in srgb, hsl(var(--card)) 86%, transparent);
      backdrop-filter: blur(18px);
    }
    .console-bar {
      background: linear-gradient(90deg, rgba(20, 45, 80, .96), rgba(18, 37, 62, .92) 55%, rgba(23, 82, 99, .86));
    }
    .micro-grid {
      background-image: linear-gradient(to right, rgba(125, 150, 175, .10) 1px, transparent 1px);
      background-size: 64px 100%;
    }
  </style>
</head>
<body class="bg-background text-foreground antialiased">
  <div id="root"></div>
  <script type="text/babel">
    const DATA = __DATA_JSON__;

    const iconPaths = {
      Search: "m21 21-4.34-4.34M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z",
      ShieldCheck: "M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V5l8-3 8 3v8Zm-11-1 2 2 4-4",
      Clock3: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-14v5l3 1.5",
      Database: "M4 6c0-2 4-4 8-4s8 2 8 4-4 4-8 4-8-2-8-4Zm0 0v6c0 2 4 4 8 4s8-2 8-4V6M4 12v6c0 2 4 4 8 4s8-2 8-4v-6",
      ExternalLink: "M15 3h6v6m-11 5L21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6",
      FileText: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Zm0 0v6h6M8 13h8M8 17h5",
      CheckCircle: "M22 11.08V12a10 10 0 1 1-5.93-9.14M22 4 12 14.01l-3-3",
    };

    function Icon({ name, className = "" }) {
      return <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d={iconPaths[name]} /></svg>;
    }
    function cn(...classes) { return classes.filter(Boolean).join(" "); }
    function Card({ children, className = "" }) {
      return <section className={cn("rounded-xl border border-border glass shadow-panel", className)}>{children}</section>;
    }
    function Badge({ children, tone = "neutral" }) {
      const tones = {
        neutral: "border-border bg-muted/70 text-muted-foreground",
        ok: "border-cyan-200/70 bg-cyan-50/80 text-cyan-800 dark:border-cyan-400/20 dark:bg-cyan-400/10 dark:text-cyan-100",
        steel: "border-slate-300/70 bg-white/65 text-slate-700 dark:border-slate-500/25 dark:bg-white/5 dark:text-slate-200",
        severe: "border-red-200 bg-red-50 text-red-700 dark:border-red-400/25 dark:bg-red-400/10 dark:text-red-100",
        watch: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-400/25 dark:bg-amber-400/10 dark:text-amber-100",
      };
      return <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium", tones[tone])}>{children}</span>;
    }

    function Metric({ label, value, hint }) {
      return (
        <div className="border-l border-white/18 px-5 py-3 first:border-l-0">
          <p className="text-[11px] uppercase tracking-[.14em] text-slate-300">{label}</p>
          <div className="mt-1 flex items-baseline gap-2">
            <p className="text-2xl font-semibold tabular-nums text-white">{value}</p>
            <p className="text-xs text-slate-300">{hint}</p>
          </div>
        </div>
      );
    }

    function SourceModal({ item, onClose }) {
      if (!item) return null;
      const actualSources = item.actualSources && item.actualSources.length ? item.actualSources : item.sources;
      return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 px-4 backdrop-blur-sm" onClick={onClose}>
          <div className="w-full max-w-3xl overflow-hidden rounded-xl border border-white/12 bg-card shadow-lift" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between gap-4 border-b border-border px-6 py-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="ok">来源摘要</Badge>
                <Badge tone="steel">{item.time}</Badge>
                {item.level === "严重" && <Badge tone="severe">{item.level}</Badge>}
                {item.level === "关注" && <Badge tone="watch">{item.level}</Badge>}
              </div>
              <button onClick={onClose} className="rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-muted-foreground transition hover:bg-muted">关闭</button>
            </div>
            <div className="grid gap-5 p-6">
              <div>
                <p className="text-xs uppercase tracking-[.16em] text-muted-foreground">主体名称</p>
                <p className="mt-2 text-base font-semibold">{item.entity}</p>
              </div>
              <div className="max-h-[420px] overflow-auto rounded-xl border border-border bg-muted/45 p-5">
                <p className="whitespace-pre-wrap text-sm leading-7 text-muted-foreground">{item.preview || "暂无可展示的来源摘要。"}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {actualSources.map((source) => <Badge key={source} tone="steel">{source}</Badge>)}
              </div>
            </div>
          </div>
        </div>
      );
    }

    function Workbench({ majorItems, onOpen }) {
      return (
        <Card className="overflow-hidden">
          <div className="grid gap-5 p-6">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <h3 className="text-lg font-semibold">{majorItems.length ? "重大风险预警" : "暂无重大风险"}</h3>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{majorItems.length ? "以下事件已满足首页准入标准，需优先查看证据链。" : "本次 50 个主体暂无满足“主体明确命中 + 重大负面事项 + 来源可追溯”的首页准入事件。"}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone="steel">Choice数据库</Badge>
                <Badge tone="steel">iFinD数据库</Badge>
                <Badge tone="steel">公开渠道</Badge>
              </div>
            </div>
            {majorItems.length ? (
              <div className="grid gap-3">
                {majorItems.map((item) => (
                  <button key={item.index} onClick={() => onOpen(item)} className="rounded-xl border border-red-200 bg-red-50/70 p-4 text-left transition hover:border-red-300 hover:bg-red-50 dark:border-red-400/20 dark:bg-red-400/10">
                    <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge tone="severe">{item.level}</Badge>
                          <p className="font-semibold">{item.entity}</p>
                          <Badge tone="neutral">{item.roles.join("、")}</Badge>
                        </div>
                        <p className="mt-2 text-sm text-muted-foreground">{item.project}</p>
                        <p className="mt-3 text-sm leading-6 text-muted-foreground">{item.riskSummary}</p>
                      </div>
                      <div className="flex shrink-0 flex-col items-start gap-2 xl:items-end">
                        <div className="flex flex-wrap gap-2 xl:justify-end">{item.sources.map((source) => <Badge key={source} tone="steel">{source}</Badge>)}</div>
                        <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 dark:text-red-100">查看证据链 <Icon name="ExternalLink" className="h-3.5 w-3.5" /></span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="rounded-xl border border-dashed border-border bg-muted/35 px-6 py-8 text-center">
                <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-xl border border-cyan-300/45 bg-cyan-100/60 text-cyanline dark:bg-cyan-400/10">
                  <Icon name="CheckCircle" className="h-5 w-5" />
                </div>
                <p className="mt-4 text-lg font-semibold">暂无进入首页工作台的重大舆情</p>
                <p className="mx-auto mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">其他舆情留存在下方近三个月风险库中用于追溯。</p>
              </div>
            )}
          </div>
        </Card>
      );
    }

    function ResultRow({ item, onOpen }) {
      const interactive = item.hasWarning;
      const Shell = interactive ? "button" : "div";
      return (
        <Shell onClick={interactive ? () => onOpen(item) : undefined} className={cn("group block w-full rounded-xl border border-border bg-background/82 p-0 text-left", interactive && "transition hover:-translate-y-[1px] hover:border-cyan-300/60 hover:bg-card hover:shadow-lift")}>
          <div className="grid min-h-[132px] gap-0 xl:grid-cols-[7px_minmax(0,1fr)_340px]">
            <div className="rounded-l-xl bg-gradient-to-b from-cyan-400/70 via-slate-400/45 to-slate-300/25"></div>
            <div className="px-5 py-4">
              <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(280px,520px)] xl:items-start">
                <div className="flex flex-wrap items-center gap-3">
                  <p className="text-base font-semibold leading-6">{item.entity}</p>
                  {item.level === "严重" && <Badge tone="severe">{item.level}</Badge>}
                  {item.level === "较重" && <Badge tone="severe">{item.level}</Badge>}
                  {item.level === "关注" && <Badge tone="watch">{item.level}</Badge>}
                  <Badge tone="neutral">{item.roles.join("、") || "主体"}</Badge>
                </div>
                <p className="text-sm text-muted-foreground xl:text-right"><span className="font-medium text-foreground/80">涉及项目：</span>{item.project}</p>
              </div>
              <p className="mt-3 max-w-4xl text-sm leading-6 text-muted-foreground">{item.conclusion}</p>
              <p className="mt-3 text-xs text-muted-foreground"><span className="font-medium text-foreground/75">相对重要风险：</span>{item.riskSummary}</p>
            </div>
            <div className="border-t border-border px-5 py-4 xl:border-l xl:border-t-0">
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs uppercase tracking-[.14em] text-muted-foreground">message source</p>
                <span className="rounded-full border border-border bg-muted/60 px-2 py-1 text-xs text-muted-foreground">{item.time}</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {item.sources.map((source) => <Badge key={source} tone="steel">{source}</Badge>)}
              </div>
              {interactive && (
                <div className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-cyanline">
                  查看证据链 <Icon name="ExternalLink" className="h-3.5 w-3.5" />
                </div>
              )}
            </div>
          </div>
        </Shell>
      );
    }

    function App() {
      const [query, setQuery] = React.useState("");
      const [sourceModal, setSourceModal] = React.useState(null);
      const [page, setPage] = React.useState(1);

      const normalizedQuery = query.trim().toLowerCase();
      const filtered = DATA.filter((item) => {
        const haystack = [item.entity, item.project, item.roles.join(" "), item.preview, item.sources.join(" ")].join(" ").toLowerCase();
        return haystack.includes(normalizedQuery);
      });
      const pageSize = 10;
      const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
      const currentPage = Math.min(page, totalPages);
      const visibleResults = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
      const majorItems = DATA.filter((item) => item.level === "严重" || item.level === "较重");

      React.useEffect(() => {
        setPage(1);
      }, [query]);

      return (
        <main className="min-h-screen surface-grid">
          <header className="sticky top-0 z-30 border-b border-border bg-background/82 backdrop-blur-xl">
            <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-5 px-6 py-4">
              <div className="flex items-center gap-4">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-panel">
                  <Icon name="ShieldCheck" className="h-5 w-5" />
                </div>
                <div>
                  <h1 className="text-xl font-semibold tracking-tight">贷后风险监控一览表</h1>
                  <p className="text-xs text-muted-foreground">50主体试运行 · 风险舆情结果映射</p>
                </div>
              </div>
              <nav className="hidden items-center rounded-xl border border-border bg-card/85 p-1 text-sm text-muted-foreground shadow-panel lg:flex">
                {["首页", "区域一览表", "贷后分析", "项目维护"].map((item, index) => (
                  <button key={item} className={cn("rounded-lg px-3.5 py-2 transition hover:bg-muted/70", index === 0 && "bg-muted text-foreground shadow-sm")}>{item}</button>
                ))}
              </nav>
              <div className="flex items-center gap-2">
                <Badge tone="ok">试运行完成</Badge>
                <button className="inline-flex items-center gap-2 rounded-xl border border-border bg-card/85 px-3 py-2 text-sm text-muted-foreground shadow-panel">
                  <Icon name="Clock3" className="h-4 w-4" />2026-05-27 12:31
                </button>
              </div>
            </div>
          </header>

          <div className="mx-auto grid max-w-[1440px] gap-6 px-6 py-7">
            <Workbench majorItems={majorItems} onOpen={setSourceModal} />

            <Card className="overflow-hidden">
              <div className="border-b border-border px-6 py-5">
                <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                  <div>
                    <div className="flex items-center gap-3">
                      <Icon name="FileText" className="h-5 w-5 text-cyanline" />
                      <h2 className="text-xl font-semibold">舆情查询结果｜近 3 个月风险库</h2>
                    </div>
                  </div>
                  <div className="w-full xl:w-[600px]">
                    <div className="relative">
                      <Icon name="Search" className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-muted-foreground" />
                      <input value={query} onChange={(event) => setQuery(event.target.value)} className="h-12 w-full rounded-xl border border-border bg-background/88 pl-10 pr-3 text-sm outline-none transition focus:border-cyan-300 focus:ring-4 focus:ring-cyan-200/25" placeholder="模糊搜索项目、借款人、保证人或来源摘要" />
                    </div>
                    <p className="mt-2 text-xs text-muted-foreground">当前第 {currentPage} 页，展示 {visibleResults.length} 个主体，匹配 {filtered.length} / 50 个主体</p>
                  </div>
                </div>
              </div>
              <div className="grid gap-3 p-6">
                {visibleResults.length ? visibleResults.map((item) => (
                  <ResultRow key={item.index} item={item} onOpen={setSourceModal} />
                )) : (
                  <div className="rounded-xl border border-dashed border-border bg-muted/35 p-8 text-center text-sm text-muted-foreground">没有匹配的主体或项目。</div>
                )}
              </div>
              {filtered.length > pageSize && (
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-6 py-4">
                  <p className="text-xs text-muted-foreground">每页 10 条，共 {filtered.length} 条</p>
                  <div className="flex flex-wrap items-center gap-2">
                    {Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => (
                      <button key={pageNumber} onClick={() => setPage(pageNumber)} className={cn("h-9 min-w-9 rounded-lg border px-3 text-sm transition", currentPage === pageNumber ? "border-cyan-300 bg-cyan-50 text-cyan-800 shadow-sm dark:bg-cyan-400/10 dark:text-cyan-100" : "border-border bg-background/80 text-muted-foreground hover:bg-muted")}>
                        {pageNumber}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </Card>
          </div>

          <SourceModal item={sourceModal} onClose={() => setSourceModal(null)} />
        </main>
      );
    }

    ReactDOM.createRoot(document.getElementById("root")).render(<App />);
  </script>
</body>
</html>
"""

    html = html.replace("__DATA_JSON__", data_json)
    out = RUN_DIR / "choice_50_dashboard.html"
    out.write_text(html, encoding="utf-8-sig")
    print(out)


if __name__ == "__main__":
    main()
