import assert from 'node:assert/strict';
import test from 'node:test';
import { ApiError, createApi } from '../src/api.ts';
import { returnMaterialIssue } from '../src/returnIssue.ts';

test('a visible issue submits the versions returned by its current detail', async () => {
  const originalFetch = globalThis.fetch;
  const requests: { path: string; method: string; body?: unknown }[] = [];
  globalThis.fetch = async (input, init) => {
    const path = String(input);
    requests.push({ path, method: init?.method ?? 'GET', body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (path === '/api/material-issues/703') return new Response(JSON.stringify({ id: 703, inventoryId: 901, version: 4, inventoryVersion: 12, permissions: { canReturn: true } }), { status: 200 });
    if (path === '/api/material-issues/703/return') return new Response(JSON.stringify({ code: 'NOT_IMPLEMENTED', message: '整单退回能力待完成' }), { status: 501 });
    throw new Error(`Unexpected request: ${path}`);
  };
  try {
    await assert.rejects(returnMaterialIssue(createApi('engineer'), 703), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.code, 'NOT_IMPLEMENTED');
      assert.equal(error.status, 501);
      return true;
    });
    assert.deepEqual(requests, [
      { path: '/api/material-issues/703', method: 'GET', body: undefined },
      { path: '/api/material-issues/703/return', method: 'POST', body: { issueVersion: 4, inventoryVersion: 12 } },
    ]);
  } finally { globalThis.fetch = originalFetch; }
});
