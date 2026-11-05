import assert from 'node:assert/strict';
import test from 'node:test';
import { createApi } from '../src/api.ts';
import { createKitOrder, returnKitOrder } from '../src/kitOrder.ts';

test('a kit issue submits every line with the version the page shows', async () => {
  const saved = globalThis.fetch;
  const requests: { path: string; body?: unknown }[] = [];
  globalThis.fetch = async (input, init) => {
    requests.push({ path: String(input), body: init?.body ? JSON.parse(String(init.body)) : undefined });
    return new Response(JSON.stringify({ order: { id: 41, orderNo: 'KIT-1' }, lines: [], inventories: [] }), { status: 201 });
  };
  try {
    await createKitOrder(createApi('engineer'), {
      warehouseId: 4101, reasonText: '夜班更换',
      lines: [{ inventoryId: 8101, quantity: 2, version: 3 }, { inventoryId: 8107, quantity: 1, version: 0 }],
    });
    assert.deepEqual(requests, [{
      path: '/api/material-issue-orders',
      body: { warehouseId: 4101, reasonText: '夜班更换', lines: [{ inventoryId: 8101, quantity: 2, version: 3 }, { inventoryId: 8107, quantity: 1, version: 0 }] },
    }]);
  } finally { globalThis.fetch = saved; }
});

test('a whole-kit return uses the original line set read from the parent detail', async () => {
  const saved = globalThis.fetch;
  const requests: { path: string; method: string; body?: unknown }[] = [];
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    requests.push({ path, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path === '/api/material-issue-orders/41') {
      return new Response(JSON.stringify({
        order: { id: 41, orderNo: 'KIT-1', version: 2, status: 'ISSUED', permissions: { canReturn: true } },
        lines: [
          { id: 501, inventoryId: 8107, inventoryVersion: 5, quantity: 1 },
          { id: 500, inventoryId: 8101, inventoryVersion: 8, quantity: 2 },
        ],
      }), { status: 200 });
    }
    return new Response(JSON.stringify({ order: { id: 41, orderNo: 'KIT-1' }, lines: [], inventories: [] }), { status: 200 });
  };
  try {
    await returnKitOrder(createApi('engineer'), 41);
    assert.deepEqual(requests, [
      { path: '/api/material-issue-orders/41', method: 'GET', body: undefined },
      {
        path: '/api/material-issue-orders/41/return', method: 'POST',
        body: { orderVersion: 2, lines: [{ inventoryId: 8107, inventoryVersion: 5 }, { inventoryId: 8101, inventoryVersion: 8 }] },
      },
    ]);
  } finally { globalThis.fetch = saved; }
});
