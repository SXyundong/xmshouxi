'use client';

import Link from 'next/link';
import { FormEvent, useEffect, useRef, useState } from 'react';
import { sendChat } from '@/services/api';
import { departments } from '@/services/departments';
import WorkflowToolbar from '@/components/WorkflowToolbar';

interface Message { role: 'user' | 'assistant'; content: string; }
interface Props { department: string; name: string; emoji: string; description: string; }

const suggestions: Record<string, string[]> = {
  sales: ['分析昨天的销售表现', '找出销量增长最快的 SKU', '生成本周销售摘要'],
  inventory: ['查看当前库存风险', '列出需要补货的 SKU', '分析库存周转情况'],
  logistics: ['检查异常物流订单', '汇总今日配送情况', '分析物流时效'],
  product: ['推荐近期选品方向', '评估新品市场机会', '分析潜力品类'],
  ads: ['分析广告投放表现', '给出预算优化建议', '诊断低效广告组'],
  operation: ['制定本周运营计划', '复盘近期活动效果', '设计提升转化方案'],
  finance: ['生成经营数据摘要', '分析近期成本变化', '查看利润表现'],
  design: ['规划新品视觉方向', '生成主图创意建议', '整理活动素材需求'],
  hr: ['起草岗位招聘要求', '整理候选人评估维度', '规划本月招聘任务'],
};

export default function DepartmentChat({ department, name, description }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  async function submit(text: string) {
    const content = text.trim();
    if (!content || loading) return;
    setMessages((prev) => [...prev, { role: 'user', content }]);
    setInput('');
    setLoading(true);
    try {
      const res = await sendChat(department, content);
      setMessages((prev) => [...prev, { role: 'assistant', content: res.answer }]);
    } catch {
      setMessages((prev) => [...prev, { role: 'assistant', content: '暂时无法连接服务，请检查后端运行状态后重试。' }]);
    } finally { setLoading(false); }
  }

  function handleSend(e: FormEvent<HTMLFormElement>) { e.preventDefault(); void submit(input); }

  return (
    <main className="flex h-screen overflow-hidden bg-[#090a0d] p-0 md:p-3">
      <aside className="glass-strong hidden w-[248px] shrink-0 flex-col rounded-2xl md:flex">
        <Link href="/" className="flex items-center gap-3 border-b border-white/[0.07] px-4 py-5">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-200/20 bg-emerald-300/10"><svg className="h-4 w-4 text-emerald-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M8 5.5 12 3l4 2.5v5L12 13l-4-2.5v-5Z"/><path d="m4 13 4 2.5v5L4 18v-5Zm12 2.5 4-2.5v5l-4 2.5v-5Z"/></svg></div>
          <div><div className="text-xs font-semibold tracking-wide text-white">Nexus Commerce</div><div className="mt-0.5 text-[9px] uppercase tracking-[.18em] text-white/30">Agent Workspace</div></div>
        </Link>
        <div className="px-3 py-4"><div className="px-2 pb-2 text-[10px] font-medium uppercase tracking-[.16em] text-white/25">智能部门</div><nav className="space-y-1">{departments.map((dept)=><Link key={dept.slug} href={`/${dept.slug}`} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-xs transition ${dept.slug===department?'border border-white/10 bg-white/[0.08] text-white shadow-lg shadow-black/10':'border border-transparent text-white/45 hover:bg-white/[0.04] hover:text-white/80'}`}><span className={`flex h-6 w-6 items-center justify-center rounded-md text-[10px] ${dept.slug===department?'bg-emerald-300/15 text-emerald-200':'bg-white/[0.05] text-white/40'}`}>{dept.name.slice(0,1)}</span><span className="flex-1">{dept.name}部门</span>{dept.slug===department&&<span className="h-1 w-1 rounded-full bg-emerald-300"/>}</Link>)}</nav></div>
        <div className="mt-auto p-3"><div className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-3"><div className="flex items-center gap-2 text-[11px] text-white/55"><span className="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_7px_rgba(110,231,183,.8)]"/>系统运行正常</div><p className="mt-1.5 text-[10px] leading-4 text-white/25">所有 Agent 服务均已连接</p></div></div>
      </aside>

      <section className="relative flex min-w-0 flex-1 flex-col">
        <header className="flex h-[68px] items-center justify-between border-b border-white/[0.07] px-4 sm:px-7">
          <div className="flex items-center gap-3"><Link href="/" className="mr-1 text-white/45 md:hidden">←</Link><div className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-gradient-to-br from-emerald-300/15 to-teal-400/5 text-xs font-semibold text-emerald-200">{name.slice(0,1)}</div><div><h1 className="text-sm font-medium text-white">{name}</h1><p className="mt-0.5 text-[10px] text-white/35">{description}</p></div></div>
          <div className="flex items-center gap-2"><button title="清空对话" onClick={()=>setMessages([])} className="rounded-lg border border-white/[0.07] bg-white/[0.025] p-2 text-white/35 transition hover:bg-white/[0.06] hover:text-white/70"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M4 7h16m-10 4v6m4-6v6M9 7l1-3h4l1 3m3 0-1 14H7L6 7" strokeLinecap="round" strokeLinejoin="round"/></svg></button><div className="hidden rounded-full border border-emerald-300/10 bg-emerald-300/[0.06] px-2.5 py-1 text-[10px] text-emerald-200/70 sm:block">● 在线</div></div>
        </header>

        <div className="border-b border-white/[0.06] px-4 py-2 xl:hidden"><WorkflowToolbar department={department} compact /></div>

        <div ref={listRef} className="flex-1 overflow-y-auto px-4 sm:px-8">
          <div className="mx-auto flex min-h-full max-w-3xl flex-col pb-6">
            {messages.length===0 ? <div className="my-auto py-12"><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl border border-emerald-200/15 bg-emerald-300/[0.07] shadow-[0_0_45px_rgba(52,211,153,.08)]"><svg className="h-5 w-5 text-emerald-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 3 9.8 8.8 4 11l5.8 2.2L12 19l2.2-5.8L20 11l-5.8-2.2L12 3Z"/></svg></div><h2 className="mt-5 text-center text-xl font-medium tracking-tight text-white">今天想从哪里开始？</h2><p className="mx-auto mt-2 max-w-md text-center text-sm leading-6 text-white/35">我是{name}，可以协助你处理{description}相关工作。</p><div className="mx-auto mt-8 grid max-w-xl gap-2 sm:grid-cols-3">{(suggestions[department]||[]).map(item=><button key={item} onClick={()=>void submit(item)} className="rounded-xl border border-white/[0.08] bg-white/[0.025] px-3 py-3 text-left text-xs leading-5 text-white/55 transition hover:-translate-y-0.5 hover:border-white/15 hover:bg-white/[0.055] hover:text-white/90">{item}<span className="mt-2 block text-white/20">↗</span></button>)}</div></div> : <div className="space-y-7 py-8">{messages.map((m,i)=><div key={i} className={`flex gap-3 ${m.role==='user'?'justify-end':'justify-start'}`}>{m.role==='assistant'&&<div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-emerald-200/10 bg-emerald-300/[0.07] text-[10px] text-emerald-200">AI</div>}<div className={m.role==='user'?'max-w-[82%] rounded-2xl rounded-tr-md border border-white/10 bg-white/[0.085] px-4 py-3 text-sm leading-7 text-white/90':'max-w-[85%] whitespace-pre-wrap py-1 text-sm leading-7 text-white/75'}>{m.content}</div></div>)}{loading&&<div className="flex items-center gap-3"><div className="flex h-7 w-7 items-center justify-center rounded-lg border border-emerald-200/10 bg-emerald-300/[0.07] text-[10px] text-emerald-200">AI</div><div className="flex gap-1 py-2"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/25" /><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/25" style={{animationDelay:'0.15s'}} /><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white/25" style={{animationDelay:'0.3s'}} /></div></div>}</div>}
          </div>
        </div>

        <div className="px-4 pb-4 sm:px-8 sm:pb-6"><form onSubmit={handleSend} className="glass mx-auto max-w-3xl rounded-2xl p-2 shadow-2xl shadow-black/30"><textarea rows={1} value={input} onChange={(e)=>setInput(e.target.value)} onKeyDown={(e)=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();void submit(input);}}} placeholder={`向${name}发送消息…`} className="max-h-36 min-h-[48px] w-full resize-none bg-transparent px-3 py-3 text-sm leading-6 text-white outline-none placeholder:text-white/25"/><div className="flex items-center justify-between px-2 pb-1"><span className="hidden text-[10px] text-white/20 sm:block">Enter 发送 · Shift + Enter 换行</span><div className="ml-auto flex items-center gap-2"><span className="text-[10px] text-white/20">AI 生成内容仅供参考</span><button type="submit" disabled={loading||!input.trim()} className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-200 text-[#12201c] transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-25"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m5 12 7-7 7 7M12 5v14" strokeLinecap="round" strokeLinejoin="round"/></svg></button></div></div></form></div>
      </section>
      <WorkflowToolbar department={department} />
    </main>
  );
}
