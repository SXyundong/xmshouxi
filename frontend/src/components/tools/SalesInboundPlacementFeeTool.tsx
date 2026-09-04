'use client';

import { useRef, useState } from 'react';
import { downloadInboundPlacementFeeWorkbook } from '@/services/api';

export default function SalesInboundPlacementFeeTool() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState('');

  async function calculate() {
    if (!file || running) return;
    setRunning(true); setError('');
    try {
      const blob = await downloadInboundPlacementFeeWorkbook(file);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url; link.download = `${file.name.replace(/\.xlsx$/i, '')}_测算结果.xlsx`;
      link.click(); URL.revokeObjectURL(url);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '入库配置费测算失败');
    } finally { setRunning(false); }
  }

  return <div className="rounded-2xl border border-white/[0.08] bg-white/[0.025] p-3">
    <div className="flex items-start gap-3"><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-emerald-200/15 bg-emerald-300/[0.07] text-emerald-100">$</div><div className="min-w-0"><div className="text-[11px] font-medium text-white/85">入库配置费测算</div><p className="mt-1 text-[9px] leading-4 text-white/35">上传美国站入库配置费表，计算重量、尺寸分段及两种费用。</p></div></div>
    <input ref={inputRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="hidden" onChange={(event) => { setFile(event.target.files?.[0] || null); setError(''); }} />
    <button type="button" onClick={() => inputRef.current?.click()} className="mt-3 w-full rounded-xl border border-dashed border-white/[0.15] bg-white/[0.035] px-3 py-2.5 text-left text-[10px] text-white/55 transition hover:bg-white/[0.07]">{file ? `已选择：${file.name}` : '选择 .xlsx 入库配置费表'}</button>
    <button type="button" disabled={!file || running} onClick={() => void calculate()} className="mt-2 w-full rounded-xl bg-emerald-200 px-3 py-2.5 text-[10px] font-medium text-[#12201c] transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-40">{running ? '正在计算并生成 Excel…' : '计算并下载结果'}</button>
    {error && <div className="mt-2 rounded-lg bg-rose-300/[0.08] px-2.5 py-2 text-[9px] leading-4 text-rose-100/80">{error}</div>}
  </div>;
}
