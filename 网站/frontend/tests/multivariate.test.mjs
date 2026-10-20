import test from 'node:test';
import assert from 'node:assert/strict';
import {mountMultivariate} from '../fitting_multivariate.mjs';

async function mount(post) {
  const ids = ['mv-text','mv-file','mv-file-note','mv-preview','mv-x1','mv-x2','mv-y','mv-group','mv-models','mv-metric','mv-folds','mv-seed','mv-inspect','mv-precheck','mv-run','mv-message','mv-check'];
  const nodes = Object.fromEntries(ids.map(id => [id, {value:'', innerHTML:'', hidden:true, addEventListener(){}}]));
  const root = {innerHTML:'', querySelector(selector){return selector.startsWith('#') ? nodes[selector.slice(1)] ?? null : null;}, querySelectorAll(){return [];}};
  const original = globalThis.document;
  globalThis.document = {querySelector(){return root;}};
  try {await mountMultivariate({get:async()=>({multivariate_models:[]}),post,openJob:async()=>{}});}
  finally {if(original===undefined) delete globalThis.document; else globalThis.document=original;}
  return nodes;
}

test('读取双自变量预览后填充所有列选项', async () => {
  const nodes = await mount(async()=>({columns:['X1','X2','Y'],row_count:1,rows:[[1,2,3]]}));
  await nodes['mv-inspect'].onclick();
  assert.equal(nodes['mv-message'].hidden,true);
  for(const id of ['mv-x1','mv-x2','mv-y','mv-group']) assert.match(nodes[id].innerHTML,/value="2">3 · Y/);
});

test('未选择三列时在前端提示且不提交预检', async () => {
  let requests=0;
  const nodes = await mount(async()=>{requests++;return {columns:['X1','X2','Y'],row_count:1,rows:[[1,2,3]]};});
  await nodes['mv-inspect'].onclick();
  await nodes['mv-precheck'].onclick();
  assert.equal(nodes['mv-message'].textContent,'请选择 X1、X2 和 Y 列');
  assert.equal(requests,1);
});
