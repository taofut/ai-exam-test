import assert from 'node:assert/strict';
import test from 'node:test';
import { createApi, ApiError } from '../src/api.ts';

test('kit error transport preserves server line details without converting failure to success', async () => {
  const saved = globalThis.fetch;
  const details = [{ lineIndex: 1, inventoryId: 987, code: 'VERSION_CONFLICT', message: '库存已变化' }];
  globalThis.fetch = async () => new Response(JSON.stringify({ code: 'VERSION_CONFLICT', message: '整单未办理', details }), { status: 409 });
  try {
    await assert.rejects(createApi('variant-user').post('/api/material-issue-orders', {}), (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.deepEqual(error.details, details);
      assert.equal(error.status, 409);
      return true;
    });
  } finally { globalThis.fetch = saved; }
});
