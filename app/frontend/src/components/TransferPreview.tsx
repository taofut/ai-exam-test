import { ArrowRightLeft } from 'lucide-react';
import { formatTime, type AgentResponse } from '../types';

export default function TransferPreview({ response, busy, onConfirm }: { response: AgentResponse; busy: boolean; onConfirm: () => void }) {
  const preview = response.preview;
  if (response.status !== 'CONFIRM_REQUIRED' || !preview || !response.confirmToken || !response.confirmExpiresAt) return null;
  return <div className="transfer-preview-card"><div className="section-title"><ArrowRightLeft size={18} /><h3>待确认调拨</h3></div><p><strong>{preview.itemName}</strong> · 调拨 {preview.quantity} 件</p><div className="preview-grid"><div><span>源仓库 #{preview.fromWarehouseId}</span><strong>{preview.fromOnHand} → {preview.fromOnHand - preview.quantity}</strong></div><div><span>目标仓库 #{preview.toWarehouseId}</span><strong>{preview.toOnHand} → {preview.toOnHand + preview.quantity}</strong></div></div><p className="subtle">确认有效至 {formatTime(response.confirmExpiresAt)}（北京时间）。确认后执行调拨。</p><button className="button primary" data-test="transfer-confirm" disabled={busy} onClick={onConfirm}>{busy ? '正在确认…' : '确认执行调拨'}</button></div>;
}
