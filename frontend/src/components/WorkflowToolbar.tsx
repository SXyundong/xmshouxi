'use client';

import { useState } from 'react';
import {
  LogisticsWorkflowResponse,
  runLogisticsSalesWorkflow,
} from '@/services/api';

interface Props {
  department: string;
  compact?: boolean;
}

export default function WorkflowToolbar({ department, compact = false }: Props) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<LogisticsWorkflowResponse | null>(null);
  const [error, setError] = useState('');

  async function runWorkflow() {
    if (running) return;
    setRunning(true);
    setResult(null);
    setError('');
    try {
      setResult(await runLogisticsSalesWorkflow());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '工作流执行失败');
    } finally {
      setRunning(false);
    }
  }

  if (compact) {
    if (department !== 'logistics') return null;
    return (
      <div>
        <button
          type="button"
          onClick={runWorkflow}
          disabled={running}
          className="flex items-center gap-2 rounded-lg border border-emerald-200/15 bg-emerald-300/[0.07] px-3 py-2 text-[11px] text-emerald-100 disabled:opacity-50"
        >
          <span className={running ? 'animate-spin' : ''}>{running ? '◌' : '↻'}</span>
          {running ? '同步销量中' : '同步健腹轮销量'}
        </button>
        {result && <p className="mt-2 text-[10px] text-emerald-200/70">已写入 {result.range}</p>}
        {error && <p className="mt-2 text-[10px] leading-4 text-rose-200/70">{error}</p>}
      </div>
    );
  }

  return (
    <aside className="glass-strong hidden w-[286px] shrink-0 flex-col rounded-2xl xl:flex">
      <div className="border-b border-white/[0.07] px-5 py-5">
        <div className="flex items-center gap-2 text-xs font-medium text-white/80">
          <svg className="h-4 w-4 text-emerald-200/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
            <path d="M12 3v4m0 10v4M3 12h4m10 0h4M5.6 5.6l2.8 2.8m7.2 7.2 2.8 2.8m0-12.8-2.8 2.8m-7.2 7.2-2.8 2.8" strokeLinecap="round" />
          </svg>
          部门工具
        </div>
        <p className="mt-1.5 text-[10px] leading-4 text-white/30">运行已配置的自动化工作流</p>
      </div>

      <div className="flex-1 overflow-y-auto p-3">
        {department === 'logistics' ? (
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-cyan-200/15 bg-cyan-300/[0.07] text-cyan-100">
                <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 7h11v10H4V7Zm11 3h3l2 3v4h-5v-7ZM7 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm10 0a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" /></svg>
              </div>
              <span className="rounded-full bg-emerald-300/[0.07] px-2 py-1 text-[9px] uppercase tracking-wider text-emerald-200/60">Ready</span>
            </div>
            <h3 className="mt-4 text-xs font-medium leading-5 text-white/85">健腹轮销量写入备货表</h3>
            <p className="mt-1.5 text-[10px] leading-5 text-white/35">从领星获取 SKU 70017-3 的滚动销量，并写入备货逻辑看板。</p>
            <div className="mt-3 grid grid-cols-4 gap-1">
              {[3, 7, 15, 30].map((days) => (
                <div key={days} className="rounded-md bg-white/[0.035] py-1.5 text-center text-[9px] text-white/35">{days} 天</div>
              ))}
            </div>
            <button
              type="button"
              onClick={runWorkflow}
              disabled={running}
              className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-200 px-3 py-2.5 text-[11px] font-medium text-[#12201c] transition hover:bg-emerald-100 disabled:cursor-wait disabled:opacity-50"
            >
              <svg className={`h-3.5 w-3.5 ${running ? 'animate-spin' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v6h-6" strokeLinecap="round" strokeLinejoin="round" /></svg>
              {running ? '正在获取并写入…' : '运行工作流'}
            </button>
          </div>
        ) : (
          <div className="mt-12 text-center"><div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.07] bg-white/[0.025] text-white/20">＋</div><p className="mt-3 text-[11px] text-white/30">暂无已配置工具</p></div>
        )}

        {result && (
          <div className="mt-3 rounded-xl border border-emerald-200/15 bg-emerald-300/[0.055] p-3">
            <div className="text-[10px] font-medium text-emerald-100/80">写入成功 · {result.range}</div>
            <div className="mt-2 grid grid-cols-4 gap-1">
              {([3, 7, 15, 30] as const).map((days) => (
                <div key={days} className="rounded-md bg-black/15 px-1 py-2 text-center"><div className="text-xs tabular-nums text-white/85">{result.sales[`days_${days}`]}</div><div className="mt-0.5 text-[8px] text-white/30">{days} 天</div></div>
              ))}
            </div>
          </div>
        )}
        {error && <div className="mt-3 rounded-xl border border-rose-300/15 bg-rose-300/[0.055] p-3 text-[10px] leading-5 text-rose-100/70">{error}</div>}
      </div>

      <div className="border-t border-white/[0.07] p-4 text-[9px] leading-4 text-white/20">工作流运行前会校验 SKU、商品名称和目标单元格，异常时不会写入文件。</div>
    </aside>
  );
}
