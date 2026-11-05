import { useState, type FormEvent } from 'react';
import { Bot, Pencil, Sparkles, X } from 'lucide-react';
import { describeError, isAbort, type Api } from '../api';
import { formatTime, type Analysis, type Decision, type Inventory, type Notice, type Suggestion } from '../types';
import { useRequestScope } from '../useRequestScope';
import { Feedback } from './Feedback';
import UsageInfo from './UsageInfo';

export default function AiPanel({ api, inventory, onChanged }: { api: Api; inventory: Inventory; onChanged: () => void }) {
  const scope = useRequestScope();
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [edited, setEdited] = useState<Suggestion | null>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<Notice | null>(null);
  const mustReview = analysis ? analysis.requiresHumanReview || analysis.degraded : false;
  const stale = analysis ? analysis.inventoryVersion !== inventory.version : false;
  // 服务端保存的真实快照与本日统计，用于说明建议所依据的实时数量与范围。
  const stock = analysis?.context?.inventory;
  const stats = analysis?.context?.issueStats;
  async function analyze() {
    if (busy) return;
    const lease = scope.begin('analysis');
    setBusy('analysis'); setNotice(null); setAnalysis(null); setReviewed(false); setEditing(false); setEdited(null);
    try {
      const result = await api.post<Analysis>(`/api/inventories/${inventory.id}/ai-replenishment`, undefined, lease.signal);
      if (lease.isCurrent()) setAnalysis(result);
    } catch (failure) { if (lease.isCurrent() && !isAbort(failure)) setNotice({ kind: 'error', message: describeError(failure) }); }
    finally { if (lease.isCurrent()) setBusy(''); lease.finish(); }
  }
  async function decide(action: 'adopt' | 'adopt-edited' | 'reject', suggestion?: Suggestion) {
    if (!analysis || analysis.decision !== 'PENDING' || busy) return;
    const lease = scope.begin('decision');
    setBusy(action); setNotice(null);
    try {
      const body = action === 'adopt-edited'
        ? { suggestedQuantity: suggestion?.suggestedQuantity, reason: suggestion?.reason, reviewed }
        : action === 'adopt' ? { reviewed } : {};
      const result = await api.post<{ callId: number | string; decision: Decision; finalSuggestion?: Suggestion | null; reviewed?: boolean | null; decisionById?: number | null; decisionAt?: string | null }>(`/api/inventories/${inventory.id}/ai-replenishment/${analysis.callId}/${action}`, body, lease.signal);
      if (!lease.isCurrent()) return;
      setAnalysis((current) => current ? { ...current, ...result } : current);
      setEditing(false);
      setNotice({ kind: 'success', message: result.decision === 'REJECTED' ? '已拒绝该建议。' : '已保存采纳决定与补充计划。' });
      onChanged();
    } catch (failure) { if (lease.isCurrent() && !isAbort(failure)) setNotice({ kind: 'error', message: describeError(failure) }); }
    finally { if (lease.isCurrent()) setBusy(''); lease.finish(); }
  }
  function submitEdit(event: FormEvent) { event.preventDefault(); if (edited) void decide('adopt-edited', edited); }
  return <section className="content-section ai-section"><div className="section-title"><Bot size={20} /><div><h3>AI 补货分析</h3><p>基于库存与本日领用统计生成建议，由人工决策</p></div></div>
    <button className="button secondary analyze-button" data-test="ai-analyze" onClick={analyze} disabled={Boolean(busy)}><Sparkles size={15} />{busy === 'analysis' ? '正在分析…' : analysis ? '重新分析' : '分析补货需求'}</button>
    <Feedback notice={notice} />
    {analysis ? <div className="suggestion-card" data-test="ai-suggestion"><div className="suggestion-top"><span>建议补货 <strong>{analysis.suggestion.suggestedQuantity}</strong> {inventory.unit}</span><span className={`badge ${mustReview ? 'amber' : ''}`}>{analysis.degraded ? '备用建议' : mustReview ? '需人工复核' : '待人工决策'}</span></div><p className="suggestion-reason">{analysis.suggestion.reason}</p>
      {stock && stats ? <p className="subtle" data-test="ai-issue-stats">本日领用 {stats.quantity ?? '—'} {stock.unit ?? inventory.unit} · 统计范围 {stats.scope} · 分析时余额 {stock.onHand}、补货点 {stock.reorderPoint}、目标库存 {stock.targetStock}</p> : null}
      <p className="subtle">模型置信度 {(analysis.suggestion.confidence * 100).toFixed(0)}% · 分析时库存 v{analysis.inventoryVersion}{analysis.suggestion.needHuman && !mustReview ? <span data-test="ai-need-human"> · 模型建议人工判断，可直接采纳或修改后采纳</span> : null}</p>
      {analysis.suggestion.knowledgeReferences.length ? <div className="references">{analysis.suggestion.knowledgeReferences.map((reference, index) => <blockquote key={`${reference.docId}-${index}`}><strong>{reference.title} · v{reference.version}</strong><p>{reference.quote}</p></blockquote>)}</div> : <p className="subtle">本日领用量来自业务统计；知识依据按本次检索展示。</p>}
      {analysis.context?.knowledge?.length ? <details className="knowledge-source" data-test="ai-knowledge-source"><summary>查看本次送检知识原文（{analysis.context.knowledge.length} 篇）</summary>
        {analysis.context.knowledge.map((doc) => <blockquote key={doc.docId}><strong>{doc.title} · v{doc.version}{doc.general ? ' · 通用资料' : ''}</strong><p>{doc.content}</p></blockquote>)}
      </details> : null}
      <UsageInfo usage={analysis.usage} />
      {analysis.reviewItems.length ? <ul className="subtle">{analysis.reviewItems.map((item, index) => <li key={index}>{item}</li>)}</ul> : null}
      {analysis.finalSuggestion ? <p className="decision-status">最终计划：{analysis.finalSuggestion.suggestedQuantity} {inventory.unit} · {analysis.finalSuggestion.reason}</p> : null}
      {analysis.decisionAt ? <p className="subtle">决定人 #{analysis.decisionById} · {formatTime(analysis.decisionAt)}</p> : null}
      {stale ? <p className="feedback error">库存已更新，请重新分析后采纳。</p> : null}
      {analysis.decision === 'PENDING' ? <><label className="review-check"><input data-test="ai-reviewed" type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />我已核对补货数量、理由与引用{mustReview ? '（此建议必须复核）' : ''}</label><div className="decision-actions">
        <button className="button primary" data-test="ai-adopt" onClick={() => void decide('adopt')} disabled={Boolean(busy) || stale || (mustReview && !reviewed)}>直接采纳</button>
        <button className="button secondary" data-test="ai-edit-adopt" onClick={() => { setEdited({ ...analysis.suggestion }); setEditing(true); }} disabled={Boolean(busy) || stale}><Pencil size={14} />修改后采纳</button>
        <button className="button quiet" data-test="ai-reject" onClick={() => void decide('reject')} disabled={Boolean(busy)}>拒绝</button></div></> : <p className="decision-status">{analysis.decision === 'REJECTED' ? '已拒绝' : '已采纳，最终计划保存在本次分析记录'}</p>}
    </div> : <p className="subtle ai-placeholder">点击分析查看补货建议。</p>}
    {editing && edited ? <div className="modal-backdrop"><form className="modal" onSubmit={submitEdit} aria-label="编辑补货建议"><div className="modal-header"><h3>修改后采纳</h3><button type="button" className="icon-button" onClick={() => setEditing(false)} aria-label="关闭编辑"><X size={18} /></button></div><p className="subtle">{inventory.warehouseName} · {inventory.itemName}</p><label>补货数量<input type="number" required min="0" max="500" step="1" value={edited.suggestedQuantity} onChange={(event) => setEdited({ ...edited, suggestedQuantity: Number(event.target.value) })} /></label><label>补货理由<textarea required value={edited.reason} onChange={(event) => setEdited({ ...edited, reason: event.target.value })} /></label><p className="subtle">沿用本次分析的真实引用；采纳仅保存本次分析的最终计划。</p><label className="review-check"><input data-test="ai-reviewed-edit" type="checkbox" checked={reviewed} onChange={(event) => setReviewed(event.target.checked)} />我已核对补货数量、理由与引用{mustReview ? '（此建议必须复核）' : ''}</label><Feedback notice={notice} /><div className="modal-actions"><button className="button secondary" type="button" onClick={() => setEditing(false)}>取消</button><button className="button primary" type="submit" disabled={Boolean(busy) || stale || (mustReview && !reviewed)}>确认修改并采纳</button></div></form></div> : null}
  </section>;
}
