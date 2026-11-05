import { useEffect, useState, type FormEvent } from 'react';
import { ArrowDownToLine, Box, Layers, Plus, RefreshCw, Trash2, X } from 'lucide-react';
import { describeError, describeWriteFailure, isAbort, type Api } from '../api';
import { createKitOrder, type KitLineInput } from '../kitOrder';
import type { Inventory, Notice } from '../types';
import { useRequestScope } from '../useRequestScope';
import { EmptyState, Feedback } from './Feedback';
import AiPanel from './AiPanel';

interface KitRow { key: string; inventoryId: string; quantity: string }
let kitRowSeq = 0;
const newKitRow = (inventoryId = '', quantity = '1'): KitRow => ({ key: `kit-row-${++kitRowSeq}`, inventoryId, quantity });

export default function InventoryDetail({ api, inventoryId, refresh, onChanged }: { api: Api; inventoryId: number; refresh: number; onChanged: () => void }) {
  const scope = useRequestScope();
  const [inventory, setInventory] = useState<Inventory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [retry, setRetry] = useState(0);
  const [kitOpen, setKitOpen] = useState(false);
  const [kitOptions, setKitOptions] = useState<Inventory[] | null>(null);
  const [kitOptionsError, setKitOptionsError] = useState('');
  const [kitRows, setKitRows] = useState<KitRow[]>([]);
  const [kitReason, setKitReason] = useState('');
  const [kitError, setKitError] = useState('');
  const [kitNotice, setKitNotice] = useState<Notice | null>(null);
  const [kitBusy, setKitBusy] = useState(false);
  const [kitReload, setKitReload] = useState(0);
  const warehouseId = inventory?.warehouseId;

  useEffect(() => {
    const lease = scope.begin('detail');
    setLoading(true); setError('');
    api.get<Inventory>(`/api/inventories/${inventoryId}`, {}, lease.signal).then((value) => { if (lease.isCurrent()) setInventory(value); })
      .catch((failure: unknown) => { if (lease.isCurrent() && !isAbort(failure)) { setInventory(null); setError(describeError(failure)); } })
      .finally(() => { if (lease.isCurrent()) setLoading(false); lease.finish(); });
  }, [api, inventoryId, refresh, retry, scope]);

  // Same-warehouse candidates for the kit list; the server still intersects them with the caller's scope.
  useEffect(() => {
    if (!kitOpen || warehouseId === undefined) return;
    const lease = scope.begin('kit-options');
    setKitOptions(null); setKitOptionsError('');
    api.get<{ items: Inventory[] }>('/api/inventories', { warehouseId }, lease.signal)
      .then((value) => { if (lease.isCurrent()) setKitOptions(value.items); })
      .catch((failure: unknown) => { if (lease.isCurrent() && !isAbort(failure)) { setKitOptions([]); setKitOptionsError(describeError(failure)); } })
      .finally(() => { if (lease.isCurrent()) lease.finish(); });
  }, [api, kitOpen, kitReload, refresh, scope, warehouseId]);

  async function issue(event: FormEvent) {
    event.preventDefault();
    if (!inventory || busy) return;
    const amount = Number(quantity);
    if (!Number.isInteger(amount) || amount < 1) { setNotice({ kind: 'error', message: '请输入正整数领用数量。' }); return; }
    const lease = scope.begin('issue');
    setBusy(true); setNotice(null);
    try {
      const result = await api.post<{ issue: { issueNo: string } }>(`/api/inventories/${inventory.id}/issue`, { quantity: amount, version: inventory.version, reasonText: reason }, lease.signal);
      if (!lease.isCurrent()) return;
      setNotice({ kind: 'success', message: `领用成功 · ${result.issue.issueNo}` });
      onChanged();
    } catch (failure) { if (lease.isCurrent() && !isAbort(failure)) { setNotice({ kind: 'error', message: describeWriteFailure(failure) }); onChanged(); } }
    finally { if (lease.isCurrent()) setBusy(false); lease.finish(); }
  }

  function openKit() {
    if (!inventory) return;
    setKitError(''); setKitNotice(null); setKitReason('');
    setKitRows([newKitRow(String(inventory.id)), newKitRow()]);
    setKitOpen(true);
  }
  function updateKitRow(key: string, patch: Partial<KitRow>) {
    setKitRows((rows) => {
      const previous = rows.find((row) => row.key === key);
      const next = rows.map((row) => row.key === key ? { ...row, ...patch } : row);
      // Fill the last row and a fresh one appears: the operator never has to hunt for "add".
      if (patch.inventoryId && previous?.inventoryId === '' && next[next.length - 1]?.key === key && next.length < 5) next.push(newKitRow());
      return next;
    });
  }
  function addKitRow() { setKitRows((rows) => rows.length >= 5 ? rows : [...rows, newKitRow()]); }
  function removeKitRow(key: string) { setKitRows((rows) => rows.length <= 2 ? rows : rows.filter((row) => row.key !== key)); }

  async function submitKit(event: FormEvent) {
    event.preventDefault();
    if (!inventory || kitBusy) return;
    const byId = new Map((kitOptions ?? []).map((option) => [option.id, option]));
    const seen = new Set<number>();
    const lines: KitLineInput[] = [];
    // Trailing blank rows are just spare inputs; only selected rows form the kit.
    const selectedRows = kitRows.filter((row) => row.inventoryId);
    if (selectedRows.length < 2) { setKitError('请至少选择 2 种物资。'); return; }
    if (selectedRows.length > 5) { setKitError('同仓套料最多 5 种物资。'); return; }
    for (const row of selectedRows) {
      const id = Number(row.inventoryId);
      if (!Number.isInteger(id)) { setKitError('所选物资不可用，请重新选择。'); return; }
      if (seen.has(id)) { setKitError('同一物资不能重复列入套料。'); return; }
      seen.add(id);
      const amount = Number(row.quantity);
      if (!Number.isInteger(amount) || amount < 1) { setKitError('每行数量须为正整数。'); return; }
      const option = byId.get(id);
      if (!option) { setKitError('所选物资已不在当前仓库，请重新选择。'); return; }
      if (amount > option.onHand) { setKitError(`${option.itemName} 当前仅 ${option.onHand} ${option.unit}，库存不足。`); return; }
      lines.push({ inventoryId: id, quantity: amount, version: option.version });
    }
    if (lines.length < 2 || lines.length > 5) { setKitError('同仓套料须为 2～5 种不同物资。'); return; }
    const lease = scope.begin('kit-submit');
    setKitBusy(true); setKitError('');
    try {
      const result = await createKitOrder(api, { warehouseId: inventory.warehouseId, reasonText: kitReason, lines }, lease.signal);
      if (!lease.isCurrent()) return;
      setKitOpen(false); setKitRows([]);
      setKitNotice({ kind: 'success', message: `套料领用成功 · ${result.order.orderNo} · ${result.lines.length} 项物资` });
      onChanged();
    } catch (failure) {
      if (lease.isCurrent() && !isAbort(failure)) {
        // Keep the filled list so the operator can retry after the balance/version refresh.
        setKitError(describeWriteFailure(failure));
        setKitReload((value) => value + 1);
        onChanged();
      }
    } finally { if (lease.isCurrent()) setKitBusy(false); lease.finish(); }
  }

  if (loading && !inventory) return <section className="detail-pane"><EmptyState text="正在读取库存详情…" loading /></section>;
  if (!inventory) return <section className="detail-pane"><EmptyState text={error || '库存详情未知'} /><button className="button secondary" onClick={() => setRetry((value) => value + 1)}><RefreshCw size={15} />重试</button></section>;
  const chosenIds = new Set(kitRows.map((row) => row.inventoryId).filter(Boolean));
  return <section className="detail-pane" aria-label="库存详情">
    <div className="detail-header"><div><span className="eyebrow">库存 #{inventory.id}</span><h2>{inventory.itemName}</h2><p>{inventory.itemNo} · 物资 #{inventory.itemId}</p><p>{inventory.warehouseName} · {inventory.deptName}</p></div><span className={`badge ${inventory.onHand < inventory.reorderPoint ? 'amber' : ''}`}>{inventory.onHand < inventory.reorderPoint ? '低于补货点' : '库存正常'}</span></div>
    <div className="stock-panel"><div className="stock-main"><span className="stock-icon"><Box size={23} /></span><div><span>当前可用库存</span><strong>{inventory.onHand}<small>{inventory.unit}</small></strong></div></div><div><span>补货点</span><strong>{inventory.reorderPoint}</strong></div><div><span>目标库存</span><strong>{inventory.targetStock}</strong></div><div><span>库存版本</span><strong>v{inventory.version}</strong></div></div>
    {loading ? <p className="subtle" role="status">正在更新库存…</p> : null}
    {inventory.permissions.canIssue ? <><section className="content-section"><div className="section-title"><ArrowDownToLine size={18} /><div><h3>领用备件</h3><p>领用后可整单退回原仓库</p></div></div>
      <form className="issue-form" onSubmit={issue}><div className="issue-inputs"><label>领用数量<input data-test="issue-quantity" type="number" min="1" step="1" required value={quantity} onChange={(event) => setQuantity(event.target.value)} /></label><label>用途（选填）<input type="text" maxLength={500} placeholder="填写本次领用用途" value={reason} onChange={(event) => setReason(event.target.value)} /></label></div><button className="button primary" data-test="issue-submit" type="submit" disabled={busy || loading}>{busy ? '正在提交…' : '确认领用'}</button></form>
      <Feedback notice={notice} />
    </section>
    <section className="content-section"><div className="section-title"><Layers size={18} /><div><h3>维修套料领用</h3><p>同仓 2～5 种物资一次提交，整单成功或整单不生效</p></div></div>
      <p className="subtle kit-hint">套料会生成一张父单和完整明细；退回须整单办理，不能单退其中一项。</p>
      <button type="button" className="button secondary kit-launch" data-test="kit-open" onClick={openKit} disabled={busy}><Layers size={15} />新建套料清单</button>
      <Feedback notice={kitNotice} />
    </section></> : <p className="read-only-note">当前身份可查看此库存。</p>}
    {inventory.permissions.canAnalyze ? <AiPanel api={api} inventory={inventory} onChanged={onChanged} /> : null}
    {kitOpen ? <div className="modal-backdrop">
      <form className="modal kit-modal" data-test="kit-dialog" onSubmit={submitKit}>
        <div className="modal-header"><h3>同仓套料清单</h3><button type="button" className="icon-button" aria-label="关闭套料清单" onClick={() => setKitOpen(false)}><X size={17} /></button></div>
        <p className="subtle">仓库：{inventory.warehouseName} · 所选库存须属于同一仓库，2～5 行且不重复物资。</p>
        <div className="kit-rows">{kitRows.map((row, index) => {
          const selected = (kitOptions ?? []).find((option) => String(option.id) === row.inventoryId);
          const candidates = (kitOptions ?? []).filter((option) => String(option.id) === row.inventoryId || !chosenIds.has(String(option.id)));
          return <div className="kit-row" key={row.key}>
            <label>物资 {index + 1}<select data-test="kit-item" value={row.inventoryId} onChange={(event) => updateKitRow(row.key, { inventoryId: event.target.value })}>
              <option value="">请选择物资</option>
              {candidates.map((option) => <option key={option.id} value={option.id}>{option.itemName} · {option.itemNo} · 余 {option.onHand} {option.unit}</option>)}
            </select></label>
            <label>数量<input data-test="kit-quantity" type="number" min="1" step="1" value={row.quantity} onChange={(event) => updateKitRow(row.key, { quantity: event.target.value })} /></label>
            <button type="button" className="icon-button" aria-label={`移除第 ${index + 1} 行`} title="移除该行" disabled={kitRows.length <= 2} onClick={() => removeKitRow(row.key)}><Trash2 size={15} /></button>
            <p className="kit-row-meta">{selected ? `库存 #${selected.id} · 余 ${selected.onHand} ${selected.unit} · v${selected.version}` : '尚未选择物资'}</p>
          </div>;
        })}</div>
        <div className="kit-row-actions"><button type="button" className="button secondary" onClick={addKitRow} disabled={kitRows.length >= 5 || kitOptions === null}><Plus size={14} />添加物资</button><span className="subtle">{kitRows.length} / 5 行</span></div>
        <label>用途（选填）<input type="text" maxLength={500} placeholder="填写本次套料领用用途" value={kitReason} onChange={(event) => setKitReason(event.target.value)} /></label>
        {kitOptions === null && !kitOptionsError ? <p className="subtle" role="status">正在读取同仓物资…</p> : null}
        <Feedback notice={kitOptionsError ? { kind: 'error', message: kitOptionsError } : null} />
        <Feedback notice={kitError ? { kind: 'error', message: kitError } : null} />
        <div className="modal-actions"><button type="button" className="button secondary" onClick={() => setKitOpen(false)}>取消</button><button type="submit" className="button primary" data-test="kit-submit" disabled={kitBusy || kitOptions === null || kitOptions.length < 2}>{kitBusy ? '正在提交…' : '提交套料领用'}</button></div>
      </form>
    </div> : null}
  </section>;
}
