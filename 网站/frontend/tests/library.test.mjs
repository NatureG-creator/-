import test from 'node:test';
import assert from 'node:assert/strict';
import {libraryImportTarget} from '../project_library.mjs';

test('成果库仅为已接入的文件类型选择对应工作流',()=>{
  for(const extension of ['.csv','.txt','.tsv','.xlsx','.xls'])assert.equal(libraryImportTarget(extension),'fitting-panel');
  for(const extension of ['.mat','.npz','.xyz'])assert.equal(libraryImportTarget(extension),'visualization-panel');
  assert.equal(libraryImportTarget('.png'),null);
});
