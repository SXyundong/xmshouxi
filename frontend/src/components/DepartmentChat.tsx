'use client';

import Link from 'next/link';
import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import {
  Conversation,
  ConversationMessage,
  CurrentUser,
  createConversation,
  generateAigcVideoPrompt,
  getConversation,
  getCurrentUser,
  listConversations,
  sendConversationMessage,
} from '@/services/api';
import { departments } from '@/services/departments';
import WorkflowToolbar from '@/components/WorkflowToolbar';

interface Props { department: string; name: string; emoji: string; description: string; }
interface PendingImage { file: File; url: string; }

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

function redirectToLogin() {
  if (typeof window !== 'undefined') {
    window.location.href = `/auth/login?return_to=${encodeURIComponent(window.location.pathname)}`;
  }
}

export default function DepartmentChat({ department, name, description }: Props) {
  const [activeDepartment, setActiveDepartment] = useState(department);
  const [expandedDepartments, setExpandedDepartments] = useState<Record<string, boolean>>({ [department]: true });
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [aigcMode, setAigcMode] = useState(false);
  const [pendingImages, setPendingImages] = useState<PendingImage[]>([]);
  const [aigcBrief, setAigcBrief] = useState('');
  const [aigcPlatform, setAigcPlatform] = useState('TikTok / 短视频');
  const [aigcDuration, setAigcDuration] = useState('10');
  const [aigcRatio, setAigcRatio] = useState('9:16');
  const [aigcStyle, setAigcStyle] = useState('明亮、干净、商业广告感');
  const [aigcError, setAigcError] = useState('');
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const pendingImagesRef = useRef<PendingImage[]>([]);
  const currentDepartment = useMemo(
    () => departments.find((item) => item.slug === activeDepartment) || { slug: activeDepartment, name, agentName: name, description, emoji: '✦' },
    [activeDepartment, description, name],
  );

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => { pendingImagesRef.current = pendingImages; }, [pendingImages]);
  useEffect(() => () => pendingImagesRef.current.forEach((item) => URL.revokeObjectURL(item.url)), []);

  useEffect(() => {
    let cancelled = false;
    async function initialize() {
      try {
        const [user, items] = await Promise.all([getCurrentUser(), listConversations()]);
        if (cancelled) return;
        setCurrentUser(user);
        setConversations(items);
        const first = items.find((item) => item.department === department);
        if (first) {
          const detail = await getConversation(first.id);
          if (!cancelled) {
            setActiveConversationId(detail.id);
            setMessages(detail.messages);
          }
        }
      } catch {
        redirectToLogin();
      } finally {
        if (!cancelled) setInitializing(false);
      }
    }
    void initialize();
    return () => { cancelled = true; };
  }, [department]);

  async function openConversation(item: Conversation) {
    if (loading) return;
    try {
      const detail = await getConversation(item.id);
      setActiveDepartment(item.department);
      setActiveConversationId(detail.id);
      setMessages(detail.messages);
      setAigcMode(false);
      clearPendingImages();
      setExpandedDepartments((current) => ({ ...current, [item.department]: true }));
    } catch {
      redirectToLogin();
    }
  }

  function toggleDepartment(slug: string) {
    const nextExpanded = !expandedDepartments[slug];
    setExpandedDepartments((current) => ({ ...current, [slug]: nextExpanded }));
    if (!nextExpanded || slug === activeDepartment) return;
    setActiveDepartment(slug);
    setAigcMode(false);
    clearPendingImages();
    const first = conversations.find((item) => item.department === slug);
    if (first) void openConversation(first);
    else { setActiveConversationId(null); setMessages([]); }
  }

  function createChat(slug = activeDepartment) {
    setActiveDepartment(slug);
    setActiveConversationId(null);
    setMessages([]);
    setInput('');
    setAigcMode(false);
    clearPendingImages();
    setAigcError('');
    setExpandedDepartments((current) => ({ ...current, [slug]: true }));
  }

  function activateAigc() {
    if (activeDepartment !== 'ads') return;
    setAigcMode(true);
    setAigcError('');
  }

  function leaveAigc() {
    setAigcMode(false);
    clearPendingImages();
    setAigcError('');
  }

  function clearPendingImages() {
    pendingImagesRef.current.forEach((item) => URL.revokeObjectURL(item.url));
    pendingImagesRef.current = [];
    setPendingImages([]);
  }

  async function ensureConversation(): Promise<string> {
    if (activeConversationId) return activeConversationId;
    const created = await createConversation(activeDepartment);
    setActiveConversationId(created.id);
    setConversations((current) => [created, ...current]);
    return created.id;
  }

  async function submit(text: string) {
    const content = text.trim();
    if (!content || loading || initializing) return;
    setInput('');
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: 'user', content, status: 'completed', created_at: new Date().toISOString() }]);
    setLoading(true);
    try {
      const conversationId = await ensureConversation();
      const result = await sendConversationMessage(conversationId, content);
      setMessages((prev) => [...prev, result.assistant_message]);
      setConversations((current) => [result.conversation, ...current.filter((item) => item.id !== result.conversation.id)]);
    } catch (error) {
      if (String(error).includes('401')) redirectToLogin();
      else setMessages((prev) => [...prev, { id: `error-${Date.now()}`, role: 'assistant', content: '暂时无法连接服务，你的问题已保留，请稍后重试。', status: 'failed', created_at: new Date().toISOString() }]);
    } finally {
      setLoading(false);
    }
  }

  function selectImages(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files || []);
    const maxBytes = 10 * 1024 * 1024;
    const valid: PendingImage[] = [];
    const errors: string[] = [];
    for (const file of files) {
      if (!file.type.startsWith('image/')) errors.push(`${file.name} 不是图片文件`);
      else if (file.size > maxBytes) errors.push(`${file.name} 超过 10 MB`);
      else if (pendingImages.length + valid.length >= 9) errors.push('最多上传 9 张商品图');
      else valid.push({ file, url: URL.createObjectURL(file) });
    }
    setPendingImages((current) => [...current, ...valid]);
    setAigcError(errors.join('；'));
    event.target.value = '';
  }

  function removeImage(index: number) {
    setPendingImages((current) => {
      const removed = current[index];
      if (removed) URL.revokeObjectURL(removed.url);
      return current.filter((_, itemIndex) => itemIndex !== index);
    });
  }

  async function submitAigc(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (loading || initializing) return;
    if (!pendingImages.length) { setAigcError('请先上传至少一张商品图片'); return; }
    const images = [...pendingImages];
    const brief = aigcBrief.trim() || '请基于商品特点设计一支简洁、有购买吸引力的电商短视频。';
    const displayContent = `【AIGC 视频提示词】\n${brief}`;
    setAigcError('');
    setMessages((prev) => [...prev, {
      id: `local-${Date.now()}`,
      role: 'user',
      content: displayContent,
      status: 'completed',
      created_at: new Date().toISOString(),
      metadata: { mode: 'aigc_video_prompt', attachments: images.map((item, index) => ({ name: item.file.name, content_type: item.file.type, size: item.file.size, label: `图片${index + 1}` })) },
    }]);
    setLoading(true);
    try {
      const conversationId = await ensureConversation();
      const result = await generateAigcVideoPrompt(conversationId, {
        files: images.map((item) => item.file),
        brief,
        platform: aigcPlatform,
        durationSeconds: aigcDuration,
        aspectRatio: aigcRatio,
        style: aigcStyle,
      });
      setMessages((prev) => [...prev, result.assistant_message]);
      setConversations((current) => [result.conversation, ...current.filter((item) => item.id !== result.conversation.id)]);
      clearPendingImages();
      setAigcBrief('');
    } catch (error) {
      if (String(error).includes('401')) redirectToLogin();
      else setMessages((prev) => [...prev, { id: `error-${Date.now()}`, role: 'assistant', content: error instanceof Error ? error.message : '提示词生成失败，请稍后重试。', status: 'failed', created_at: new Date().toISOString() }]);
    } finally {
      setLoading(false);
    }
  }

  function handleSend(event: FormEvent<HTMLFormElement>) { event.preventDefault(); void submit(input); }

  async function copyMessage(message: ConversationMessage) {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessageId(message.id);
      window.setTimeout(() => setCopiedMessageId((current) => current === message.id ? null : current), 1600);
    } catch { /* Clipboard permission is optional. */ }
  }

  return <main className="agent-shell flex h-screen overflow-hidden bg-[#f7f8fb] p-0 md:p-3">
    <aside className="agent-sidebar hidden w-[260px] shrink-0 flex-col rounded-2xl border border-[#e7ebf0] bg-white/85 shadow-[0_18px_55px_rgba(36,43,61,.07)] backdrop-blur-xl md:flex">
      <Link href="/" className="agent-brand flex items-center gap-3 border-b border-[#eef1f4] px-5 py-5"><div className="agent-brand-mark flex h-9 w-9 items-center justify-center rounded-xl text-sm font-extrabold text-white">E</div><div><div className="text-sm font-extrabold tracking-tight text-[#202632]">ERGOLIFE</div><div className="mt-0.5 text-[9px] uppercase tracking-[.18em] text-[#a5acb7]">Agent Workspace</div></div></Link>
      <div className="px-3 py-4"><button type="button" onClick={() => createChat()} className="agent-new-chat flex w-full items-center justify-center gap-2 rounded-xl bg-[#202632] px-3 py-3 text-xs font-bold text-white shadow-[0_8px_17px_rgba(32,38,50,.14)] transition hover:-translate-y-0.5 hover:bg-[#303746]"><span className="text-lg font-light leading-none">＋</span>新建聊天</button></div>
      <div className="px-4 pb-2 text-[10px] font-extrabold uppercase tracking-[.13em] text-[#a5acb7]">部门工作区</div>
      <nav className="flex-1 space-y-1 overflow-y-auto px-3 pb-4">
        {departments.map((dept) => {
          const isActive = dept.slug === activeDepartment;
          const expanded = expandedDepartments[dept.slug];
          const items = conversations.filter((item) => item.department === dept.slug);
          return <div key={dept.slug} className="department-group"><div className="flex items-center gap-1"><button type="button" onClick={() => toggleDepartment(dept.slug)} className={`department-row group flex min-w-0 flex-1 items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${isActive ? 'bg-[#e8f8f2] text-[#202632]' : 'text-[#687080] hover:bg-[#f4f6f9] hover:text-[#202632]'}`}><span className={`department-icon flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs ${isActive ? 'bg-white text-[#087b61] shadow-[0_3px_9px_rgba(16,163,127,.12)]' : 'bg-[#f1f3f7] text-[#87909d]'}`}>{dept.emoji}</span><span className="min-w-0 flex-1 truncate text-xs font-semibold">{dept.name}部门</span><span className={`text-[10px] ${isActive ? 'text-[#078565]' : 'text-[#a6adba]'}`}>{items.length}</span></button><button type="button" onClick={() => createChat(dept.slug)} aria-label={`在${dept.name}部门新建聊天`} className="department-plus rounded-lg px-1.5 py-1 text-base leading-none text-[#b4bbc5] opacity-0 transition hover:bg-[#e8f8f2] hover:text-[#087b61] focus:opacity-100 group-hover:opacity-100">＋</button><button type="button" onClick={() => toggleDepartment(dept.slug)} aria-label={`${expanded ? '收起' : '展开'}${dept.name}部门聊天`} aria-expanded={expanded} className={`rounded-lg px-1.5 py-1 text-sm leading-none text-[#aab1bd] transition hover:bg-[#f4f6f9] hover:text-[#087b61] ${expanded ? 'rotate-90 text-[#087b61]' : ''}`}>›</button></div>{expanded && <div className="nested-chat-list ml-5 mt-1 space-y-0.5 border-l border-[#dfeee8] pl-3">{items.map((item) => <button key={item.id} type="button" onClick={() => void openConversation(item)} className={`nested-chat-item flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[10px] transition ${activeConversationId === item.id ? 'bg-[#f0f3f6] font-bold text-[#202632]' : 'text-[#7f8794] hover:bg-[#f5f7f9] hover:text-[#202632]'}`}><span className={`h-1 w-1 shrink-0 rounded-full ${activeConversationId === item.id ? 'bg-[#10a37f] shadow-[0_0_0_3px_rgba(16,163,127,.12)]' : 'bg-[#cdd2db]'}`} />{item.title}</button>)}</div>}</div>;
        })}
      </nav>
      <div className="m-3 mt-auto flex items-center gap-2 border-t border-[#eef1f4] px-2 pt-4"><div className="flex h-8 w-8 items-center justify-center rounded-full bg-[#eeeafd] text-[11px] font-extrabold text-[#6b51bb]">{(currentUser?.display_name || '员').slice(0, 1)}</div><div><div className="text-[11px] font-bold text-[#3d4451]">{currentUser?.display_name || '正在验证身份'}</div><div className="mt-0.5 text-[10px] text-[#a0a7b2]">飞书员工 · 已连接</div></div><span className="ml-auto text-lg text-[#aeb4bf]">···</span></div>
    </aside>

    <section className="relative flex min-w-0 flex-1 flex-col"><header className="flex h-[68px] items-center justify-between border-b border-[#e9edf2] px-4 sm:px-7"><div className="flex min-w-0 items-center gap-3"><Link href="/" className="mr-1 text-sm text-[#7f8795] md:hidden">←</Link><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#e8f8f2] text-lg">{currentDepartment.emoji}</div><div className="min-w-0"><div className="flex items-center gap-2"><h1 className="truncate text-sm font-extrabold tracking-tight text-[#202632]">{currentDepartment.name} Agent</h1><span className="hidden rounded-full bg-[#e8f8f2] px-2 py-1 text-[9px] font-bold text-[#087b61] sm:inline">在线</span>{aigcMode && <span className="rounded-full bg-[#fff4df] px-2 py-1 text-[9px] font-bold text-[#a96820]">AIGC 提示词模式</span>}</div><p className="mt-0.5 truncate text-[10px] text-[#8c94a0]">{aigcMode ? '上传商品图，生成 Seedance 视频提示词' : currentDepartment.description}</p></div></div><div className="flex items-center gap-2"><button title="新建聊天" onClick={() => createChat()} className="rounded-lg border border-[#e9edf2] bg-white p-2 text-[#87909d] transition hover:border-[#cbece2] hover:text-[#087b61]">＋</button><div className="hidden items-center gap-1.5 rounded-full bg-white px-2.5 py-1.5 text-[10px] text-[#648175] sm:flex"><span className="h-1.5 w-1.5 rounded-full bg-[#22ba8a] shadow-[0_0_0_4px_rgba(34,186,138,.12)]" />系统运行正常</div></div></header>
      <div className="border-b border-[#e9edf2] px-4 py-2 xl:hidden"><WorkflowToolbar department={activeDepartment} compact onSelectAigc={activateAigc} aigcActive={aigcMode} /></div>
      <div ref={listRef} className="flex-1 overflow-y-auto px-4 sm:px-8"><div className="mx-auto flex min-h-full max-w-3xl flex-col pb-6">{messages.length === 0 ? <div className="my-auto py-12"><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-[#e8f8f2] text-xl text-[#087b61] shadow-[0_0_35px_rgba(16,163,127,.12)]">✦</div><h2 className="mt-5 text-center text-xl font-bold tracking-tight text-[#202632]">今天想从哪里开始？</h2><p className="mx-auto mt-2 max-w-md text-center text-sm leading-6 text-[#8a929e]">我是{currentDepartment.agentName}，可以协助你处理{currentDepartment.description}相关工作。</p><div className="mx-auto mt-8 grid max-w-xl gap-2 sm:grid-cols-3">{(suggestions[activeDepartment] || []).map((item) => <button key={item} onClick={() => void submit(item)} className="group rounded-xl border border-[#e9edf2] bg-white px-3 py-3 text-left text-xs leading-5 text-[#687080] shadow-[0_8px_22px_rgba(36,43,61,.04)] transition hover:-translate-y-0.5 hover:border-[#cbece2] hover:bg-[#fbfffd] hover:text-[#202632]">{item}<span className="mt-2 block text-[#b5bdc8] transition group-hover:text-[#10a37f]">↗</span></button>)}</div></div> : <div className="space-y-7 py-8">{messages.map((message) => { const attachments = message.metadata?.attachments || []; const isAigc = message.metadata?.mode === 'aigc_video_prompt'; return <div key={message.id} className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>{message.role === 'assistant' && <div className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[#e8f8f2] text-[10px] font-extrabold text-[#087b61]">AI</div>}<div className={message.role === 'user' ? 'max-w-[82%] rounded-2xl rounded-tr-md bg-[#303746] px-4 py-3 text-sm leading-7 text-white shadow-[0_8px_20px_rgba(32,38,50,.13)]' : `max-w-[90%] whitespace-pre-wrap py-1 text-sm leading-7 ${message.status === 'failed' ? 'text-[#b42318]' : 'text-[#202632]'}`}><div>{message.content}</div>{attachments.length > 0 && <div className={`mt-2 flex flex-wrap gap-1.5 ${message.role === 'user' ? 'border-t border-white/15 pt-2' : ''}`}>{attachments.map((attachment) => <span key={`${message.id}-${attachment.label || attachment.name}`} className={`rounded-lg px-2 py-1 text-[10px] ${message.role === 'user' ? 'bg-white/10 text-white/80' : 'bg-[#f0f8f5] text-[#087b61]'}`}>▧ {attachment.label || attachment.name}</span>)}</div>}{isAigc && message.role === 'assistant' && <button type="button" onClick={() => void copyMessage(message)} className="mt-3 rounded-lg border border-[#dfeee8] bg-white px-2.5 py-1.5 text-[10px] font-bold text-[#087b61] transition hover:bg-[#f2fcf8]">{copiedMessageId === message.id ? '已复制' : '复制完整提示词'}</button>}</div></div>; })}{loading && <div className="flex items-center gap-3"><div className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#e8f8f2] text-[10px] font-extrabold text-[#087b61]">AI</div><div className="flex gap-1 py-2"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#aeb6c1]" /><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#aeb6c1]" style={{ animationDelay: '0.15s' }} /><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#aeb6c1]" style={{ animationDelay: '0.3s' }} /></div></div>}</div>}</div></div>
      {aigcMode ? <div className="px-4 pb-4 sm:px-8 sm:pb-6"><form onSubmit={submitAigc} className="mx-auto max-w-3xl rounded-2xl border border-[#bde8da] bg-white p-3 shadow-[0_10px_30px_rgba(16,163,127,.09)]"><div className="flex items-center justify-between gap-3"><div><div className="text-xs font-extrabold text-[#202632]">生成 AIGC 视频提示词</div><div className="mt-1 text-[10px] text-[#687383]">商品图只用于本次生成，提示词和聊天记录会保存。</div></div><button type="button" onClick={leaveAigc} className="rounded-lg px-2.5 py-1.5 text-[10px] font-bold text-[#687383] transition hover:bg-[#f4f6f8]">退出模式</button></div><button type="button" onClick={() => fileInputRef.current?.click()} className="mt-3 flex min-h-[88px] w-full flex-wrap items-center gap-2 rounded-xl border border-dashed border-[#bce5d8] bg-[#f8fdfb] p-2.5 text-left transition hover:bg-[#f1fbf7]"><input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/gif,image/webp" multiple className="hidden" onChange={selectImages} />{pendingImages.length ? pendingImages.map((item, index) => <span key={`${item.file.name}-${index}`} className="relative h-16 w-16 overflow-hidden rounded-lg border border-[#dceee7] bg-white"><img src={item.url} alt={`商品图${index + 1}`} className="h-full w-full object-cover" /><span onClick={(event) => { event.stopPropagation(); removeImage(index); }} className="absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-black/60 text-[10px] text-white">×</span></span>) : <span className="flex w-full flex-col items-center justify-center py-2 text-center"><span className="text-xl text-[#10a37f]">＋</span><span className="mt-1 text-[10px] font-bold text-[#087b61]">上传商品图片</span><span className="mt-0.5 text-[9px] text-[#8b96a2]">支持 JPG、PNG、GIF、WebP，最多 9 张</span></span>}{pendingImages.length > 0 && <span className="flex h-16 min-w-[74px] items-center justify-center rounded-lg border border-[#dceee7] text-[10px] font-bold text-[#087b61]">＋ 添加</span>}</button><textarea value={aigcBrief} onChange={(event) => setAigcBrief(event.target.value)} placeholder="描述你想要的视频，例如：突出防水、便携和户外使用场景…" rows={2} className="mt-3 w-full resize-none rounded-xl border border-[#e5e9ee] bg-[#fbfcfd] px-3 py-2.5 text-xs leading-5 text-[#202632] outline-none placeholder:text-[#aeb6c1] focus:border-[#a9dfcf]" /><div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-4"><label className="text-[9px] font-bold text-[#687383]">投放平台<select value={aigcPlatform} onChange={(event) => setAigcPlatform(event.target.value)} className="mt-1 h-8 w-full rounded-lg border border-[#e5e9ee] bg-white px-2 text-[10px] font-normal text-[#202632] outline-none"><option>TikTok / 短视频</option><option>Amazon</option><option>独立站</option><option>Instagram / Reels</option></select></label><label className="text-[9px] font-bold text-[#687383]">视频时长<select value={aigcDuration} onChange={(event) => setAigcDuration(event.target.value)} className="mt-1 h-8 w-full rounded-lg border border-[#e5e9ee] bg-white px-2 text-[10px] font-normal text-[#202632] outline-none"><option value="6">6 秒</option><option value="10">10 秒</option><option value="15">15 秒</option></select></label><label className="text-[9px] font-bold text-[#687383]">画面比例<select value={aigcRatio} onChange={(event) => setAigcRatio(event.target.value)} className="mt-1 h-8 w-full rounded-lg border border-[#e5e9ee] bg-white px-2 text-[10px] font-normal text-[#202632] outline-none"><option>9:16</option><option>1:1</option><option>16:9</option></select></label><label className="text-[9px] font-bold text-[#687383]">风格<input value={aigcStyle} onChange={(event) => setAigcStyle(event.target.value)} className="mt-1 h-8 w-full rounded-lg border border-[#e5e9ee] bg-white px-2 text-[10px] font-normal text-[#202632] outline-none" /></label></div>{aigcError && <div className="mt-2 rounded-lg bg-[#fff1f2] px-3 py-2 text-[10px] leading-4 text-[#b42318]">{aigcError}</div>}<div className="mt-3 flex items-center justify-between gap-3"><span className="text-[9px] text-[#8b96a2]">视觉模型：DeepSeek Vision</span><button type="submit" disabled={loading || initializing || !pendingImages.length} className="rounded-xl bg-[#10a37f] px-4 py-2.5 text-[10px] font-bold text-white transition hover:bg-[#087b61] disabled:cursor-not-allowed disabled:opacity-40">{loading ? '正在分析商品图…' : '生成视频提示词'}</button></div></form></div> : <div className="px-4 pb-4 sm:px-8 sm:pb-6"><div className="mx-auto mb-2 flex max-w-3xl gap-2 overflow-x-auto">{(suggestions[activeDepartment] || []).map((item) => <button key={item} type="button" onClick={() => setInput(item)} className="shrink-0 rounded-full border border-[#e9edf2] bg-white px-3 py-1.5 text-[10px] text-[#7b8492] transition hover:border-[#cbece2] hover:bg-[#f5fffb] hover:text-[#087b61]">{item}</button>)}</div><form onSubmit={handleSend} className="mx-auto max-w-3xl rounded-2xl border border-[#dfe4eb] bg-white p-2 shadow-[0_10px_30px_rgba(54,61,79,.07)] transition focus-within:border-[#a9dfcf] focus-within:shadow-[0_10px_30px_rgba(16,163,127,.1)]"><textarea rows={1} value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit(input); } }} placeholder={`向${currentDepartment.agentName}发送消息…`} className="max-h-36 min-h-[48px] w-full resize-none bg-transparent px-3 py-3 text-sm leading-6 text-[#202632] outline-none placeholder:text-[#aeb4c0]" /><div className="flex items-center justify-between px-2 pb-1"><span className="hidden text-[10px] text-[#b0b6c1] sm:block">Enter 发送 · Shift + Enter 换行</span><div className="ml-auto flex items-center gap-2"><span className="hidden text-[10px] text-[#b0b6c1] sm:inline">AI 生成内容仅供参考</span><button type="submit" disabled={loading || initializing || !input.trim()} className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#10a37f] text-white transition hover:bg-[#087b61] disabled:cursor-not-allowed disabled:opacity-25"><svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m5 12 7-7 7 7M12 5v14" strokeLinecap="round" /></svg></button></div></div></form></div>}</section>
    <WorkflowToolbar department={activeDepartment} onSelectAigc={activateAigc} aigcActive={aigcMode} />
  </main>;
}
