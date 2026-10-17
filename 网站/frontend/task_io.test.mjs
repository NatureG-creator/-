import test from 'node:test';
import assert from 'node:assert/strict';
import {withTaskSettings, taskLabel} from './task_io.mjs';
import {finiteElementPayload} from './state.mjs';
import {readBenchmarkConfiguration} from './benchmark.mjs';

test('all task submissions carry user name and selected output directory', () => {
  const payload={kind:'pointcloud',reference_id:'a',detail_id:'b'};
  const result=withTaskSettings(payload,{name:'  我的试样  ',export_directory:' D:\\研究成果 '});
  assert.equal(result.case_name,'我的试样');
  assert.equal(result.export_directory,'D:\\研究成果');
  assert.equal(result.reference_id,'a');
  assert.equal(payload.case_name,undefined);
});

test('batch case names are preserved and share the chosen export directory', () => {
  const payload={cases:[{case_name:'试样A'},{case_name:'试样B',export_directory:'E:\\单独成果'}]};
  const result=withTaskSettings(payload,{name:'批次',export_directory:'D:\\成果'});
  assert.deepEqual(result.cases.map(c=>c.case_name),['试样A','试样B']);
  assert.deepEqual(result.cases.map(c=>c.export_directory),['D:\\成果','E:\\单独成果']);
  assert.equal(payload.cases[0].export_directory,undefined);
});

test('renamed label wins over frozen case name, with old task fallback', () => {
  assert.equal(taskLabel({display_name:'新名称',spec:{case_name:'旧名称'},id:'id'}),'新名称');
  assert.equal(taskLabel({spec:{case_name:'旧名称'},id:'id'}),'旧名称');
  assert.equal(taskLabel({id:'id'}),'id');
});

test('legacy finite element accepts local uploads without inventing a task id', () => {
  const value=finiteElementPayload({uploadId:'a'.repeat(32),sourceKind:'measured',inputVariable:'F_filled'});
  assert.equal(value.upload_id,'a'.repeat(32));
  assert.equal(value.source_job_id,undefined);
  assert.equal(value.input_variable,'F_filled');
  assert.throws(()=>finiteElementPayload({uploadId:'bad'}),/上传/);
});

test('benchmark imports an independent configuration and six-metric targets', () => {
  const config={GA_CONFIG:{seed:12},GEOMETRY_CONFIG:{grid_w:5},ACTIVE_STAGE_TARGET_DATA:[[1,2,3,4,5,6]]};
  const result=readBenchmarkConfiguration(JSON.stringify({config}));
  assert.deepEqual(result.targets,[[1,2,3,4,5,6]]);
  result.config.GA_CONFIG.seed=34;
  assert.equal(config.GA_CONFIG.seed,12);
  assert.throws(()=>readBenchmarkConfiguration('{}'),/配置/);
  assert.throws(()=>readBenchmarkConfiguration(JSON.stringify({config,targets:[[1,2]]})),/六指标/);
});
