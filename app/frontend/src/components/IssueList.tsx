import { useEffect, useState } from 'react';
import { CornerDownLeft, Layers } from 'lucide-react';
import { describeError, describeWriteFailure, isAbort, type Api } from '../api';
import { returnKitOrder } from '../kitOrder';
import { formatTime, type Inventory, type KitOrderDetail, type MaterialIssue, type MaterialIssueOrder, type MaterialIssueOrderLine, type Notice } from '../types';
import { useRequestScope } from '../useRequestScope';
import { returnMaterialIssue } from '../returnIssue';
import { EmptyState, Feedback } from './Feedback';

interface Props { api: Api; issues: MaterialIssue[] | null; catalog: Inventory[]; error: string; refresh: number; onChanged: () => void }

export default function IssueList({ api, issues, catalog, error, refresh, onChanged }: Props) {
  const scope = useRequestScope();
  const [busyId, setBusyId] = useState<number | null>(null);
  const [busyOrderId, setBusyOrderId] = useState<number | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [orders, setOrders] = useState<MaterialIssueOrder[] | null>(null);
  const [orderLines, setOrderLines] = useState<Record<number, MaterialIssueOrderLine[]>>({});
  const [ordersError, setOrdersError] = useState('');

  useEffect(() => {
    const lease = scope.begin('orders');
    setOrdersError('');
    api.get<{ items: MaterialIssueOrder[] }>('/api/material-issue-orders', { mine: true }, lease.signal).then(async (value) => {
      if (!lease.isCurrent()) return;
      setOrders(value.items);
      // Each parent record needs its real line list to show the whole kit and to return it.
      const details = await Promise.all(value.items.map((order) => api.get<KitOrderDetail>(`/api/material-issue-orders/${order.id}`, {}, lease.signal).catch(() => null)));
      if (!lease.isCurrent()) return;
      const map: Record<number, MaterialIssueOrderLine[]> = {};
      // A failed detail read keeps the parent card visible but must say so, never spin forever.
      details.forEach((detail, index) => { map[value.items[index].id] = detail ? detail.lines : []; });
      setOrderLines(map);
    }).catch((failure: unknown) => { if (lease.isCurrent() && !isAbort(failure)) { setOrders(null); setOrdersError(describeError(failure)); } })
      .finally(() => { if (lease.isCurrent()) lease.finish(); });
  }, [api, refresh, scope]);

  const stockMap = new Map(catalog.map((item) => [item.id, item]));
  const warehouseName = (warehouseId: number) => catalog.find((item) => item.warehouseId === warehouseId)?.warehouseName ?? `仓库 #${warehouseId}`;
  const plainIssues = (issues ?? []).filter((issue) => issue.issueOrderId == null);
  const kitOrders = orders ?? [];

  async function returnIssue(issue: MaterialIssue) {
    if (busyId !== null) return;
    const lease = scope.begin('return');
    setBusyId(issue.id); setNotice(null);
    try {
      const result = await returnMaterialIssue(api, issue.id, lease.signal);
      if (!lease.isCurrent()) return;
      setNotice({ kind: 'success', message: `整单退回成功 · ${result.issue.issueNo}` });
      onChanged();
    } catch (failure) { if (lease.isCurrent() && !isAbort(failure)) { setNotice({ kind: 'error', message: describeWriteFailure(failure) }); onChanged(); } }
    finally { if (lease.isCurrent()) setBusyId(null); lease.finish(); }
  }

  async function returnOrder(order: MaterialIssueOrder) {
    if (busyOrderId !== null) return;
    const lease = scope.begin('return-kit');
    setBusyOrderId(order.id); setNotice(null);
    try {
      const result = await returnKitOrder(api, order.id, lease.signal);
      if (!lease.isCurrent()) return;
      setNotice({ kind: 'success', message: `套料整单退回成功 · ${result.order.orderNo} · ${result.lines.length} 项物资已入库` });
      onChanged();
    } catch (failure) { if (lease.isCurrent() && !isAbort(failure)) { setNotice({ kind: 'error', message: describeWriteFailure(failure) }); onChanged(); } }
    finally { if (lease.isCurrent()) setBusyOrderId(null); lease.finish(); }
  }

  const loading = issues === null || (orders === null && !ordersError);
  const nothing = plainIssues.length === 0 && kitOrders.length === 0;
  return <section className="wide-panel" data-test="my-issues"><div className="panel-heading"><h2>本人领用记录</h2><p>单物资可整单退回；维修套料按父单整单退回，一次恢复全部明细。时间按北京时间展示。</p></div><Feedback notice={notice} />
    {error || ordersError ? <><EmptyState text={error || ordersError} /><button className="button secondary" onClick={onChanged}>重试</button></> : loading ? <EmptyState text="正在读取领用记录…" loading /> : nothing ? <EmptyState text="暂无本人领用记录" /> : <>
      {kitOrders.length > 0 ? <section className="issue-group"><h3 className="group-title">维修套料 · {kitOrders.length} 单</h3><div className="issue-cards">{kitOrders.map((order) => {
        const lines = orderLines[order.id];
        return <article className="issue-card kit-card" key={`order-${order.id}`} data-test="kit-parent" data-order-id={order.id}>
          <div className="issue-card-top"><strong>{order.orderNo}</strong><span className={`badge ${order.status === 'ISSUED' ? 'amber' : ''}`}>{order.status === 'ISSUED' ? '套料已领用' : '套料已退回'}</span></div>
          <h3><Layers size={14} /> 维修套料 · {lines?.length ? `${lines.length} 项物资` : '父单'}</h3>
          <p className="subtle">{warehouseName(order.warehouseId)} · 父单 #{order.id}</p>
          {!lines ? <p className="subtle" role="status">正在读取套料明细…</p> : lines.length === 0
            ? <p className="subtle">套料明细读取失败，请刷新后重试。</p>
            : <ul className="kit-lines">{lines.map((line) => <li key={line.id}><span>{line.itemName} · {line.itemNo}</span><b>{line.quantity} {line.unit}</b><span className="subtle">{line.issueNo} · 明细库存 v{line.inventoryVersion}</span></li>)}</ul>}
          <div className="issue-meta"><span>领用时间 {formatTime(order.issuedAt)}</span>{order.returnedAt ? <span>退回时间 {formatTime(order.returnedAt)}</span> : null}{order.reasonText ? <span>用途：{order.reasonText}</span> : null}</div>
          {order.permissions.canReturn && order.status === 'ISSUED' ? <button className="button secondary" data-test="kit-return" data-order-id={order.id} disabled={busyOrderId !== null} onClick={() => void returnOrder(order)}><CornerDownLeft size={15} />{busyOrderId === order.id ? '正在退回…' : '整单退回套料'}</button> : null}
        </article>;
      })}</div></section> : null}
      {plainIssues.length > 0 ? <section className="issue-group"><h3 className="group-title">单物资领用 · {plainIssues.length} 单</h3><div className="issue-cards">{plainIssues.map((issue) => {
        const inventory = stockMap.get(issue.inventoryId);
        return <article className="issue-card" key={issue.id} data-test="issue-card" data-issue-id={issue.id}><div className="issue-card-top"><strong>{issue.issueNo}</strong><span className={`badge ${issue.status === 'ISSUED' ? 'amber' : ''}`}>{issue.status === 'ISSUED' ? '已领用' : '已退回'}</span></div><h3>{issue.itemName ?? inventory?.itemName ?? `物资 #${issue.itemId}`}</h3><p className="subtle">{issue.warehouseName ?? inventory?.warehouseName ?? `仓库 #${issue.warehouseId}`}</p><div className="issue-meta"><span>领用数量 <b>{issue.quantity}</b>{` ${issue.unit ?? inventory?.unit ?? ''}`} </span><span>领用时间 {formatTime(issue.issuedAt)}</span>{issue.returnedAt ? <span>退回时间 {formatTime(issue.returnedAt)}</span> : null}</div>{issue.reasonText ? <p className="issue-reason">用途：{issue.reasonText}</p> : null}{issue.permissions.canReturn && issue.status === 'ISSUED' ? <button className="button secondary" data-test="issue-return" data-issue-id={issue.id} disabled={busyId !== null} onClick={() => void returnIssue(issue)}><CornerDownLeft size={15} />{busyId === issue.id ? '正在退回…' : '整单退回'}</button> : null}</article>;
      })}</div></section> : null}
    </>}
  </section>;
}
