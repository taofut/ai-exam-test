import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError, createApi } from '../src/api.ts';

test('API calls send the employee number as identity and preserve native failure codes', async () => {
  const originalFetch = globalThis.fetch;
  let header: string | null = null;
  globalThis.fetch = async (_input, init) => {
    header = new Headers(init?.headers).get('X-User');
    return new Response(JSON.stringify({ code: 'NOT_IMPLEMENTED', message: '领用能力待完成' }), { status: 501 });
  };
  try {
    await assert.rejects(createApi('employee-variant').post('/api/inventories/79/issue', { quantity: 2 }), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.code, 'NOT_IMPLEMENTED');
      assert.equal(error.status, 501);
      assert.equal(error.message, '领用能力待完成');
      return true;
    });
    assert.equal(header, 'employee-variant');
  } finally { globalThis.fetch = originalFetch; }
});

test('read filters are encoded without discarding false or numeric IDs', async () => {
  const originalFetch = globalThis.fetch;
  let url = '';
  globalThis.fetch = async (input) => {
    url = String(input);
    return new Response(JSON.stringify({ items: [] }), { status: 200 });
  };
  try {
    await createApi('reader').get('/api/inventories', { deptId: 81, warehouseId: 90, belowReorderPoint: false });
    const query = new URL(url, 'http://localhost').searchParams;
    assert.equal(query.get('deptId'), '81');
    assert.equal(query.get('warehouseId'), '90');
    assert.equal(query.get('belowReorderPoint'), 'false');
  } finally { globalThis.fetch = originalFetch; }
});

