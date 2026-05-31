import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# === 1. Navbar: merge status + update time into compact element ===
old_navbar = '''                  <Badge tone="ok">数据源正常</Badge>
                  <button className="hidden items-center gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm text-muted-foreground sm:inline-flex">
                    <Icon name="Clock3" className="h-4 w-4" />
                    更新于 22:30
                  </button>'''
new_navbar = '''                  <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:inline-flex">
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                    数据源正常 · 更新于 22:30
                  </span>'''
content = content.replace(old_navbar, new_navbar)

# === 2. Stats bar: weaken 更新时间 tone ===
content = content.replace(
    '{ label: "更新时间", value: "22:30", tone: "text-slate-900" }',
    '{ label: "更新时间", value: "22:30", tone: "text-muted-foreground" }'
)

# === 3. Stats bar: enlarge numbers ===
content = content.replace(
    '<p className={cn("mt-1 text-xl font-semibold tabular-nums", item.tone)}>{item.value}</p>',
    '<p className={cn("mt-1 text-2xl font-bold tabular-nums tracking-tight", item.tone)}>{item.value}</p>'
)

# === 4. Workbench header: weaken subtitle ===
old_sub = '''                        <p className="mt-2 text-sm text-muted-foreground">仅展示严重及较重事件；关注类进入下方近三个月风险库。</p>'''
new_sub = '''                        <p className="mt-1 text-xs text-muted-foreground/70">数据源：司法公开渠道 / 评级公告 / Choice / iFinD / 资讯源</p>'''
content = content.replace(old_sub, new_sub)

# === 5. Event items: restructure to 3-line, sources at bottom ===
old_event = '''                          <div className="px-5 py-3.5">
                            <div className="flex items-start gap-2.5">
                              <Badge tone={tone}>{item.level}</Badge>
                              <p className="flex-1 text-sm font-medium leading-snug">{item.title}</p>
                              <span className="shrink-0 text-xs text-muted-foreground whitespace-nowrap">{item.time}</span>
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                              <span className="font-medium text-foreground">{item.entity}</span>
                              <span className="text-muted-foreground/40">·</span>
                              <span>{item.role}</span>
                              <span className="text-muted-foreground/40">·</span>
                              <span className="truncate">{item.project}</span>
                            </div>
                            <div className="mt-1.5 flex flex-wrap items-center gap-2">
                              <p className="text-xs text-muted-foreground flex-1 truncate">{item.impact}</p>
                              <div className="flex shrink-0 flex-wrap gap-1">
                                {item.sources.slice(0, 2).map((source) => <Badge key={source}>{source}</Badge>)}{item.sources.length > 2 && <Badge>+{item.sources.length - 2}</Badge>}
                              </div>
                            </div>
                          </div>'''

new_event = '''                          <div className="px-5 py-3.5">
                            <div className="flex items-start gap-2.5">
                              <Badge tone={tone}>{item.level}</Badge>
                              <p className={cn("flex-1 text-sm leading-snug", active ? "font-semibold" : "font-medium")}>{item.title}</p>
                              <span className="shrink-0 text-xs text-muted-foreground whitespace-nowrap">{item.time}</span>
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                              <span className="font-medium text-foreground">{item.entity}</span>
                              <span className="text-muted-foreground/30">·</span>
                              <span>{item.role}</span>
                              <span className="text-muted-foreground/30">·</span>
                              <span className="truncate">{item.project}</span>
                            </div>
                            <div className="mt-2 space-y-1.5">
                              <p className="text-xs leading-relaxed text-muted-foreground">{item.impact}</p>
                              <div className="flex flex-wrap gap-1">
                                {item.sources.slice(0, 2).map((source) => <Badge key={source}>{source}</Badge>)}{item.sources.length > 2 && <Badge>+{item.sources.length - 2}</Badge>}
                              </div>
                            </div>
                          </div>'''

content = content.replace(old_event, new_event)

# === 6. Selected state: thicker red bar ===
content = content.replace(
    '{active && <span className="absolute bottom-3 left-0 top-3 w-[3px] rounded-r-full bg-red-600" />}',
    '{active && <span className="absolute bottom-3 left-0 top-3 w-1 rounded-r-full bg-red-600/80" />}'
)

# === 7. Evidence chain: better subtitle ===
old_ev_sub = '''                      <p className="mt-2 text-sm text-muted-foreground">按事件发现、数据交叉验证和外部来源形成审计轨迹。</p>'''
new_ev_sub = '''                      <p className="mt-1 text-xs text-muted-foreground/70">事件发现 · 交叉验证 · 外部佐证</p>'''
content = content.replace(old_ev_sub, new_ev_sub)

# === 8. Add custom scrollbar CSS ===
scrollbar_css = '''
      .custom-scrollbar::-webkit-scrollbar { width: 4px; }
      .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
      .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.25); border-radius: 4px; }
      .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(148,163,184,0.40); }
      .dark .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(71,85,105,0.35); }
      .dark .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(71,85,105,0.50); }'''
content = content.replace('      @media (prefers-reduced-motion: reduce) {', scrollbar_css + '\n' + '      @media (prefers-reduced-motion: reduce) {')

# === 9. Add custom-scrollbar class to workbench list and evidence panel ===
content = content.replace(
    '<div className="min-h-0 flex-1 overflow-y-auto">',
    '<div className="min-h-0 flex-1 overflow-y-auto custom-scrollbar">'
)
# Evidence panel scroll
content = content.replace(
    '<div className="mt-5 min-h-0 flex-1 overflow-y-auto pr-1">',
    '<div className="mt-5 min-h-0 flex-1 overflow-y-auto pr-1 custom-scrollbar">'
)

# === 10. More muted timeline colors ===
# Replace severe timeline dot bg-red-600 -> bg-red-500/80, heavier bg-orange-500 -> bg-orange-400/80
# We need to fix both the evidence panel and add lighter dots
content = content.replace(
    'selected.level === "严重" ? "bg-red-600" : selected.level === "较重" ? "bg-orange-500" : "bg-emerald-600"',
    'selected.level === "严重" ? "bg-red-500" : selected.level === "较重" ? "bg-orange-400" : "bg-emerald-500"'
)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("All UI refinements applied successfully")
