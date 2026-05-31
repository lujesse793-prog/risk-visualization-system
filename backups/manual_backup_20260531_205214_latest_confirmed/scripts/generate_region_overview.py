import json
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
RUN_DIR = BASE / "choice_runs"


REGION_RULES = [
    ("杭州", ("浙江省", "杭州市", "钱塘区", "330000", "330100")),
    ("钱塘", ("浙江省", "杭州市", "钱塘区", "330000", "330100")),
    ("桐庐", ("浙江省", "杭州市", "桐庐县", "330000", "330100")),
    ("诸暨", ("浙江省", "绍兴市", "诸暨市", "330000", "330600")),
    ("嵊州", ("浙江省", "绍兴市", "嵊州市", "330000", "330600")),
    ("绍兴", ("浙江省", "绍兴市", "越城区", "330000", "330600")),
    ("宁波", ("浙江省", "宁波市", "鄞州区", "330000", "330200")),
    ("湖州", ("浙江省", "湖州市", "吴兴区", "330000", "330500")),
    ("长兴", ("浙江省", "湖州市", "长兴县", "330000", "330500")),
    ("嘉兴", ("浙江省", "嘉兴市", "南湖区", "330000", "330400")),
    ("金华", ("浙江省", "金华市", "婺城区", "330000", "330700")),
    ("温州", ("浙江省", "温州市", "鹿城区", "330000", "330300")),
    ("台州", ("浙江省", "台州市", "椒江区", "330000", "331000")),
    ("苏州", ("江苏省", "苏州市", "姑苏区", "320000", "320500")),
    ("南京", ("江苏省", "南京市", "建邺区", "320000", "320100")),
    ("无锡", ("江苏省", "无锡市", "梁溪区", "320000", "320200")),
    ("常州", ("江苏省", "常州市", "天宁区", "320000", "320400")),
    ("南通", ("江苏省", "南通市", "崇川区", "320000", "320600")),
    ("合肥", ("安徽省", "合肥市", "蜀山区", "340000", "340100")),
    ("滁州", ("安徽省", "滁州市", "琅琊区", "340000", "341100")),
    ("山东", ("山东省", "济南市", "历下区", "370000", "370100")),
    ("济宁", ("山东省", "济宁市", "任城区", "370000", "370800")),
    ("潍坊", ("山东省", "潍坊市", "奎文区", "370000", "370700")),
    ("成都", ("四川省", "成都市", "武侯区", "510000", "510100")),
    ("武汉", ("湖北省", "武汉市", "武昌区", "420000", "420100")),
]


PROVINCE_CODES = {
    "浙江省": "330000",
    "江苏省": "320000",
    "安徽省": "340000",
    "山东省": "370000",
    "四川省": "510000",
    "湖北省": "420000",
}


def infer_region(name, index):
    for key, region in REGION_RULES:
        if key in name:
            return region
    fallback = [
        ("浙江省", "杭州市", "上城区", "330000", "330100"),
        ("江苏省", "苏州市", "吴中区", "320000", "320500"),
        ("安徽省", "合肥市", "包河区", "340000", "340100"),
        ("山东省", "济南市", "历下区", "370000", "370100"),
    ]
    return fallback[index % len(fallback)]


def main():
    jsonl_path = sorted(RUN_DIR.glob("choice_negative_news_*.jsonl"))[-1]
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    items = []
    for i, row in enumerate(rows):
        entity = row["entity"]
        province, city, district, province_code, city_code = infer_region(entity["name"], i)
        level = "无"
        warning_count = 0
        latest_warning_time = ""
        if i == 0:
            level = "严重"
            warning_count = 2
            latest_warning_time = "2026-05-27"
        elif i == 1:
            level = "关注"
            warning_count = 1
            latest_warning_time = "2026-05-26"

        items.append(
            {
                "companyName": entity["name"],
                "projectName": entity.get("projects", [""])[0] if entity.get("projects") else "",
                "role": "、".join(entity.get("roles", [])) or "交易对手",
                "province": province,
                "city": city,
                "district": district,
                "provinceCode": province_code,
                "cityCode": city_code,
                "warningCount": warning_count,
                "latestWarningTime": latest_warning_time,
                "riskLevel": level,
                "source": ["iFinD数据库", "Choice数据库", "公开渠道"] if warning_count else ["iFinD数据库"],
                "lastUpdated": "2026-05-27 22:30",
            }
        )

    data_json = json.dumps(items, ensure_ascii=False)
    province_json = json.dumps(PROVINCE_CODES, ensure_ascii=False)

    html = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>区域一览表 - 贷后风险监控</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
  <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
  <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
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
            panel: "0 22px 58px rgba(15, 23, 42, .08)",
            lift: "0 16px 38px rgba(15, 23, 42, .10)",
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
      --cyanline: 190 42% 45%;
    }
    body {
      font-family: "Aptos", "DIN Alternate", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
      letter-spacing: 0;
    }
    .surface-grid {
      background:
        radial-gradient(circle at 14% -10%, rgba(45, 81, 128, .15), transparent 32rem),
        linear-gradient(135deg, rgba(255,255,255,.9), rgba(235,242,249,.8)),
        linear-gradient(to right, rgba(78, 95, 117, .075) 1px, transparent 1px),
        linear-gradient(to bottom, rgba(78, 95, 117, .075) 1px, transparent 1px);
      background-size: auto, auto, 28px 28px, 28px 28px;
    }
    .glass {
      background: color-mix(in srgb, hsl(var(--card)) 88%, transparent);
      backdrop-filter: blur(18px);
    }
    .map-shell {
      background:
        linear-gradient(180deg, rgba(255,255,255,.75), rgba(241,246,251,.65)),
        linear-gradient(to right, rgba(80, 105, 130, .08) 1px, transparent 1px);
      background-size: auto, 72px 100%;
    }
    .no-scrollbar::-webkit-scrollbar { width: 0; height: 0; }
  </style>
</head>
<body class="bg-background text-foreground antialiased">
  <div id="root"></div>
  <script type="text/babel">
    const REGION_DATA = __DATA_JSON__;
    const PROVINCE_CODES = __PROVINCE_JSON__;
    const GEO_URL = "https://geo.datav.aliyun.com/areas_v3/bound/";

    const iconPaths = {
      ShieldCheck: "M20 13c0 5-3.5 7.5-8 9-4.5-1.5-8-4-8-9V5l8-3 8 3v8Zm-11-1 2 2 4-4",
      Search: "m21 21-4.34-4.34M10.5 18a7.5 7.5 0 1 1 0-15 7.5 7.5 0 0 1 0 15Z",
      RotateCcw: "M3 12a9 9 0 1 0 3-6.7L3 8m0-5v5h5",
      MapPinned: "M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Zm-8 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
      ChevronRight: "m9 18 6-6-6-6",
      Building2: "M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18M6 12H4a2 2 0 0 0-2 2v8m16-10h2a2 2 0 0 1 2 2v8M10 6h4M10 10h4M10 14h4M10 18h4",
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
        cyan: "border-cyan-200/70 bg-cyan-50/80 text-cyan-800",
        severe: "border-rose-200 bg-rose-50 text-rose-700",
        watch: "border-amber-200 bg-amber-50 text-amber-700",
        steel: "border-slate-300/70 bg-white/65 text-slate-700",
      };
      return <span className={cn("inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium", tones[tone])}>{children}</span>;
    }
    function RiskBadge({ level }) {
      const tone = level === "严重" || level === "较重"
        ? "border-rose-200 bg-rose-50 text-rose-700"
        : "border-amber-200 bg-amber-50 text-amber-700";
      return (
        <span className={cn("inline-flex h-7 shrink-0 items-center justify-center whitespace-nowrap rounded-full border px-2.5 text-xs font-medium leading-none", tone)}>
          {level}
        </span>
      );
    }

    const RISK_ORDER = { "严重": 3, "较重": 2, "关注": 1, "无": 0 };
    function riskTone(level) {
      if (level === "严重" || level === "较重") return "severe";
      if (level === "关注") return "watch";
      return "neutral";
    }
    function aggregate(data, field) {
      const map = new Map();
      data.forEach((item) => {
        const key = item[field] || "未识别";
        const existing = map.get(key) || { name: key, value: 0, warningCount: 0, maxRisk: "无", items: [] };
        existing.value += 1;
        existing.warningCount += item.warningCount || 0;
        if (RISK_ORDER[item.riskLevel] > RISK_ORDER[existing.maxRisk]) existing.maxRisk = item.riskLevel;
        existing.items.push(item);
        map.set(key, existing);
      });
      return Array.from(map.values()).sort((a, b) => b.value - a.value);
    }
    function uniqueCount(data, field) {
      return new Set(data.map((item) => item[field]).filter(Boolean)).size;
    }
    function getGeoCode(state) {
      if (state.level === "country") return "100000";
      if (state.level === "province") return PROVINCE_CODES[state.province] || "100000";
      const cityItem = REGION_DATA.find((item) => item.province === state.province && item.city === state.city);
      return cityItem?.cityCode || PROVINCE_CODES[state.province] || "100000";
    }
    function getMapName(state) {
      if (state.level === "country") return "china";
      if (state.level === "province") return state.province;
      return state.city;
    }
    function getAggregateField(state) {
      if (state.level === "country") return "province";
      if (state.level === "province") return "city";
      return "district";
    }
    function filterByState(data, state) {
      return data.filter((item) => {
        if (state.province && item.province !== state.province) return false;
        if (state.city && item.city !== state.city) return false;
        if (state.district && item.district !== state.district) return false;
        return true;
      });
    }
    function regionOptions() {
      return Array.from(new Set(REGION_DATA.flatMap((item) => [item.province, item.city, item.district]))).filter(Boolean);
    }
    function findRegion(query) {
      const q = query.trim();
      if (!q) return null;
      const provinces = Array.from(new Set(REGION_DATA.map((item) => item.province)));
      const province = provinces.find((name) => name === q) || provinces.find((name) => name.includes(q));
      if (province) return { type: "province", province };
      const cityItem = REGION_DATA.find((item) => item.city === q) || REGION_DATA.find((item) => item.city.includes(q));
      if (cityItem) return { type: "city", province: cityItem.province, city: cityItem.city };
      const districtItem = REGION_DATA.find((item) => item.district === q) || REGION_DATA.find((item) => item.district.includes(q));
      if (districtItem) return { type: "district", province: districtItem.province, city: districtItem.city, district: districtItem.district };
      return null;
    }

    function RegionMap({ state, data, hovered, setHovered, onDrill, selectedCompany }) {
      const ref = React.useRef(null);
      const chartRef = React.useRef(null);
      const [loading, setLoading] = React.useState(true);
      const [error, setError] = React.useState("");
      const scoped = filterByState(data, state);
      const field = getAggregateField(state);
      const aggregated = aggregate(scoped, field);

      React.useEffect(() => {
        if (!ref.current || !window.echarts) return;
        const chart = chartRef.current || window.echarts.init(ref.current);
        chartRef.current = chart;
        let disposed = false;
        const code = getGeoCode(state);
        const mapName = getMapName(state);
        setLoading(true);
        setError("");
        fetch(`${GEO_URL}${code}_full.json`)
          .then((res) => {
            if (!res.ok) throw new Error("地图数据加载失败");
            return res.json();
          })
          .then((geoJson) => {
            if (disposed) return;
            window.echarts.registerMap(mapName, geoJson);
            const max = Math.max(1, ...aggregated.map((item) => item.value));
            chart.setOption({
              animationDurationUpdate: 260,
              tooltip: {
                trigger: "item",
                backgroundColor: "rgba(12, 20, 34, .86)",
                borderColor: "rgba(148, 163, 184, .22)",
                borderWidth: 1,
                padding: 12,
                textStyle: { color: "#e5edf6", fontSize: 13 },
                formatter: (params) => {
                  const row = aggregated.find((item) => item.name === params.name);
                  if (!row) return `${params.name}<br/>交易对手 0`;
                  return `<div style="font-weight:600;margin-bottom:6px">${params.name}</div><div>交易对手：${row.value}</div><div>预警数量：${row.warningCount}</div>`;
                }
              },
              visualMap: {
                show: false,
                min: 0,
                max,
                inRange: { color: ["#edf3f8", "#c8d9e8", "#8fabc1", "#486b87"] }
              },
              series: [{
                name: "交易对手",
                type: "map",
                map: mapName,
                roam: false,
                selectedMode: false,
                data: aggregated.map((item) => ({ name: item.name, value: item.value, warningCount: item.warningCount })),
                zoom: state.level === "country" ? 1.12 : 1,
                label: { show: false, color: "#22324a", fontSize: 11 },
                itemStyle: { borderColor: "#d7e2ec", borderWidth: 0.8, areaColor: "#eef4f8" },
                emphasis: {
                  label: { show: true, color: "#122033", fontWeight: 600 },
                  itemStyle: { areaColor: "#7fb5c5", borderColor: "#2d6b81", borderWidth: 1.2, shadowBlur: 12, shadowColor: "rgba(45,107,129,.16)" }
                }
              }]
            }, true);
            chart.off("mouseover");
            chart.off("mouseout");
            chart.off("click");
            chart.on("mouseover", (params) => setHovered(params.name));
            chart.on("mouseout", () => setHovered(""));
            chart.on("click", (params) => onDrill(params.name));
            setLoading(false);
          })
          .catch(() => {
            if (!disposed) {
              setError("地图数据暂未加载，仍可通过右侧区域列表查看归集结果。");
              setLoading(false);
            }
          });
        const resize = () => chart.resize();
        window.addEventListener("resize", resize);
        return () => {
          disposed = true;
          window.removeEventListener("resize", resize);
        };
      }, [state.level, state.province, state.city, data.length]);

      React.useEffect(() => {
        if (!chartRef.current || !selectedCompany) return;
        setHovered(selectedCompany.district);
      }, [selectedCompany]);

      return (
        <div className="relative h-full min-h-[620px] overflow-hidden rounded-xl border border-border map-shell">
          <div ref={ref} className="absolute inset-0" />
          {loading && <div className="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground">地图加载中...</div>}
          {error && <div className="absolute left-6 top-6 rounded-xl border border-border bg-card/90 px-4 py-3 text-sm text-muted-foreground shadow-panel">{error}</div>}
          {hovered && <div className="absolute bottom-5 left-5 rounded-xl border border-border bg-card/90 px-4 py-3 text-sm shadow-panel">当前悬浮：<span className="font-semibold">{hovered}</span></div>}
        </div>
      );
    }

    function App() {
      const [state, setState] = React.useState({ level: "country", province: "", city: "", district: "" });
      const [hovered, setHovered] = React.useState("");
      const [selectedCompany, setSelectedCompany] = React.useState(null);
      const [regionQuery, setRegionQuery] = React.useState("");
      const [searchHint, setSearchHint] = React.useState("");
      const scopedData = filterByState(REGION_DATA, state);
      const aggregateField = getAggregateField(state);
      const regionRows = aggregate(scopedData, aggregateField);
      const activeName = state.district || hovered || state.city || state.province || "全国";
      const activeItems = hovered ? scopedData.filter((item) => item[aggregateField] === hovered) : scopedData;

      function resetCountry() {
        setState({ level: "country", province: "", city: "", district: "" });
        setHovered("");
        setRegionQuery("");
        setSearchHint("");
      }
      function goBackOneLevel() {
        setSelectedCompany(null);
        setHovered("");
        if (state.district) {
          setState({ level: "city", province: state.province, city: state.city, district: "" });
          return;
        }
        if (state.level === "city") {
          setState({ level: "province", province: state.province, city: "", district: "" });
          return;
        }
        if (state.level === "province") {
          resetCountry();
        }
      }
      function drill(name) {
        if (state.level === "country") {
          if (!PROVINCE_CODES[name]) return;
          setState({ level: "province", province: name, city: "", district: "" });
        } else if (state.level === "province") {
          const city = REGION_DATA.find((item) => item.province === state.province && item.city === name);
          if (!city) return;
          setState({ level: "city", province: state.province, city: name, district: "" });
        } else {
          setState({ ...state, district: name });
        }
        setHovered("");
      }
      function locateCompany(item) {
        setSelectedCompany(item);
        setState({ level: "city", province: item.province, city: item.city, district: item.district });
        setHovered(item.district);
      }
      function submitRegionSearch(event) {
        event.preventDefault();
        const found = findRegion(regionQuery);
        if (!found) {
          setSearchHint("未找到匹配区域");
          return;
        }
        setSelectedCompany(null);
        if (found.type === "province") {
          setState({ level: "province", province: found.province, city: "", district: "" });
          setHovered("");
          setSearchHint(`已切换至 ${found.province}`);
        }
        if (found.type === "city") {
          setState({ level: "city", province: found.province, city: found.city, district: "" });
          setHovered("");
          setSearchHint(`已切换至 ${found.city}`);
        }
        if (found.type === "district") {
          setState({ level: "city", province: found.province, city: found.city, district: found.district });
          setHovered(found.district);
          setSearchHint(`已定位至 ${found.district}`);
        }
      }
      const stats = {
        total: scopedData.length,
        provinces: uniqueCount(scopedData, "province"),
        cities: uniqueCount(scopedData, "city"),
        warnings: scopedData.reduce((sum, item) => sum + (item.warningCount > 0 ? 1 : 0), 0),
      };

      return (
        <main className="min-h-screen surface-grid">
          <header className="sticky top-0 z-30 border-b border-border bg-background/82 backdrop-blur-xl">
            <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-5 px-6 py-4">
              <div className="flex items-center gap-4">
                <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-panel"><Icon name="ShieldCheck" className="h-5 w-5" /></div>
                <div>
                  <h1 className="text-xl font-semibold tracking-tight">贷后风险监控一览表</h1>
                  <p className="text-xs text-muted-foreground">区域一览表 · 交易对手归集下钻</p>
                </div>
              </div>
              <nav className="hidden items-center rounded-xl border border-border bg-card/85 p-1 text-sm text-muted-foreground shadow-panel lg:flex">
                {["首页", "区域一览表", "贷后分析", "项目维护"].map((item, index) => (
                  <button key={item} className={cn("rounded-lg px-3.5 py-2 transition hover:bg-muted/70", index === 1 && "bg-muted text-foreground shadow-sm")}>{item}</button>
                ))}
              </nav>
              <button onClick={resetCountry} className="inline-flex items-center gap-2 rounded-xl border border-border bg-card/85 px-3 py-2 text-sm text-muted-foreground shadow-panel"><Icon name="RotateCcw" className="h-4 w-4" />返回全国</button>
            </div>
          </header>

          <div className="mx-auto grid max-w-[1440px] gap-5 px-6 py-6">
            <Card className="grid gap-0 overflow-hidden lg:grid-cols-4">
              <div className="border-b border-border px-5 py-4 lg:border-b-0 lg:border-r"><p className="text-xs uppercase tracking-[.16em] text-muted-foreground">当前范围</p><p className="mt-2 text-xl font-semibold">{activeName}</p></div>
              <div className="border-b border-border px-5 py-4 lg:border-b-0 lg:border-r"><p className="text-xs uppercase tracking-[.16em] text-muted-foreground">交易对手</p><p className="mt-2 text-xl font-semibold tabular-nums">{stats.total}</p></div>
              <div className="border-b border-border px-5 py-4 lg:border-b-0 lg:border-r"><p className="text-xs uppercase tracking-[.16em] text-muted-foreground">覆盖区域</p><p className="mt-2 text-xl font-semibold">{stats.provinces} 省 / {stats.cities} 市</p></div>
              <div className="px-5 py-4"><p className="text-xs uppercase tracking-[.16em] text-muted-foreground">有预警主体</p><p className="mt-2 text-xl font-semibold tabular-nums">{stats.warnings}</p></div>
            </Card>

            <section className="grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)_360px]">
              <Card className="h-fit p-5">
                <h2 className="text-lg font-semibold">筛选区域</h2>
                <form onSubmit={submitRegionSearch} className="mt-5">
                  <label className="block">
                    <span className="text-xs text-muted-foreground">省 / 市 / 区县</span>
                    <div className="mt-2 flex items-center gap-2">
                      <div className="relative min-w-0 flex-1">
                        <Icon name="Search" className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                        <input list="region-suggestions" value={regionQuery} onChange={(e) => setRegionQuery(e.target.value)} className="h-9 w-full rounded-lg border border-border bg-background pl-9 pr-3 text-sm outline-none focus:border-cyan-300" placeholder="输入区域名称" />
                      </div>
                      <button className="h-9 rounded-lg border border-border bg-primary px-3 text-sm text-primary-foreground">确认</button>
                    </div>
                  </label>
                  <datalist id="region-suggestions">{regionOptions().map((name) => <option key={name} value={name} />)}</datalist>
                  {searchHint && <p className="mt-2 text-xs text-muted-foreground">{searchHint}</p>}
                </form>
              </Card>

              <Card className="overflow-hidden p-4">
                <div className="mb-4 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                  <div className="flex flex-wrap items-center gap-2 text-sm">
                    <button onClick={resetCountry} className="font-medium text-cyanline">全国</button>
                    {state.province && <><Icon name="ChevronRight" className="h-4 w-4 text-muted-foreground" /><button onClick={() => setState({ level: "province", province: state.province, city: "", district: "" })} className="font-medium text-cyanline">{state.province}</button></>}
                    {state.city && <><Icon name="ChevronRight" className="h-4 w-4 text-muted-foreground" /><button onClick={() => setState({ level: "city", province: state.province, city: state.city, district: "" })} className="font-medium text-cyanline">{state.city}</button></>}
                    {state.district && <><Icon name="ChevronRight" className="h-4 w-4 text-muted-foreground" /><span>{state.district}</span></>}
                  </div>
                </div>
                <RegionMap state={state} data={REGION_DATA} hovered={hovered} setHovered={setHovered} onDrill={drill} selectedCompany={selectedCompany} />
              </Card>

              <Card className="overflow-hidden">
                <div className="border-b border-border p-5">
                  <div className="flex items-center gap-2"><Icon name="MapPinned" className="h-5 w-5 text-cyanline" /><h2 className="text-lg font-semibold">区域概览</h2></div>
                  <p className="mt-2 text-sm text-muted-foreground">{activeName} · {scopedData.length} 个交易对手</p>
                </div>
                <div className="border-b border-border p-4">
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <p className="text-xs uppercase tracking-[.16em] text-muted-foreground">区域排行</p>
                    {(state.level !== "country" || state.district) && <button onClick={goBackOneLevel} className="rounded-lg border border-border bg-background px-3 py-1.5 text-xs text-muted-foreground transition hover:bg-muted">返回上一层</button>}
                  </div>
                  <div className="space-y-2">
                    {regionRows.slice(0, 6).map((row) => (
                      <button key={row.name} onMouseEnter={() => setHovered(row.name)} onMouseLeave={() => setHovered("")} onClick={() => drill(row.name)} className={cn("w-full rounded-xl border px-3 py-2 text-left text-sm transition hover:bg-muted/60", hovered === row.name ? "border-cyan-300 bg-cyan-50/70" : "border-border bg-background/65")}>
                        <div className="flex items-center justify-between gap-3"><span className="font-medium">{row.name}</span><span className="tabular-nums text-muted-foreground">{row.value}</span></div>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="max-h-[520px] overflow-auto p-4 no-scrollbar">
                  <p className="mb-3 text-xs uppercase tracking-[.16em] text-muted-foreground">交易对手列表</p>
                  <div className="space-y-3">
                    {activeItems.slice(0, 12).map((item) => (
                      <button key={item.companyName} onClick={() => locateCompany(item)} className={cn("w-full rounded-xl border p-3 text-left transition hover:border-cyan-300 hover:bg-muted/50", selectedCompany?.companyName === item.companyName ? "border-cyan-300 bg-cyan-50/70" : "border-border bg-background/70")}>
                        <div className="flex items-start justify-between gap-3"><p className="font-semibold leading-5">{item.companyName}</p>{item.riskLevel !== "无" && <RiskBadge level={item.riskLevel} />}</div>
                        <p className="mt-2 text-xs leading-5 text-muted-foreground">{item.province} / {item.city} / {item.district}</p>
                        <p className="mt-1 text-xs text-muted-foreground">预警 {item.warningCount} · {item.latestWarningTime || "暂无预警"}</p>
                      </button>
                    ))}
                  </div>
                </div>
              </Card>
            </section>
          </div>
        </main>
      );
    }

    ReactDOM.createRoot(document.getElementById("root")).render(<App />);
  </script>
</body>
</html>
"""
    html = html.replace("__DATA_JSON__", data_json).replace("__PROVINCE_JSON__", province_json)
    out = RUN_DIR / "region_overview.html"
    out.write_text(html, encoding="utf-8-sig")
    print(out)


if __name__ == "__main__":
    main()
