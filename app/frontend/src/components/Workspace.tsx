import { useEffect, useMemo, useState } from 'react';
import { ArrowRightLeft, Boxes, ClipboardList, FileText, RefreshCw } from 'lucide-react';
import { createApi, describeError, isAbort } from '../api';
import type { Inventory, IssueStats, MaterialIssue, User } from '../types';
import { useRequestScope } from '../useRequestScope';
import { EmptyState } from './Feedback';
import InventoryList, { type InventoryFilters } from './InventoryList';
import InventoryDetail from './InventoryDetail';
import IssueList from './IssueList';
import CandidateEntry, { type CandidatePage } from './CandidateEntry';

type Page = 'inventory' | 'issues' | CandidatePage;
const pageTitles: Record<Page, string> = { inventory: '库存中心', issues: '我的领用', knowledge: '备件保障研判', workbench: '调拨助手' };
const emptyFilters: InventoryFilters = { deptId: '', warehouseId: '', itemId: '', belowReorderPoint: false };

export default function Workspace({ user }: { user: User }) {
  const api = useMemo(() => createApi(user.employeeNo), [user.employeeNo]);
  const scope = useRequestScope();
  const [me, setMe] = useState<User | null>(null);
  const [page, setPage] = useState<Page>('inventory');
  const [inventories, setInventories] = useState<Inventory[] | null>(null);
  const [catalog, setCatalog] = useState<Inventory[]>([]);
  const [inventoryError, setInventoryError] = useState('');
  const [inventoryLoading, setInventoryLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | undefined>();
  const [filters, setFilters] = useState(emptyFilters);
  const [issues, setIssues] = useState<MaterialIssue[] | null>(null);
  const [issuesError, setIssuesError] = useState('');
  const [stats, setStats] = useState<IssueStats | null>(null);
  const [statsError, setStatsError] = useState('');
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const lease = scope.begin('session');
    api.get<User>('/api/session/me', {}, lease.signal).then((value) => { if (lease.isCurrent()) setMe(value); })
      .catch(() => {}).finally(lease.finish);
    return () => scope.cancelAll();
  }, [api, scope]);

  useEffect(() => {
    const lease = scope.begin('inventories');
    setInventoryLoading(true);
    setInventoryError('');
    api.get<{ items: Inventory[] }>('/api/inventories', {
      deptId: filters.deptId || undefined, warehouseId: filters.warehouseId || undefined,
      itemId: filters.itemId || undefined, belowReorderPoint: filters.belowReorderPoint || undefined,
    }, lease.signal).then((value) => {
      if (!lease.isCurrent()) return;
      setInventories(value.items);
      if (!filters.deptId && !filters.warehouseId && !filters.itemId && !filters.belowReorderPoint) setCatalog(value.items);
    }).catch((error: unknown) => { if (lease.isCurrent() && !isAbort(error)) { setInventories(null); setInventoryError(describeError(error)); } })
      .finally(() => { if (lease.isCurrent()) setInventoryLoading(false); lease.finish(); });
  }, [api, scope, filters, refresh]);

  useEffect(() => {
    const issueLease = scope.begin('issues');
    const statsLease = scope.begin('stats');
    setIssues(null); setStats(null); setIssuesError(''); setStatsError('');
    const issueRequest = api.get<{ items: MaterialIssue[] }>('/api/material-issues', { mine: true }, issueLease.signal)
      .then((value) => { if (issueLease.isCurrent()) setIssues(value.items); })
      .catch((error: unknown) => { if (issueLease.isCurrent() && !isAbort(error)) setIssuesError(describeError(error)); }).finally(issueLease.finish);
    const statsRequest = api.get<IssueStats>('/api/material-issues/stats', { period: 'TODAY' }, statsLease.signal)
      .then((value) => { if (statsLease.isCurrent()) setStats(value); })
      .catch((error: unknown) => { if (statsLease.isCurrent() && !isAbort(error)) setStatsError(describeError(error)); }).finally(statsLease.finish);
    void Promise.all([issueRequest, statsRequest]);
  }, [api, scope, refresh]);

  const selection = inventories?.some((item) => item.id === selectedId) ? selectedId : inventories?.[0]?.id;
  const refreshData = () => setRefresh((value) => value + 1);

  return <>
    <nav className="sidebar" aria-label="备件导航">
      <button className={`nav-item ${page === 'inventory' ? 'active' : ''}`} onClick={() => setPage('inventory')}><Boxes size={18} /><span>库存中心</span></button>
      <button className={`nav-item ${page === 'issues' ? 'active' : ''}`} onClick={() => setPage('issues')}><ClipboardList size={18} /><span>我的领用</span>{issues ? <b>{issues.length}</b> : null}</button>
      <button className={`nav-item ${page === 'knowledge' ? 'active' : ''}`} onClick={() => setPage('knowledge')}><FileText size={18} /><span>保障研判</span></button>
      <button className={`nav-item ${page === 'workbench' ? 'active' : ''}`} onClick={() => setPage('workbench')}><ArrowRightLeft size={18} /><span>调拨助手</span></button>
      <div className="sidebar-note"><strong>{me?.deptName ?? user.deptName}</strong><span>设备备件工作台</span></div>
    </nav>
    <main className={`main-workspace ${page === 'inventory' ? 'inventory-workspace' : ''}`}>
      <div className="workspace-summary">
        <div><span className="eyebrow">MATERIAL OPERATIONS</span><h1>{pageTitles[page]}</h1></div>
        <div className="summary-right"><div className="today-stat"><span>本日领用 · 北京时间 · 按物资</span><div className="today-groups" data-test="today-issue-total" title={statsError || undefined}>
          {stats ? stats.groups.length > 0 ? stats.groups.map((group) => <div className="today-group" key={`${group.warehouseId ?? 'all'}-${group.itemId}`}><span>{group.name} · {group.itemNo}</span><strong>{group.quantity} <small>{group.unit}</small></strong></div>) : <span>暂无本日领用记录</span> : <span>{statsError ? '未知' : '加载中…'}</span>}
        </div></div>
          <button className="icon-button" aria-label="刷新数据" title="刷新数据" onClick={refreshData}><RefreshCw size={18} /></button></div>
      </div>
      {statsError ? <p className="summary-error" role="alert">本日统计：{statsError}</p> : null}
      {page === 'inventory' ? <div className="inventory-columns">
        <InventoryList items={inventories} catalog={catalog} loading={inventoryLoading} error={inventoryError} selectedId={selection} filters={filters} onFilter={setFilters} onSelect={setSelectedId} onRetry={refreshData} />
        {selection !== undefined ? <InventoryDetail key={selection} api={api} inventoryId={selection} refresh={refresh} onChanged={refreshData} /> : <section className="detail-pane"><EmptyState text={inventoryLoading ? '正在加载库存…' : '选择一条库存查看详情'} loading={inventoryLoading} /></section>}
      </div> : page === 'issues' ? <IssueList api={api} issues={issues} catalog={catalog} error={issuesError} refresh={refresh} onChanged={refreshData} /> : <CandidateEntry key={page} page={page} />}
    </main>
  </>;
}
