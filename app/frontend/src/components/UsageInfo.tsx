import type { Usage } from '../types';

function numberText(value: unknown) { return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? String(value) : '未知'; }
export default function UsageInfo({ usage }: { usage?: Usage | null }) {
  const cost = typeof usage?.cost === 'number' && Number.isFinite(usage.cost) && usage.cost >= 0 ? `${usage.cost} ${usage.currency ?? ''}` : '未配置价格';
  return <p className="usage-info">输入 token：{numberText(usage?.inputTokens ?? usage?.prompt_tokens)} · 输出 token：{numberText(usage?.outputTokens ?? usage?.completion_tokens)} · 成本：{cost}</p>;
}
