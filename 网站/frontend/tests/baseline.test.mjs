import test from 'node:test';
import assert from 'node:assert/strict';
import {baselineOptions,baselineApdlDraft,renderBaselineResult} from '../baseline.mjs';
import {buildApdlPayload} from '../apdl.mjs';

test('conversion requires explicit units and an odd smoothing window',()=>{
 const fields={space_xy_um:'25',space_z_um:'25',window_size:'15',gaussian_sigma:'1.5'};
 assert.equal(baselineOptions(fields).space_xy_um,25);
 for(const update of [{space_xy_um:''},{space_z_um:0},{window_size:2},{gaussian_sigma:'NaN'}])assert.throws(()=>baselineOptions({...fields,...update}));
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
