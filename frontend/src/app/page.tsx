import DepartmentCard from '@/components/DepartmentCard';
import { departments } from '@/services/departments';

export default function Home() {
  return (
    <main className="relative min-h-screen overflow-hidden px-5 py-6 sm:px-8 lg:px-12">
      <nav className="mx-auto flex max-w-6xl items-center justify-between">
        <div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-xl border border-emerald-200/20 bg-emerald-300/10 shadow-[0_0_30px_rgba(110,231,183,.08)]"><svg className="h-5 w-5 text-emerald-200" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M8 5.5 12 3l4 2.5v5L12 13l-4-2.5v-5Z"/><path d="m4 13 4 2.5v5L4 18v-5Zm12 2.5 4-2.5v5l-4 2.5v-5Z"/></svg></div><div><div className="text-sm font-semibold tracking-wide text-white">Nexus Commerce</div><div className="text-[10px] uppercase tracking-[0.22em] text-white/35">Agent Workspace</div></div></div>
        <div className="glass hidden items-center gap-2 rounded-full px-3 py-2 text-xs text-white/50 sm:flex"><span className="h-1.5 w-1.5 rounded-full bg-emerald-300" />9 个智能部门已连接</div>
      </nav>
      <section className="mx-auto max-w-6xl pb-20 pt-20 sm:pt-28">
        <div className="max-w-3xl"><div className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.035] px-3 py-1.5 text-[11px] tracking-wide text-white/50 backdrop-blur-xl"><span className="text-emerald-200">✦</span> AI 驱动的企业协作中枢</div><h1 className="text-balance text-4xl font-medium leading-[1.15] tracking-[-0.035em] text-white sm:text-6xl">让每个部门，都拥有自己的<span className="bg-gradient-to-r from-emerald-200 via-teal-100 to-violet-200 bg-clip-text text-transparent"> 智能协作伙伴</span></h1><p className="mt-6 max-w-2xl text-base leading-7 text-[#9298a6] sm:text-lg">连接销售、库存、运营与创意团队。选择一个业务部门，开始分析数据、制定策略并推动工作落地。</p></div>
        <div className="mt-14 flex items-end justify-between border-b border-white/[0.08] pb-4"><div><h2 className="text-sm font-medium text-white/90">部门工作区</h2><p className="mt-1 text-xs text-white/35">选择专业 Agent 开始对话</p></div><span className="text-xs tabular-nums text-white/25">09 / 09 ACTIVE</span></div>
        <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">{departments.map((dept,index)=><DepartmentCard key={dept.slug} dept={dept} index={index}/>)}</div>
      </section>
      <footer className="mx-auto flex max-w-6xl items-center justify-between border-t border-white/[0.06] py-6 text-[11px] text-white/25"><span>© 2026 Nexus Commerce</span><span>Secure enterprise workspace</span></footer>
    </main>
  );
}
