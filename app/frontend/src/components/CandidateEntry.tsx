export type CandidatePage = 'knowledge' | 'workbench';
const entries = {
  knowledge: { title: '保障建议与人工决定', contract: 'contracts/specs/t2.md', description: '复用本日统计与预置资料，完成模型建议、引用、复核和三种决定。计划保存在已有分析记录，无独立草稿管理。AiPanel可作表单参考。' },
  workbench: { title: '备件调拨对话助手', contract: 'contracts/specs/t3.md', description: '完成真实进度、会话澄清、预览确认和双库原子调拨。只要求最低SSE闭环与显式核对，不要求任务运行平台。' },
};
export default function CandidateEntry({ page }: { page: CandidatePage }) {
  const entry = entries[page];
  return <section className="wide-panel" data-test={`${page}-starter`}>
    <div className="panel-heading"><span className="badge amber">考生开发入口 · 未实现</span><h2>{entry.title}</h2><p>{entry.description}</p></div>
    <p className="subtle">开发契约：{entry.contract}</p>
  </section>;
}
