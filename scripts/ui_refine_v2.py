import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# ============================================================
# 1. BACKGROUND: Remove grid, keep clean gradient
# ============================================================
old_surface = '''      .surface-grid {
        background-image:
          linear-gradient(to right, rgba(64, 92, 124, 0.055) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(64, 92, 124, 0.055) 1px, transparent 1px),
          linear-gradient(180deg, rgba(245, 248, 251, 0.96), rgba(236, 243, 249, 0.92));
        background-size: 32px 32px, 32px 32px, auto;
      }

      .dark .surface-grid {
        background-image:
          linear-gradient(to right, rgba(148, 163, 184, 0.06) 1px, transparent 1px),
          linear-gradient(to bottom, rgba(148, 163, 184, 0.06) 1px, transparent 1px),
          linear-gradient(180deg, rgba(17, 24, 39, 0.98), rgba(15, 23, 42, 0.94));
      }'''

new_surface = '''      .surface-grid {
        background: linear-gradient(180deg, #F3F7FB 0%, #F7F9FC 260px);
      }

      .dark .surface-grid {
        background: linear-gradient(180deg, #141E2E 0%, #111827 260px);
      }'''

content = content.replace(old_surface, new_surface)

# Also fix the body background
content = content.replace(
    'background: #f5f8fb;',
    'background: #F7F9FC;'
)

# ============================================================
# 2. NAVBAR: Glassmorphism light
# ============================================================
old_header = '<header className="sticky top-0 z-30 border-b border-border/70 bg-background/82 backdrop-blur-xl">'
new_header = '<header className="sticky top-0 z-30 border-b border-[#E2E8F0]/80 bg-white/75 backdrop-blur-[12px]">'
content = content.replace(old_header, new_header)

# Lighter shadow on nav tabs
content = content.replace(
    'rounded-xl border border-border/70 bg-card/90 p-1 text-sm text-muted-foreground shadow-soft lg:flex',
    'rounded-xl border border-[#E2E8F0]/70 bg-white/70 p-1 text-sm text-muted-foreground lg:flex'
)

# ============================================================
# 3. STATS BAR: Replace 5 cards with summary bar
# ============================================================
old_stats = '''              <section className="grid gap-3 rounded-2xl border border-border/70 bg-card/78 p-3 shadow-soft backdrop-blur md:grid-cols-5">
                {homeStats.map((item) => (
                  <div key={item.label} className="rounded-xl border border-border/60 bg-white/68 px-4 py-3">
                    <p className="text-xs text-muted-foreground">{item.label}</p>
                    <p className={cn("mt-1 text-2xl font-bold tabular-nums tracking-tight", item.tone)}>{item.value}</p>
                  </div>
                ))}
              </section>'''

new_stats = '''              <section className="flex items-center gap-4 rounded-[14px] border border-[#E5EAF1] bg-white/70 px-5 py-3 shadow-sm">
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
              </section>'''

content = content.replace(old_stats, new_stats)

# ============================================================
# 4. BADGE: Refined pill styles
# ============================================================
old_badge_severe = 'severe: "border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/35 dark:text-red-300"'
new_badge_severe = 'severe: "border-[#FECDD3] bg-[#FFF1F2] text-[#BE123C] dark:border-red-900/60 dark:bg-red-950/35 dark:text-red-300"'

old_badge_high = 'high: "border-orange-200 bg-orange-50 text-orange-700 dark:border-orange-900/60 dark:bg-orange-950/30 dark:text-orange-300"'
new_badge_high = 'high: "border-[#FED7AA] bg-[#FFF7ED] text-[#C2410C] dark:border-orange-900/60 dark:bg-orange-950/30 dark:text-orange-300"'

old_badge_watch = 'watch: "border-yellow-200 bg-yellow-50 text-yellow-700 dark:border-yellow-900/60 dark:bg-yellow-950/25 dark:text-yellow-300"'
new_badge_watch = 'watch: "border-[#FDE68A] bg-[#FFFBEB] text-[#A16207] dark:border-yellow-900/60 dark:bg-yellow-950/25 dark:text-yellow-300"'

content = content.replace(old_badge_severe, new_badge_severe)
content = content.replace(old_badge_high, new_badge_high)
content = content.replace(old_badge_watch, new_badge_watch)

# Make badge text slightly smaller
content = content.replace(
    'className={cn("inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2.5 py-1 text-xs font-medium leading-none", tones[tone])}',
    'className={cn("inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium leading-[18px]", tones[tone])}'
)

# ============================================================
# 5. EVENT LIST: Lighter dividers
# ============================================================
content = content.replace(
    'className={cn("relative block w-full border-b border-border/60 text-left transition", active ? "bg-red-50/55" : "hover:bg-white/55")}',
    'className={cn("relative block w-full border-b border-[#EEF2F7] text-left transition", active ? "bg-[#FFF5F5]" : "hover:bg-slate-50/70")}'
)

# ============================================================
# 6. SCROLLBAR: Refined colors
# ============================================================
old_scroll_css = '''      .custom-scrollbar::-webkit-scrollbar { width: 4px; }
      .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
      .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(148,163,184,0.25); border-radius: 4px; }
      .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: rgba(148,163,184,0.40); }
      .dark .custom-scrollbar::-webkit-scrollbar-thumb { background: rgba(71,85,105,0.35); }'''

new_scroll_css = '''      .custom-scrollbar::-webkit-scrollbar { width: 4px; }
      .custom-scrollbar::-webkit-scrollbar-track { background: transparent; }
      .custom-scrollbar::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 4px; }
      .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #94A3B8; }
      .dark .custom-scrollbar::-webkit-scrollbar-thumb { background: #475569; }
      .dark .custom-scrollbar::-webkit-scrollbar-thumb:hover { background: #64748B; }'''

content = content.replace(old_scroll_css, new_scroll_css)

# ============================================================
# 7. REMOVE Navbar duplicate status (now in summary bar)
# ============================================================
old_nav_status = '''                  <span className="hidden items-center gap-1.5 text-xs text-muted-foreground sm:inline-flex">
                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-emerald-500"></span>
                    数据源正常 · 更新于 22:30
                  </span>
'''
content = content.replace(old_nav_status, '')

# ============================================================
# 8. Card border-radius: increase from rounded-2xl to rounded-[16px]
# ============================================================
# The Card component uses rounded-2xl (16px in Tailwind). Keep as is - it's already 16px.
# For the workbench card, use rounded-[16px] explicitly.
content = content.replace(
    '<Card className="flex h-[820px] overflow-hidden shadow-cabin">',
    '<Card className="flex h-[820px] overflow-hidden shadow-cabin rounded-[16px]">'
)
content = content.replace(
    '<Card className="flex h-[820px] flex-col overflow-hidden p-5 shadow-cabin">',
    '<Card className="flex h-[820px] flex-col overflow-hidden p-5 shadow-cabin rounded-[16px]">'
)

# ============================================================
# 9. Navbar separator dots thinner
# ============================================================
content = content.replace(
    '<span className="text-muted-foreground/30">·</span>',
    '<span className="text-slate-300 select-none">·</span>'
)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("All refinements applied successfully")
