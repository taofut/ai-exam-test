import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequestScope } from '../src/requestScope.ts';

test('a newer request cancels and invalidates an earlier response for the same view', () => {
  const scope = createRequestScope();
  const old = scope.begin('inventory');
  const current = scope.begin('inventory');
  assert.equal(old.signal.aborted, true);
  assert.equal(old.isCurrent(), false);
  assert.equal(current.isCurrent(), true);
});

test('identity cleanup invalidates every pending response and allows fresh requests', () => {
  const scope = createRequestScope();
  const stock = scope.begin('stock');
  const suggestion = scope.begin('suggestion');
  scope.cancelAll();
  assert.equal(stock.signal.aborted, true);
  assert.equal(suggestion.isCurrent(), false);
  assert.equal(scope.begin('stock').isCurrent(), true);
});

test('finishing a stale request does not cancel a newer request', () => {
  const scope = createRequestScope();
  const old = scope.begin('agent');
  const current = scope.begin('agent');
  old.finish();
  assert.equal(current.isCurrent(), true);
});
