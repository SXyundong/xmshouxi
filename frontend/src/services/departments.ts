export interface Department {
  slug: string;
  name: string;
  agentName: string;
  description: string;
  emoji: string;
}

export const departments: Department[] = [
  { slug: 'sales', name: '销售', agentName: '销售分析Agent', description: '销售数据分析与业绩查询', emoji: '📈' },
  { slug: 'inventory', name: '库存', agentName: '库存Agent', description: '库存查询与管理', emoji: '📦' },
  { slug: 'logistics', name: '物流', agentName: '物流Agent', description: '物流跟踪与配送管理', emoji: '🚚' },
  { slug: 'product', name: '选品', agentName: '选品Agent', description: '选品分析与建议', emoji: '🧺' },
  { slug: 'ads', name: '广告', agentName: '广告Agent', description: '广告投放与优化', emoji: '📣' },
  { slug: 'operation', name: '运营', agentName: '运营Agent', description: '运营策略与活动', emoji: '🛠️' },
  { slug: 'finance', name: '财务', agentName: '财务Agent', description: '财务数据与报表', emoji: '💰' },
  { slug: 'design', name: '美工', agentName: '美工Agent', description: '设计素材与创意', emoji: '🎨' },
  { slug: 'hr', name: '招聘', agentName: '招聘Agent', description: '招聘与人事', emoji: '🤝' },
];
