import type { Api } from './api';
import type { KitOrderDetail, KitOrderResult } from './types';

export interface KitLineInput { inventoryId: number; quantity: number; version: number }

/** One atomic kit issue: every line is submitted together with the version the page shows. */
export function createKitOrder(api: Api, input: { warehouseId: number; reasonText: string; lines: KitLineInput[] }, signal?: AbortSignal) {
  return api.post<KitOrderResult>('/api/material-issue-orders', input, signal);
}

/** Read the real detail first, so the whole-kit return carries exactly the original line set. */
export async function returnKitOrder(api: Api, orderId: number, signal?: AbortSignal) {
  const detail = await api.get<KitOrderDetail>(`/api/material-issue-orders/${orderId}`, {}, signal);
  return api.post<KitOrderResult>(`/api/material-issue-orders/${orderId}/return`, {
    orderVersion: detail.order.version,
    lines: detail.lines.map((line) => ({ inventoryId: line.inventoryId, inventoryVersion: line.inventoryVersion })),
  }, signal);
}
