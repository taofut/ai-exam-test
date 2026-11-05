import { useState, type FormEvent } from 'react';
import { ChevronRight, Filter } from 'lucide-react';
import type { Inventory } from '../types';
import { EmptyState } from './Feedback';

export interface InventoryFilters { deptId: string; warehouseId: string; itemId: string; belowReorderPoint: boolean }
interface Props {
  items: Inventory[] | null; catalog: Inventory[]; loading: boolean; error: string; selectedId?: number;
  filters: InventoryFilters; onFilter: (value: InventoryFilters) => void; onSelect: (id: number) => void; onRetry: () => void;
}

export default function InventoryList({ items, catalog, loading, error, selectedId, filters, onFilter, onSelect, onRetry }: Props) {
  const [draft, setDraft] = useState(filters);
  const warehouses = [...new Map(catalog.map((item) => [item.warehouseId, `${item.warehouseName} · ${item.deptName}`])).entries()];
  const materialItems = [...new Map(catalog.map((item) => [item.itemId, `${item.itemName} · ${item.itemNo}`])).entries()];
  function submit(event: FormEvent) { event.preventDefault(); onFilter({ ...draft }); }
  return <section className="list-pane" aria-label="库存列表">
    <form className="filter-form" onSubmit={submit}>
      <div className="section-heading"><h2>可见库存</h2><span>{loading ? '加载中' : items ? `${items.length} 条` : '未知'}</span></div>
      <div className="filter-grid">
        <label>仓库<select aria-label="筛选仓库" value={draft.warehouseId} onChange={(event) => setDraft({ ...draft, warehouseId: event.target.value })}><option value="">全部仓库</option>{warehouses.map(([id, name]) => <option key={id} value={id}>{name} · #{id}</option>)}</select></label>
        <label>物资<select aria-label="筛选物资" value={draft.itemId} onChange={(event) => setDraft({ ...draft, itemId: event.target.value })}><option value="">全部物资</option>{materialItems.map(([id, name]) => <option key={id} value={id}>{name} · #{id}</option>)}</select></label>
        <label className="dept-filter">部门 ID<input aria-label="筛选部门 ID" type="number" min="1" step="1" placeholder="全部可见部门" value={draft.deptId} onChange={(event) => setDraft({ ...draft, deptId: event.target.value })} /></label>
      </div>
      <div className="filter-actions"><label className="check-label"><input type="checkbox" checked={draft.belowReorderPoint} onChange={(event) => setDraft({ ...draft, belowReorderPoint: event.target.checked })} />低于补货点</label><button className="button secondary" type="submit"><Filter size={14} />筛选</button></div>
    </form>
    <div data-test="inventory-list" className="inventory-list" aria-busy={loading}>
      {loading ? <EmptyState text="正在读取库存…" loading /> : error ? <div className="list-error"><EmptyState text={error} /><button className="button secondary" onClick={onRetry}>重试</button></div> : items?.length ? items.map((item) => <button key={item.id} className={`inventory-row ${item.id === selectedId ? 'selected' : ''}`} data-test="inventory-row" data-inventory-id={item.id} onClick={() => onSelect(item.id)} aria-pressed={item.id === selectedId}>
        <div className="row-top"><span className="inventory-ref">#{item.id} · {item.warehouseName} · {item.deptName}</span>{item.onHand < item.reorderPoint ? <span className="badge amber">待补货</span> : <span className="badge">库存正常</span>}</div>
        <div className="row-title"><h3>{item.itemName}</h3><ChevronRight size={16} /></div>
        <p className="subtle">{item.itemNo}</p>
        <div className="row-bottom"><span>现有 <strong>{item.onHand}</strong> {item.unit}</span><span>补货点 {item.reorderPoint}</span></div>
      </button>) : <EmptyState text="没有符合筛选条件的可见库存" />}
    </div>
  </section>;
}
