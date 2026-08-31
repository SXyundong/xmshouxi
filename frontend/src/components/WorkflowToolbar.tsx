'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  executeLogisticsSalesWorkflow,
  waitForLogisticsSalesExecute,
  getLogisticsSalesPreviewStatus,
  LogisticsWorkflowJob,
  LogisticsWorkflowPreview,
  LogisticsWorkflowResult,
  LogisticsWorkflowExport,
  LogisticsWorkflowWarning,
  startLogisticsSalesExport,
  getLogisticsSalesExportStatus,
  startLogisticsSalesPreview,
} from '@/services/api';

interface Props { department: string; compact?: boolean; }
type WorkflowPhase = 'idle' | 'previewing' | 'executing' | 'exporting';
type WarningGroupCode = 'duplicate_identity' | 'product_not_found' | 'dimension_validation' | 'platform_scope_limited' | 'other';

const DEFAULT_PANEL_WIDTH = 360;
const MIN_PANEL_WIDTH = 300;
const MAX_PANEL_WIDTH = 650;
const warningGroupMeta: Record<WarningGroupCode, { label: string; tone: string; icon: string }> = {
  duplicate_identity: { label: '重复商品', tone: 'amber', icon: '↔' },
  product_not_found: { label: '未找到唯一商品', tone: 'rose', icon: '!' },
  dimension_validation: { label: '字段映射差异', tone: 'yellow', icon: '△' },
  platform_scope_limited: { label: '数据范围说明', tone: 'cyan', icon: 'i' },
  other: { label: '其他提示', tone: 'slate', icon: '·' },
};

function warningGroupCode(code: string): WarningGroupCode { return code in warningGroupMeta ? code as WarningGroupCode : 'other'; }
function warningSku(warning: LogisticsWorkflowWarning) { return warning.identity?.sku || warning.identity?.lingxing_sku || ''; }
function warningMatches(warning: LogisticsWorkflowWarning, search: string) {
  if (!search.trim()) return true;
  const needle = search.trim().toLowerCase();
  return [warning.message, warningSku(warning), warning.rows.join('、')].some((value) => value.toLowerCase().includes(needle));
}

function WarningGroups({ warnings }: { warnings: LogisticsWorkflowWarning[] }) {
  const [openGroup, setOpenGroup] = useState<WarningGroupCode | null>(null);
  const [search, setSearch] = useState('');
  const [visibleCount, setVisibleCount] = useState<Record<string, number>>({});
  const grouped = useMemo(() => {
    const result = new Map<WarningGroupCode, LogisticsWorkflowWarning[]>();
    warnings.forEach((warning) => { const group = warningGroupCode(warning.code); result.set(group, [...(result.get(group) || []), warning]); });
    return Array.from(result.entries());
  }, [warnings]);
  if (!warnings.length) return null;

  return <div className="mt-4 border-t border-white/[0.07] pt-3">
    <div className="flex items-center justify-between gap-2"><div><div className="text-[10px] font-medium text-white/65">提示与异常</div><div className="mt-0.5 text-[9px] text-white/25">按类型收起，点击查看 SKU 和行号</div></div><span className="rounded-full bg-white/[0.06] px-2 py-1 text-[9px] tabular-nums text-white/45">{warnings.length}</span></div>
    <div className="relative mt-3"><svg className="pointer-events-none absolute left-2.5 top-2.5 h-3 w-3 text-white/25" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4" strokeLinecap="round"/></svg><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索 SKU、行号或提示" className="h-8 w-full rounded-lg border border-white/[0.07] bg-black/15 pl-8 pr-3 text-[10px] text-white/75 outline-none placeholder:text-white/20 focus:border-white/15" /></div>
    <div className="mt-2 space-y-1.5">{grouped.map(([code, groupWarnings]) => {
      const meta = warningGroupMeta[code];
      const filtered = groupWarnings.filter((warning) => warningMatches(warning, search));
      const isOpen = openGroup === code;
      const limit = visibleCount[code] || 20;
      return <div key={code} className="overflow-hidden rounded-xl border border-white/[0.07] bg-white/[0.02]">
        <button type="button" onClick={() => setOpenGroup(isOpen ? null : code)} className="flex w-full items-center gap-2 px-3 py-2.5 text-left transition hover:bg-white/[0.035]" aria-expanded={isOpen}><span className={`flex h-5 w-5 items-center justify-center rounded-md text-[10px] ${meta.tone === 'rose' ? 'bg-rose-300/10 text-rose-200' : meta.tone === 'cyan' ? 'bg-cyan-300/10 text-cyan-200' : 'bg-amber-300/10 text-amber-200'}`}>{meta.icon}</span><span className="min-w-0 flex-1 text-[10px] text-white/65">{meta.label}</span><span className="text-[9px] tabular-nums text-white/30">{filtered.length}/{groupWarnings.length}</span><span className={`text-[10px] text-white/30 transition-transform ${isOpen ? 'rotate-180' : ''}`}>⌄</span></button>
        {isOpen && <div className="border-t border-white/[0.06] px-2.5 pb-2.5 pt-2">{!filtered.length ? <div className="py-3 text-center text-[9px] text-white/25">没有匹配的提示</div> : <><div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">{filtered.slice(0, limit).map((warning, index) => <div key={`${warning.code}-${warning.rows.join('-')}-${index}`} className="rounded-lg border border-white/[0.06] bg-black/10 px-2.5 py-2"><div className="flex items-start gap-1.5 text-[9px] leading-4 text-white/55"><span className="mt-0.5 text-amber-200/65">{meta.icon}</span><span>{warning.message}</span></div>{(warning.rows.length || warningSku(warning)) ? <div className="mt-1 text-[8px] leading-4 text-white/25">{warning.rows.length ? `行号：${warning.rows.join('、')}` : '未定位行'}{warningSku(warning) ? ` · ${warningSku(warning)}` : ''}</div> : null}</div>)}</div>{filtered.length > limit && <button type="button" onClick={() => setVisibleCount((current) => ({ ...current, [code]: limit + 20 }))} className="mt-2 w-full rounded-lg border border-white/[0.07] bg-white/[0.025] py-1.5 text-[9px] text-white/35 transition hover:bg-white/[0.06] hover:text-white/60">加载更多（剩余 {filtered.length - limit} 条）</button>}</>}</div>}
      </div>;
    })}</div>
  </div>;
}

function StatusBadge({ phase, job, preview, result, exportResult, error }: { phase: WorkflowPhase; job: LogisticsWorkflowJob | null; preview: LogisticsWorkflowPreview | null; result: LogisticsWorkflowResult | null; exportResult: LogisticsWorkflowExport | null; error: string }) {
  if (error) return <span className="rounded-full bg-rose-300/10 px-2 py-1 text-[9px] text-rose-200/80">失败</span>;
  if (phase === 'executing') return <span className="rounded-full bg-emerald-300/10 px-2 py-1 text-[9px] text-emerald-200/80">写入中</span>;
  if (phase === 'exporting') return <span className="rounded-full bg-cyan-300/10 px-2 py-1 text-[9px] text-cyan-200/80">生成中</span>;
  if (phase === 'previewing' && job?.status === 'queued') return <span className="rounded-full bg-cyan-300/10 px-2 py-1 text-[9px] text-cyan-200/80">排队中</span>;
  if (phase === 'previewing') return <span className="rounded-full bg-cyan-300/10 px-2 py-1 text-[9px] text-cyan-200/80">同步中</span>;
  if (preview) return <span className="rounded-full bg-amber-300/10 px-2 py-1 text-[9px] text-amber-100/80">待确认</span>;
  if (result) return <span className="rounded-full bg-emerald-300/10 px-2 py-1 text-[9px] text-emerald-200/80">已完成</span>;
  if (exportResult) return <span className="rounded-full bg-emerald-300/10 px-2 py-1 text-[9px] text-emerald-200/80">可下载</span>;
  return <span className="rounded-full bg-white/[0.06] px-2 py-1 text-[9px] text-white/35">未运行</span>;
}

function ToolSummary({ phase, job, preview, result, exportResult, error }: { phase: WorkflowPhase; job: LogisticsWorkflowJob | null; preview: LogisticsWorkflowPreview | null; result: LogisticsWorkflowResult | null; exportResult: LogisticsWorkflowExport | null; error: string }) {
  if (phase === 'previewing') return <span className="text-[9px] tabular-nums text-cyan-100/50">{job?.progress || 0}%</span>;
  if (phase === 'exporting') return <span className="text-[9px] tabular-nums text-cyan-100/50">{job?.progress || 0}%</span>;
  if (preview) return <span className="text-[9px] text-white/35">{preview.matched_rows} 可写入 · {preview.missing_rows} 未匹配</span>;
  if (result) return <span className="text-[9px] text-emerald-200/55">已更新 {result.updated_rows} 行</span>;
  if (exportResult) return <span className="text-[9px] text-emerald-200/55">已生成 {exportResult.matched_rows} 行</span>;
  if (error) return <span className="truncate text-[9px] text-rose-200/60">{error}</span>;
  return <span className="text-[9px] text-white/25">60 天销量同步 · AJ:AM</span>;
}

export default function WorkflowToolbar({ department, compact = false }: Props) {
  const [phase, setPhase] = useState<WorkflowPhase>('idle');
  const [preview, setPreview] = useState<LogisticsWorkflowPreview | null>(null);
  const [job, setJob] = useState<LogisticsWorkflowJob | null>(null);
  const [result, setResult] = useState<LogisticsWorkflowResult | null>(null);
  const [exportResult, setExportResult] = useState<LogisticsWorkflowExport | null>(null);
  const [error, setError] = useState('');
  const [expanded, setExpanded] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [panelWidth, setPanelWidth] = useState(DEFAULT_PANEL_WIDTH);
  const [forceRefresh, setForceRefresh] = useState(false);
  const resizing = useRef(false);
  const busy = phase !== 'idle';
  const canShowTool = department === 'logistics';
  const maxPanelWidth = typeof window === 'undefined' ? MAX_PANEL_WIDTH : Math.min(MAX_PANEL_WIDTH, Math.max(420, Math.round(window.innerWidth * 0.45)));

  useEffect(() => { const stored = Number(window.localStorage.getItem('department-tools-width')); if (Number.isFinite(stored)) setPanelWidth(Math.min(maxPanelWidth, Math.max(MIN_PANEL_WIDTH, stored))); }, [maxPanelWidth]);
  useEffect(() => { window.localStorage.setItem('department-tools-width', String(panelWidth)); }, [panelWidth]);
  useEffect(() => {
    function move(event: PointerEvent) { if (!resizing.current) return; const next = window.innerWidth - event.clientX; setPanelWidth(Math.min(maxPanelWidth, Math.max(MIN_PANEL_WIDTH, next))); }
    function stop() { resizing.current = false; document.body.style.cursor = ''; document.body.style.userSelect = ''; }
    window.addEventListener('pointermove', move); window.addEventListener('pointerup', stop);
    return () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', stop); };
  }, [maxPanelWidth]);

  function beginResize(event: React.PointerEvent<HTMLDivElement>) { event.preventDefault(); resizing.current = true; document.body.style.cursor = 'col-resize'; document.body.style.userSelect = 'none'; }
  function resetWidth() { setPanelWidth(DEFAULT_PANEL_WIDTH); }

  async function createPreview(force = false) {
    if (busy) return;
    if (force && !window.confirm('将跳过PostgreSQL缓存，重新查询表格中的全部商品。领星调用可能持续一段时间，是否继续？')) return;
    setForceRefresh(force); setPhase('previewing'); setExpanded(true); setPreview(null); setResult(null); setError('');
    try {
      const started = await startLogisticsSalesPreview(force); setJob(started); let current = started;
      while (current.status !== 'complete' && current.status !== 'failed') { await new Promise((resolve) => setTimeout(resolve, 1800)); current = await getLogisticsSalesPreviewStatus(started.job_id); setJob(current); }
      if (current.status === 'failed') throw new Error(current.error || '物流销量预览失败');
      if (!current.preview) throw new Error('预览任务已完成，但没有返回预览数据');
      setPreview(current.preview);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '预览生成失败'); } finally { setPhase('idle'); }
  }

  async function createExport(force = false) {
    if (busy) return;
    if (force && !window.confirm('将跳过 PostgreSQL 缓存，重新从领星同步商品销量。任务可能持续一段时间，是否继续？')) return;
    setForceRefresh(force); setPhase('exporting'); setExpanded(true); setPreview(null); setResult(null); setExportResult(null); setError('');
    try {
      const started = await startLogisticsSalesExport(force); setJob(started); let current = started;
      while (current.status !== 'complete' && current.status !== 'failed') { await new Promise((resolve) => setTimeout(resolve, 1800)); current = await getLogisticsSalesExportStatus(started.job_id); setJob(current); }
      if (current.status === 'failed') throw new Error(current.error || '物流销量 Excel 导出失败');
      if (!current.export) throw new Error('Excel 任务已完成，但没有返回下载信息');
      setExportResult(current.export);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Excel 导出失败'); } finally { setPhase('idle'); }
  }

  async function confirmWrite() {
    if (busy || !preview?.can_execute) return;
    setPhase('executing'); setExpanded(true); setError('');
    try { const started = await executeLogisticsSalesWorkflow(preview.preview_id); const response = await waitForLogisticsSalesExecute(started.job_id); setResult(response); setPreview(null); } catch (reason) { setError(reason instanceof Error ? reason.message : '写入失败'); } finally { setPhase('idle'); }
  }

  function ToolCard({ drawer = false }: { drawer?: boolean }) {
    if (!canShowTool) return <div className="flex h-full items-center justify-center text-center"><div><div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.07] bg-white/[0.025] text-white/20">＋</div><p className="mt-3 text-[11px] text-white/30">暂无已配置工具</p></div></div>;
    return <div className={`rounded-2xl border border-white/[0.08] bg-white/[0.025] ${drawer ? 'p-4' : 'p-3'}`}>
      <button type="button" onClick={() => setExpanded((current) => !current)} className="flex w-full items-center gap-3 text-left" aria-expanded={expanded}><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-cyan-200/15 bg-cyan-300/[0.07] text-cyan-100"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 7h11v10H4V7Zm11 3h3l2 3v4h-5v-7ZM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm10 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" /></svg></div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="truncate text-[11px] font-medium text-white/85">备货逻辑看板 · 销量导出</span><StatusBadge phase={phase} job={job} preview={preview} result={result} exportResult={exportResult} error={error} /></div><div className="mt-1 flex min-w-0 items-center gap-2"><ToolSummary phase={phase} job={job} preview={preview} result={result} exportResult={exportResult} error={error} /></div></div><span className={`shrink-0 text-sm text-white/30 transition-transform ${expanded ? 'rotate-180' : ''}`}>⌄</span></button>
      {expanded && <div className="mt-4 border-t border-white/[0.07] pt-4"><div className="flex items-start justify-between gap-3"><div><h3 className="text-[11px] font-medium leading-5 text-white/80">备货逻辑看板销量导出</h3><p className="mt-1 text-[9px] leading-4 text-white/30">从 PostgreSQL 读取商品与销量，按 A–F 匹配并生成临时 Excel；未找到的行保留为空并提示。</p></div><span className="rounded-full bg-cyan-300/[0.07] px-2 py-1 text-[8px] uppercase tracking-wider text-cyan-100/55">PostgreSQL</span></div><div className="mt-3 grid grid-cols-4 gap-1">{[3, 7, 15, 30].map((days) => <div key={days} className="rounded-md bg-white/[0.035] py-1.5 text-center text-[9px] text-white/35">{days} 天</div>)}</div>
        {(phase === 'previewing' || phase === 'exporting') && <div className="mt-3 rounded-xl border border-cyan-200/15 bg-cyan-300/[0.045] p-3"><div className="flex items-center justify-between gap-2 text-[9px] text-cyan-100/70"><span className="truncate">{job?.message || '正在准备任务…'}</span><span className="shrink-0 tabular-nums">{job?.progress || 0}%</span></div><div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.08]"><div className="h-full rounded-full bg-cyan-200/70 transition-all" style={{ width: `${job?.progress || 0}%` }} /></div></div>}
        {!preview && !result && !exportResult && <div className="mt-4 space-y-2"><button type="button" onClick={() => createExport(false)} disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl border border-white/[0.09] bg-white/[0.055] px-3 py-2.5 text-[10px] font-medium text-white/75 transition hover:bg-white/[0.08] disabled:cursor-wait disabled:opacity-50"><svg className={`h-3.5 w-3.5 ${phase === 'exporting' && !forceRefresh ? 'animate-spin' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3v12m0 0 4-4m-4 4-4-4M5 21h14" strokeLinecap="round" strokeLinejoin="round" /></svg>{phase === 'exporting' && !forceRefresh ? '正在生成 Excel…' : '生成 Excel 并下载'}</button><button type="button" onClick={() => createExport(true)} disabled={busy} className="flex w-full items-center justify-center gap-2 rounded-xl border border-cyan-200/15 bg-cyan-300/[0.06] px-3 py-2.5 text-[10px] font-medium text-cyan-100/75 transition hover:bg-cyan-300/[0.1] disabled:cursor-wait disabled:opacity-50"><svg className={`h-3.5 w-3.5 ${phase === 'exporting' && forceRefresh ? 'animate-spin' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v6h-6" strokeLinecap="round" strokeLinejoin="round" /></svg>{phase === 'exporting' && forceRefresh ? '正在从领星更新…' : '跳过缓存，更新后导出'}</button><p className="px-1 text-[9px] leading-4 text-white/25">数据来自 PostgreSQL；文件只临时保留，生成后点击下载，不写入 Railway 磁盘。</p></div>}
        {preview && <div className="mt-3 rounded-xl border border-amber-200/15 bg-amber-300/[0.045] p-3"><div className="text-[10px] font-medium text-amber-100/80">等待确认 · {preview.workbook}</div><div className="mt-2 grid grid-cols-3 gap-1"><div className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-white/85">{preview.matched_rows}</div><div className="mt-0.5 text-[8px] text-white/30">可写入</div></div><div className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-amber-100/80">{preview.missing_rows}</div><div className="mt-0.5 text-[8px] text-white/30">未匹配</div></div><div className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-amber-100/80">{preview.duplicate_groups}</div><div className="mt-0.5 text-[8px] text-white/30">重复组</div></div></div><WarningGroups warnings={preview.warnings} /><button type="button" onClick={confirmWrite} disabled={busy || !preview.can_execute} className="mt-3 flex w-full items-center justify-center rounded-xl bg-emerald-200 px-3 py-2.5 text-[10px] font-medium text-[#12201c] transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-40">{phase === 'executing' ? '正在写入并校验…' : `确认写入 ${preview.matched_rows} 行`}</button></div>}
        {exportResult && <div className="mt-3 rounded-xl border border-emerald-200/15 bg-emerald-300/[0.055] p-3"><div className="text-[10px] font-medium text-emerald-100/80">Excel 已生成 · 临时下载</div><p className="mt-1.5 break-all text-[9px] leading-4 text-white/40">{exportResult.filename} · 数据来自 PostgreSQL，不写入服务器文件。</p><div className="mt-2 grid grid-cols-3 gap-1"><div className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-white/85">{exportResult.matched_rows}</div><div className="mt-0.5 text-[8px] text-white/30">已生成</div></div><div className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-amber-100/80">{exportResult.missing_rows}</div><div className="mt-0.5 text-[8px] text-white/30">未匹配</div></div><div className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-amber-100/80">{exportResult.duplicate_groups}</div><div className="mt-0.5 text-[8px] text-white/30">重复组</div></div></div><a href={exportResult.download_url} download={exportResult.filename} className="mt-3 flex w-full items-center justify-center rounded-xl bg-emerald-200 px-3 py-2.5 text-[10px] font-medium text-[#12201c] transition hover:bg-emerald-100">下载 Excel</a><WarningGroups warnings={exportResult.warnings} /></div>}
        {result && <div className="mt-3 rounded-xl border border-emerald-200/15 bg-emerald-300/[0.055] p-3"><div className="text-[10px] font-medium text-emerald-100/80">写入成功 · {result.target_columns}</div><p className="mt-1.5 text-[9px] leading-4 text-white/40">已更新 {result.updated_rows} 行，跳过 {result.skipped_rows} 行，并完成写后校验。</p><WarningGroups warnings={result.warnings} /></div>}
        {error && <div className="mt-3 rounded-xl border border-rose-300/15 bg-rose-300/[0.055] p-3 text-[10px] leading-5 text-rose-100/70">{error}</div>}
      </div>}
    </div>;
  }

  if (compact) {
    if (!canShowTool) return null;
    return <div className="workflow-light relative z-30"><button type="button" onClick={() => setMobileOpen(true)} className="flex w-full items-center gap-2 rounded-xl border border-white/[0.08] bg-white/[0.035] px-3 py-2 text-left"><span className="flex h-6 w-6 items-center justify-center rounded-lg bg-cyan-300/[0.08] text-cyan-100">↗</span><span className="min-w-0 flex-1"><span className="block text-[10px] font-medium text-white/70">工具库</span><span className="mt-0.5 block truncate text-[9px] text-white/30">{preview ? `销量同步待确认 · ${preview.matched_rows} 行` : phase === 'previewing' || phase === 'exporting' ? `销量同步运行中 · ${job?.progress || 0}%` : result ? `销量同步已完成 · ${result.updated_rows} 行` : exportResult ? `Excel 已生成 · ${exportResult.matched_rows} 行，可下载` : '销量同步 · 点击打开工具栏'}</span></span><span className="text-[10px] text-white/30">→</span></button>{mobileOpen && <><button type="button" aria-label="关闭工具栏" onClick={() => setMobileOpen(false)} className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm" /><div className="workflow-light fixed inset-x-3 bottom-3 top-20 z-50 overflow-y-auto rounded-2xl border border-white/[0.1] bg-white/95 p-3 shadow-2xl backdrop-blur-2xl"><div className="mb-3 flex items-center justify-between px-1"><div className="text-xs font-medium text-white/75">工具库</div><button type="button" onClick={() => setMobileOpen(false)} className="rounded-lg px-2 py-1 text-sm text-white/35 hover:bg-white/[0.06] hover:text-white/70">×</button></div><ToolCard drawer /></div></>}</div>;
  }

  return <aside className="workflow-light relative hidden min-w-0 shrink-0 flex-col rounded-2xl xl:flex" style={{ width: panelWidth }}><div role="separator" aria-label="拖动调整工具栏宽度" onPointerDown={beginResize} onDoubleClick={resetWidth} className="group absolute -left-1.5 inset-y-0 z-10 flex w-3 cursor-col-resize items-center justify-center"><span className="h-10 w-0.5 rounded-full bg-white/10 transition group-hover:h-16 group-hover:bg-emerald-200/60" /></div><div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-4"><div className="flex items-center gap-2 text-xs font-medium text-white/80"><svg className="h-4 w-4 text-emerald-200/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m7.2 7.2 2.8 2.8m0-12.8-2.8 2.8m-7.2 7.2-2.8 2.8" strokeLinecap="round" /></svg>工具库</div><span className="rounded-full bg-white/[0.05] px-2 py-1 text-[9px] text-white/30">{busy ? '1 个运行中' : '1 个可用'}</span></div><div className="flex-1 overflow-y-auto p-3"><ToolCard /></div><div className="border-t border-white/[0.07] px-4 py-3 text-[9px] leading-4 text-white/20">可拖动左侧边缘调整宽度 · 双击恢复默认。现在仅生成临时 Excel 下载，不写入服务器路径。</div></aside>;
}
