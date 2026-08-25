'use client';

import { useState } from 'react';
import {
  executeLogisticsSalesWorkflow,
  getLogisticsSalesPreviewStatus,
  LogisticsWorkflowJob,
  LogisticsWorkflowPreview,
  LogisticsWorkflowResult,
  LogisticsWorkflowWarning,
  startLogisticsSalesPreview,
} from '@/services/api';

interface Props {
  department: string;
  compact?: boolean;
}

function WarningList({ warnings }: { warnings: LogisticsWorkflowWarning[] }) {
  if (!warnings.length) return null;
  return (
    <div className="mt-3 max-h-52 space-y-2 overflow-y-auto pr-1">
      {warnings.map((warning, index) => (
        <div
          key={`${warning.code}-${warning.rows.join('-')}-${index}`}
          className="rounded-lg border border-amber-200/10 bg-amber-300/[0.045] px-2.5 py-2"
        >
          <div className="flex items-start gap-1.5 text-[9px] leading-4 text-amber-100/70">
            <span className="mt-0.5 text-amber-300/70">△</span>
            <span>{warning.message}</span>
          </div>
          {!!warning.rows.length && (
            <div className="mt-1 text-[8px] text-white/30">
              行号：{warning.rows.join('、')}
              {warning.identity?.sku ? ` · ${warning.identity.sku}` : ''}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function WorkflowToolbar({ department, compact = false }: Props) {
  const [phase, setPhase] = useState<'idle' | 'previewing' | 'executing'>('idle');
  const [preview, setPreview] = useState<LogisticsWorkflowPreview | null>(null);
  const [job, setJob] = useState<LogisticsWorkflowJob | null>(null);
  const [result, setResult] = useState<LogisticsWorkflowResult | null>(null);
  const [error, setError] = useState('');

  const busy = phase !== 'idle';

  async function createPreview() {
    if (busy) return;
    setPhase('previewing');
    setPreview(null);
    setResult(null);
    setError('');
    try {
      const started = await startLogisticsSalesPreview();
      setJob(started);
      let current = started;
      while (current.status !== 'complete' && current.status !== 'failed') {
        await new Promise((resolve) => setTimeout(resolve, 1800));
        current = await getLogisticsSalesPreviewStatus(started.job_id);
        setJob(current);
      }
      if (current.status === 'failed') throw new Error(current.error || '物流销量预览失败');
      if (!current.preview) throw new Error('预览任务已完成，但没有返回预览数据');
      setPreview(current.preview);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '预览生成失败');
    } finally {
      setPhase('idle');
    }
  }

  async function confirmWrite() {
    if (busy || !preview?.can_execute) return;
    setPhase('executing');
    setError('');
    try {
      const response = await executeLogisticsSalesWorkflow(preview.preview_id);
      setResult(response);
      setPreview(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '写入失败');
    } finally {
      setPhase('idle');
    }
  }

  if (compact) {
    if (department !== 'logistics') return null;
    return (
      <div className="space-y-2">
        <button
          type="button"
          onClick={createPreview}
          disabled={busy}
          className="flex items-center gap-2 rounded-lg border border-emerald-200/15 bg-emerald-300/[0.07] px-3 py-2 text-[11px] text-emerald-100 disabled:opacity-50"
        >
          <span className={phase === 'previewing' ? 'animate-spin' : ''}>↻</span>
          {phase === 'previewing' ? '核对全部商品中' : '预览全部销量更新'}
        </button>
        {preview?.can_execute && (
          <button
            type="button"
            onClick={confirmWrite}
            disabled={busy}
            className="rounded-lg bg-emerald-200 px-3 py-2 text-[10px] font-medium text-[#12201c] disabled:opacity-50"
          >
            {phase === 'executing' ? '写入中…' : `确认写入 ${preview.matched_rows} 行`}
          </button>
        )}
        {result && (
          <p className="text-[10px] text-emerald-200/70">已写入 {result.updated_rows} 行</p>
        )}
        {error && <p className="text-[10px] leading-4 text-rose-200/70">{error}</p>}
      </div>
    );
  }

  return (
    <aside className="glass-strong hidden w-[300px] shrink-0 flex-col rounded-2xl xl:flex">
      <div className="border-b border-white/[0.07] px-5 py-5">
        <div className="flex items-center gap-2 text-xs font-medium text-white/80">
          <svg className="h-4 w-4 text-emerald-200/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m7.2 7.2 2.8 2.8m0-12.8-2.8 2.8m-7.2 7.2-2.8 2.8" strokeLinecap="round" />
          </svg>
          部门工具
        </div>
        <p className="mt-1.5 text-[10px] leading-4 text-white/30">先预览，再确认写入本地测试表</p>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {department === 'logistics' ? (
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-200/15 bg-cyan-300/[0.07] text-cyan-100">
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 7h11v10H4V7Zm11 3h3l2 3v4h-5v-7ZM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm10 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" /></svg>
              </div>
              <span className="rounded-full bg-cyan-300/[0.07] px-2 py-1 text-[9px] uppercase tracking-wider text-cyan-100/60">Local test</span>
            </div>
            <h3 className="mt-4 text-xs font-medium leading-5 text-white/85">全商品滚动销量同步</h3>
            <p className="mt-1.5 text-[10px] leading-5 text-white/35">按 A–F 完整匹配商品，重复行写入相同销量；未找到的行保持不变。</p>
            <div className="mt-3 grid grid-cols-4 gap-1">
              {[3, 7, 15, 30].map((days) => (
                <div key={days} className="rounded-md bg-white/[0.035] py-1.5 text-center text-[9px] text-white/35">{days} 天</div>
              ))}
            </div>
            <button
              type="button"
              onClick={createPreview}
              disabled={busy}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-white/[0.09] bg-white/[0.055] px-3 py-2.5 text-[11px] font-medium text-white/75 transition hover:bg-white/[0.08] disabled:cursor-wait disabled:opacity-50"
            >
              <svg className={`h-3.5 w-3.5 ${phase === 'previewing' ? 'animate-spin' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v6h-6" strokeLinecap="round" strokeLinejoin="round" /></svg>
              {phase === 'previewing' ? '正在查询并核对…' : '生成写入预览'}
            </button>
          </div>
        ) : (
          <div className="mt-12 text-center"><div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.07] bg-white/[0.025] text-white/20">＋</div><p className="mt-3 text-[11px] text-white/30">暂无已配置工具</p></div>
        )}

        {job && job.status !== 'complete' && job.status !== 'failed' && (
          <div className="mt-3 rounded-xl border border-cyan-200/15 bg-cyan-300/[0.045] p-3">
            <div className="flex items-center justify-between text-[10px] text-cyan-100/80"><span>{job.message}</span><span className="tabular-nums">{job.progress}%</span></div>
            <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/[0.08]"><div className="h-full rounded-full bg-cyan-200/70 transition-all" style={{ width: `${job.progress}%` }} /></div>
          </div>
        )}

        {preview && (
          <div className="mt-3 rounded-xl border border-cyan-200/15 bg-cyan-300/[0.045] p-3">
            <div className="text-[10px] font-medium text-cyan-100/80">等待确认 · {preview.workbook}</div>
            <div className="mt-2 grid grid-cols-3 gap-1">
              <div className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-white/85">{preview.matched_rows}</div><div className="mt-0.5 text-[8px] text-white/30">可写入</div></div>
              <div className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-amber-100/80">{preview.missing_rows}</div><div className="mt-0.5 text-[8px] text-white/30">未匹配</div></div>
              <div className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-amber-100/80">{preview.duplicate_groups}</div><div className="mt-0.5 text-[8px] text-white/30">重复组</div></div>
            </div>
            <WarningList warnings={preview.warnings} />
            <button
              type="button"
              onClick={confirmWrite}
              disabled={busy || !preview.can_execute}
              className="mt-3 flex w-full items-center justify-center rounded-xl bg-emerald-200 px-3 py-2.5 text-[11px] font-medium text-[#12201c] transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {phase === 'executing' ? '正在写入并校验…' : `确认写入 ${preview.matched_rows} 行`}
            </button>
          </div>
        )}

        {result && (
          <div className="mt-3 rounded-xl border border-emerald-200/15 bg-emerald-300/[0.055] p-3">
            <div className="text-[10px] font-medium text-emerald-100/80">写入成功 · {result.target_columns}</div>
            <p className="mt-1.5 text-[9px] leading-4 text-white/40">已更新 {result.updated_rows} 行，跳过 {result.skipped_rows} 行，并完成写后校验。</p>
            <WarningList warnings={result.warnings} />
          </div>
        )}
        {error && <div className="mt-3 rounded-xl border border-rose-300/15 bg-rose-300/[0.055] p-3 text-[10px] leading-5 text-rose-100/70">{error}</div>}
      </div>

      <div className="border-t border-white/[0.07] p-4 text-[9px] leading-4 text-white/20">网络路径写入已关闭。预览后若 A–F 或文件内容发生变化，系统会拒绝执行并要求重新预览。</div>
    </aside>
  );
}
