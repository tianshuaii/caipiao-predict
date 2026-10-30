import { test } from 'node:test';
import assert from 'node:assert/strict';
import { strategyCatalog, strategyName } from '../src/strategies.ts';

test('all sixteen candidates have distinct labels and versioned names resolve exactly', () => {
  const entries = Object.entries(strategyCatalog).filter(([key]) => key !== 'uniform');
  assert.equal(entries.length, 16);
  assert.equal(new Set(entries.map(([, value]) => value.name)).size, 16);
  for (const [key, value] of entries) {
    assert.equal(strategyName(`${key}-v1-0123456789abcdef`), value.name);
    assert.ok(value.features.length > 0);
  }
  assert.equal(strategyName('uniform-v1'), '均匀随机基线');
  assert.equal(strategyName('unknown-v1'), 'unknown-v1');
});
