import test from 'node:test';
import assert from 'node:assert/strict';
import {apdlDefaults,buildApdlPayload,createApdlDraftState,createFaceUploadManager,applyApdlPreset} from '../apdl.mjs';

const info={default_variable:'a_sd',geometry:{space_xy_um:40},variables:[{name:'a_sd',supported:true,stage_count:2,shape:[2,2,3,5],state_shape:[2,3,5]}],warnings:[]};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

test('外部NPZ payload继承文件尺寸、补填缺失Z尺寸并选择阶段',()=>{
 const d=apdlDefaults();d.options.corrosion_mode='single_top';d.top={origin:'upload_npz',upload_id:'external',source_job_id:'stale',source_kind:'measured',npz_info:info,npz_variable:'a_sd',npz_stage:'1',space_z_um:'25',mapping:{unit:'um',value_mode:'height',center_crop_columns:193,dx_mm:99,reference_height:'-'}};
 const p=buildApdlPayload(d).top_source;
 assert.equal(p.source_kind,'simulation');assert.equal(p.upload_id,'external');assert.equal(p.source_job_id,undefined);
 assert.deepEqual(p.cell_geometry,{space_z_um:25});assert.equal(p.mapping.npz_stage,1);assert.equal(p.mapping.npz_variable,'a_sd');
 assert.equal(p.mapping.dx_mm,undefined);assert.equal(p.mapping.center_crop_columns,undefined);assert.equal(p.mapping.value_mode,'depth');assert.equal(p.mapping.unit,'mm');
 delete d.top.space_z_um;assert.throws(()=>buildApdlPayload(d),/尺寸/);
});

test('切换外部读取方式清除旧上传检查、尺寸和阶段，且强制模拟类型',()=>{
 const s=createApdlDraftState();Object.assign(s.draft.top,{origin:'upload',upload_id:'old',npz_info:info,npz_variable:'a_sd',npz_stage:'2',space_z_um:'123'});
 s.update('source','origin','upload_npz','top');assert.equal(s.draft.top.source_kind,'simulation');
 for(const key of ['upload_id','npz_info','npz_variable','npz_stage','space_z_um'])assert.equal(s.draft.top[key],undefined,key);
});

test('NPZ检查响应同上传世代绑定，不能覆写较新文件',async()=>{
 const d=apdlDefaults(),manager=createFaceUploadManager(),old=deferred(),fresh=deferred();d.top.origin='upload_npz';
 const a=manager.run('top',()=>d.top,old.promise,'old.npz');const b=manager.run('top',()=>d.top,fresh.promise,'new.npz');
 fresh.resolve({id:'new',npz_info:info});assert.equal(await b,true);assert.equal(d.top.npz_variable,'a_sd');assert.equal(d.top.npz_stage,2);assert.equal(d.top.npz_info,info);
 old.resolve({id:'old',npz_info:{...info,geometry:{space_xy_um:999}}});assert.equal(await a,false);assert.equal(d.top.upload_id,'new');assert.equal(d.top.npz_info.geometry.space_xy_um,40);assert.equal(manager.pending,0);
});

test('对象历史不可选、越界阶段拒绝、切换状态变量清除阶段',()=>{
 const state=createApdlDraftState(),d=state.draft;d.options.corrosion_mode='single_top';Object.assign(d.top,{origin:'upload_npz',upload_id:'x',npz_info:info,npz_variable:'a_sd',npz_stage:3,space_z_um:25});
 assert.throws(()=>buildApdlPayload(d),/阶段/);d.top.npz_variable='perfect_a';assert.throws(()=>buildApdlPayload(d),/变量/);
 state.update('source','npz_variable','a_sd','top');assert.equal(d.top.npz_stage,undefined);
});

test('原实测双面预设不能将外部NPZ当实测矩阵提交',()=>{
 const d=apdlDefaults();Object.assign(d.top,{origin:'upload_npz',upload_id:'npz',npz_info:info});
 const next=applyApdlPreset(d,{id:'github',name:'原实测',options:{corrosion_mode:'single_top'},top_mapping:{value_mode:'height',dx_mm:.3,dy_mm:.3}});
 assert.equal(next.top.source_kind,'measured');assert.notEqual(next.top.origin,'upload_npz');assert.equal(next.top.upload_id,undefined);assert.throws(()=>buildApdlPayload(next),/来源/);
});
