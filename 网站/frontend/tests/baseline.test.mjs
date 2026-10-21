import test from 'node:test';
import assert from 'node:assert/strict';
import {baselineOptions,baselineApdlDraft,renderBaselineResult} from '../baseline.mjs';
import {buildApdlPayload} from '../apdl.mjs';

test('matrix conversion validates original processing parameters without requiring physical units',()=>{
 const fields={window_size:'5',gaussian_sigma:'1',expand_factor:'2',physical_layers:'100'};
 const options=baselineOptions(fields);
 assert.deepEqual(options,{output_variable:'baseline',matrix_only:true,window_size:5,gaussian_sigma:1,expand_factor:2,physical_layers:100});
 for(const update of [{window_size:2},{window_size:''},{gaussian_sigma:-1},{gaussian_sigma:'NaN'},{expand_factor:1.5},{expand_factor:11},{physical_layers:0}])assert.throws(()=>baselineOptions({...fields,...update}));
 const job={id:'a'.repeat(16),state:'completed',spec:{options},result:{shape:[400,160],value_range_cells:[1,100]}};
 const result=renderBaselineResult(job);
 assert.match(result,/400 × 160/);
 assert.match(result,/高斯 sigma 1/);
 assert.match(result,/放大倍数 N 2/);
 assert.match(result,/下载 baseline.mat/);
 assert.doesNotMatch(result,/undefined|元胞尺寸|转入有限元正面/);
 assert.throws(()=>baselineApdlDraft(job),/物理尺寸/);
 const old={...job,spec:{options:{matrix_only:true,output_variable:'baseline',physical_layers:100}}};
 assert.match(renderBaselineResult(old),/高斯 sigma 0/);
});

test('completed MAT transfers its task source and baseline variable into APDL',()=>{
 const job={id:'a'.repeat(16),state:'completed',spec:{case_name:'表面',options:{output_variable:'baseline',space_xy_um:25,space_z_um:25,window_size:15,gaussian_sigma:1.5,npz_variable:'perfect_a',npz_stage:1}}};
 const draft=baselineApdlDraft(job),payload=buildApdlPayload(draft,'build');
 assert.equal(payload.top_source.source_job_id,job.id);
 assert.equal(payload.top_source.source_file,'baseline.mat');
 assert.equal(payload.top_source.mapping.variable,'baseline');
 assert.equal(payload.top_source.mapping.layout,'auto');
 assert.equal(payload.options.corrosion_mode,'single_top');
 const existing=structuredClone(draft);existing.options.E_MPa=185226;existing.options.thickness_mm=8;
 const transferred=baselineApdlDraft(job,existing);
 assert.equal(transferred.options.E_MPa,185226);
 assert.equal(transferred.options.thickness_mm,8);
 assert.match(renderBaselineResult(job),/下载 baseline.mat/);
 assert.match(renderBaselineResult(job),/转入有限元正面/);
 assert.throws(()=>baselineApdlDraft({...job,state:'running'}));
});
