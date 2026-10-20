import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const css = fs.readFileSync(path.join(root, 'styles.css'), 'utf8');

test('workbench exposes grouped research flow and keeps every workflow panel', () => {
  assert.match(html, /data-layout="product-performs"/);
  for (const label of ['采集与模拟', '验证与拟合', '结果与记录']) assert.match(html, new RegExp(label));
  for (const id of ['pointcloud-panel', 'simulation-panel', 'benchmark-panel', 'finite-element-panel', 'fitting-panel', 'multivariate-panel', 'results-panel', 'history-panel']) {
    assert.match(html, new RegExp(`id="${id}"`));
  }
});

test('workbench defines readable typography and surface tokens', () => {
  for (const token of ['--font-display', '--font-body', '--text-body', '--surface-strong', '--accent']) {
    assert.match(css, new RegExp(token));
  }
});
