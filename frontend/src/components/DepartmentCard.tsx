import Link from 'next/link';
import type { Department } from '@/services/departments';

const accents: Record<string, string> = {
  sales: 'from-emerald-300/20 to-teal-400/5 text-emerald-200', inventory: 'from-sky-300/20 to-blue-400/5 text-sky-200',
  logistics: 'from-cyan-300/20 to-slate-400/5 text-cyan-200', product: 'from-violet-300/20 to-purple-400/5 text-violet-200',
  ads: 'from-fuchsia-300/20 to-pink-400/5 text-fuchsia-200', operation: 'from-amber-300/20 to-orange-400/5 text-amber-200',
  finance: 'from-lime-300/20 to-emerald-400/5 text-lime-200', design: 'from-rose-300/20 to-violet-400/5 text-rose-200',
  hr: 'from-indigo-300/20 to-sky-400/5 text-indigo-200',
};

export default function DepartmentCard({ dept, index }: { dept: Department; index: number }) {
  return (
    <Link
      href={`/${dept.slug}`}
      style={{ animationDelay: `${index * 45}ms` }}
      className="group glass animate-fade-up relative overflow-hidden rounded-2xl p-5 transition duration-300 hover:-translate-y-1 hover:border-white/20 hover:bg-white/[0.075] hover:shadow-2xl hover:shadow-black/30"
    >
      <div className={`absolute inset-x-0 top-0 h-px bg-gradient-to-r ${accents[dept.slug]}`} />
      <div className="flex items-start justify-between">
        <div className={`flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br ${accents[dept.slug]} ring-1 ring-inset ring-white/10`}><span className="text-sm font-semibold">{dept.name.slice(0, 1)}</span></div>
        <svg className="h-4 w-4 text-white/20 transition duration-300 group-hover:translate-x-0.5 group-hover:text-white/70" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><path d="M5 12h14m-6-6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </div>
      <h2 className="mt-6 text-[15px] font-medium tracking-wide text-white">{dept.name}部门</h2>
      <p className="mt-1.5 text-sm leading-6 text-[#9298a6]">{dept.description}</p>
      <div className="mt-5 flex items-center gap-2 border-t border-white/[0.07] pt-4"><span className="h-1.5 w-1.5 rounded-full bg-emerald-300 shadow-[0_0_8px_rgba(110,231,183,.8)]" /><span className="text-[11px] tracking-wide text-white/40">{dept.agentName} · 在线</span></div>
    </Link>
  );
}
