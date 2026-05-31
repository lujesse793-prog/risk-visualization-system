with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# === 1. Remove summary bar ===
old_summary = '''              <section className="flex items-center gap-4 rounded-[14px] border border-[#E5EAF1] bg-white/70 px-5 py-3 shadow-sm">
                <span className="text-sm text-slate-700">监控主体 <b className="font-semibold tabular-nums text-slate-900">{appAlerts.length}</b></span>
                <span className="text-slate-300 select-none">·</span>
                <span className="text-sm text-slate-700">近 7 日风险 <b className="font-semibold tabular-nums text-slate-900">{workbenchAlerts.length}</b></span>
                <span className="text-slate-300 select-none">·</span>
                <span className="text-sm text-slate-700">严重 <b className="font-semibold tabular-nums text-red-600">{severeWorkbenchCount}</b></span>
                <span className="text-slate-300 select-none">·</span>
                <span className="text-sm text-slate-700">较重 <b className="font-semibold tabular-nums text-orange-600">{highWorkbenchCount}</b></span>
                <span className="ml-auto flex items-center gap-2 text-xs text-slate-400">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                  数据正常 · 更新于 22:30
                </span>
              </section>

'''
content = content.replace(old_summary, '')

# === 2. Rework workbench header with inline stats ===
old_header = '''                  <div className="shrink-0 border-b border-border/70 bg-white/46 p-5">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                      <div>
                        <div className="flex flex-wrap items-center gap-3">
                          <h2 className="w-full text-xl font-semibold sm:w-auto">重要舆情工作台｜近 7 天重大风险</h2>
                          <Badge tone="severe">严重 {severeWorkbenchCount}</Badge>
                          <Badge tone="high">较重 {highWorkbenchCount}</Badge>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground/70">数据源：司法公开渠道 / 评级公告 / Choice / iFinD / 资讯源</p>
                      </div>
                    </div>
                  </div>'''

new_header = '''                  <div className="shrink-0 border-b border-[#EEF2F7] bg-white/50 p-5">
                    <div className="flex items-start justify-between gap-4">
                      <div className="min-w-0">
                        <h2 className="text-xl font-semibold tracking-tight text-slate-900">重要舆情工作台｜近 7 天重大风险</h2>
                        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] leading-relaxed text-[#64748B]">
                          <span>数据源：司法公开渠道 / 评级公告 / Choice / iFinD / 资讯源</span>
                          <span className="text-slate-300 select-none">·</span>
                          <span>监控主体 <b className="font-semibold tabular-nums text-slate-700">{appAlerts.length}</b></span>
                          <span className="text-slate-300 select-none">·</span>
                          <span>近 7 日风险 <b className="font-semibold tabular-nums text-slate-700">{workbenchAlerts.length}</b></span>
                          <span className="text-slate-300 select-none">·</span>
                          <span>严重 <b className="font-semibold tabular-nums text-red-600">{severeWorkbenchCount}</b></span>
                          <span className="text-slate-300 select-none">·</span>
                          <span>较重 <b className="font-semibold tabular-nums text-orange-600">{highWorkbenchCount}</b></span>
                        </div>
                      </div>
                      <div className="shrink-0 flex items-center gap-1.5 text-xs text-[#94A3B8] pt-1">
                        <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                        数据正常 · 22:30
                      </div>
                    </div>
                  </div>'''

content = content.replace(old_header, new_header)

# === 3. Remove the homeStats array (no longer needed) ===
old_home_stats = '''        const homeStats = [
          { label: "监控主体数", value: appAlerts.length, tone: "text-slate-900" },
          { label: "近 7 日风险", value: workbenchAlerts.length, tone: "text-slate-900" },
          { label: "严重事件", value: severeWorkbenchCount, tone: "text-red-700" },
          { label: "较重事件", value: highWorkbenchCount, tone: "text-orange-700" },
          { label: "更新时间", value: "22:30", tone: "text-muted-foreground" },
        ];
'''
content = content.replace(old_home_stats, '')

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done")
