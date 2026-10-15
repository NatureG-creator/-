import test from 'node:test';
import assert from 'node:assert/strict';
import {apdlDefaults,buildApdlPayload,availableSurfaceFiles,renderApdlResult,createFaceUploadManager,applyApdlPreset} from '../apdl.mjs';

test('默认弹性平板可直接建模且不附带无关表面',()=>{
 const draft=apdlDefaults(),p=buildApdlPayload(draft,'build');
 assert.equal(p.options.corrosion_mode,'flat');assert.equal(p.options.E_MPa,206000);
 assert.equal(p.run_mode,'build');assert.equal(p.top_source,undefined);assert.equal(p.bottom_source,undefined);
});
test('模拟继承真实间距，阶段使用整数',()=>{
 const d=apdlDefaults();d.options.corrosion_mode='single_top';d.top={source_kind:'simulation',source_job_id:'abc',source_stage:'2',mapping:{dx_mm:'0.3',dy_mm:'0.3',layout:'auto'}};
 const p=buildApdlPayload(d,'build');assert.equal(p.top_source.source_stage,2);assert.equal(p.top_source.mapping.dx_mm,undefined);assert.equal(p.top_source.mapping.dy_mm,undefined);assert.equal(p.top_source.mapping.origin_x_mm,undefined);assert.equal(p.top_source.mapping.origin_y_mm,undefined);
});
test('独立双面要求配准并保留实测映射与文件',()=>{
 const d=apdlDefaults();d.options.corrosion_mode='double_independent';d.top={source_kind:'measured',upload_id:'u',mapping:{dx_mm:'0.3',dy_mm:'0.4',height_sign:'-1',transpose:true}};d.bottom={source_kind:'measured',source_job_id:'b',source_file:'surface.mat',mapping:{dx_mm:'0.3',dy_mm:'0.4'}};
 assert.throws(()=>buildApdlPayload(d,'solve'),/配准/);d.registration_confirmed=true;const p=buildApdlPayload(d,'solve');assert.equal(p.bottom_source.source_file,'surface.mat');assert.equal(p.top_source.mapping.height_sign,-1);assert.equal(p.top_source.mapping.transpose,true);
});
test('拒绝上传缺少间距与无效MISO JSON',()=>{
 const d=apdlDefaults();d.options.corrosion_mode='single_top';d.top={source_kind:'measured',upload_id:'u',mapping:{}};assert.throws(()=>buildApdlPayload(d,'build'),/间距/);
 d.options.corrosion_mode='flat';d.options.material_model='multilinear_iso';d.options.plastic_curve='oops';assert.throws(()=>buildApdlPayload(d,'build'),/JSON/);
});
test('有效MISO二维JSON解析为数值数组，子步约束前置校验',()=>{
 const d=apdlDefaults();d.options.material_model='multilinear_iso';d.options.plastic_curve='[[0,235],[0.1,300]]';assert.deepEqual(buildApdlPayload(d,'build').options.plastic_curve,[[0,235],[0.1,300]]);
 d.options.min_substeps=20;assert.throws(()=>buildApdlPayload(d,'build'),/子步/);
});
test('源文件目录按类型筛选，不将CSV结果当默认MAT',()=>{
 assert.deepEqual(availableSurfaceFiles({kind:'pointcloud',files:['a.mat','force_displacement.csv','b.png']}),['a.mat']);
 assert.deepEqual(availableSurfaceFiles({kind:'simulation',files:['stage_001.npz','simulation.npz','x.mat']}),['stage_001.npz','simulation.npz']);
});
test('旧有限元任务默认继承原点和行列约定，明确输入时允许覆盖',()=>{
 const d=apdlDefaults();d.options.corrosion_mode='single_top';d.top.source_kind='measured';d.top.source_job_id='legacy';let p=buildApdlPayload(d,'build');assert.equal(p.top_source.mapping.origin_x_mm,undefined);assert.equal(p.top_source.mapping.origin_y_mm,undefined);assert.equal(p.top_source.mapping.layout,'auto');d.top.mapping.origin_x_mm='3.5';p=buildApdlPayload(d,'build');assert.equal(p.top_source.mapping.origin_x_mm,3.5);
});
test('建模结果不呈现伪求解，solved与校核通过分开',()=>{
 assert.match(renderApdlResult({solve_state:'built',stats:{node_count:10}}),/未调用 MAPDL/);
 const html=renderApdlResult({solve_state:'solved',validation_state:'needs_review',final_load_n:100,warnings:['<script>']});assert.match(html,/需要复核/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/>校核通过</);
});
test('后端嵌套results校核状态与警告正确显示',()=>{
 const html=renderApdlResult({solve_state:'solved',results:{validation_state:'passed',warnings:['已保存路径'],final_load_n:100}});assert.match(html,/>校核通过</);assert.match(html,/已保存路径/);
});
test('显式来源方式优先于遗留ID且请求只带一种来源',()=>{
 const d=apdlDefaults();d.options.corrosion_mode='single_top';d.top={origin:'task',source_kind:'simulation',source_job_id:'B',upload_id:'stale-A',mapping:{}};const p=buildApdlPayload(d,'build');assert.equal(p.top_source.source_job_id,'B');assert.equal(p.top_source.upload_id,undefined);assert.equal(p.top_source.source_kind,'simulation');d.top.origin='upload';delete d.top.upload_id;assert.throws(()=>buildApdlPayload(d,'build'),/来源/);
});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
test('上传A未结束切换任务B时陈旧响应不能回写来源',async()=>{
 const uploads=createFaceUploadManager(),d=apdlDefaults(),a=deferred();d.top.origin='upload';const pending=uploads.run('top',()=>d.top,a.promise,'A.mat');assert.equal(uploads.pending,1);uploads.invalidate('top');d.top.origin='task';d.top.source_job_id='B';a.resolve({id:'A'});assert.equal(await pending,false);assert.equal(d.top.upload_id,undefined);assert.equal(d.top.source_job_id,'B');assert.equal(uploads.pending,0);
});
test('同一面后发上传先返回时保留新文件且准确累计pending',async()=>{
 const uploads=createFaceUploadManager(),d=apdlDefaults(),a=deferred(),b=deferred();d.top.origin='upload';const pa=uploads.run('top',()=>d.top,a.promise,'A.mat'),pb=uploads.run('top',()=>d.top,b.promise,'B.mat');assert.equal(uploads.pending,2);b.resolve({id:'B'});assert.equal(await pb,true);assert.equal(uploads.pending,1);a.resolve({id:'A'});assert.equal(await pa,false);assert.equal(uploads.pending,0);assert.equal(d.top.upload_id,'B');assert.equal(d.top.upload_name,'B.mat');
});
test('两面并发上传互不失效，过期失败不覆盖当前操作',async()=>{
 const uploads=createFaceUploadManager(),d=apdlDefaults(),a=deferred(),b=deferred();d.top.origin='upload';d.bottom.origin='upload';const pa=uploads.run('top',()=>d.top,a.promise,'A.mat'),pb=uploads.run('bottom',()=>d.bottom,b.promise,'B.mat');uploads.invalidate('top');a.reject(new Error('old failure'));assert.equal(await pa,false);assert.equal(uploads.pending,1);b.resolve({id:'B'});assert.equal(await pb,true);assert.equal(d.bottom.upload_id,'B');assert.equal(uploads.pending,0);
});
test('原双面预设切回弹性预设后手动单双面不残留高度、裁剪与间距',()=>{
 const initial=apdlDefaults();initial.top={...initial.top,origin:'task',source_kind:'measured',source_job_id:'surface-top'};initial.bottom={...initial.bottom,origin:'task',source_kind:'measured',source_job_id:'surface-bottom'};
 const original={id:'github_original_double',name:'原双面',options:{corrosion_mode:'double_independent'},top_mapping:{value_mode:'height',reference_mode:'maximum',layout:'yx',center_crop_columns:193,dx_mm:.3,dy_mm:.3},bottom_mapping:{value_mode:'height',reference_mode:'maximum',layout:'yx',center_crop_columns:193,dx_mm:.3,dy_mm:.3}};
 const before=structuredClone(initial),originalDraft=applyApdlPreset(initial,original);assert.deepEqual(initial,before);assert.equal(originalDraft.top.mapping.center_crop_columns,193);
 const d=applyApdlPreset(originalDraft,{id:'elastic_flat',name:'弹性平板',options:{corrosion_mode:'flat'}});
 for(const face of ['top','bottom']){assert.equal(d[face].mapping.value_mode,'depth');assert.equal(d[face].mapping.layout,'auto');assert.equal(d[face].mapping.reference_mode,'manual');for(const key of ['center_crop_columns','dx_mm','dy_mm','origin_x_mm','origin_y_mm'])assert.equal(d[face].mapping[key],'');}
 d.options.corrosion_mode='single_top';let payload=buildApdlPayload(d,'build');assert.equal(payload.top_source.mapping.center_crop_columns,undefined);assert.equal(payload.top_source.mapping.value_mode,'depth');
 d.options.corrosion_mode='double_independent';d.registration_confirmed=true;payload=buildApdlPayload(d,'build');assert.equal(payload.bottom_source.mapping.center_crop_columns,undefined);assert.equal(payload.bottom_source.mapping.layout,'auto');assert.equal(payload.top_source.source_job_id,'surface-top');assert.equal(payload.bottom_source.source_job_id,'surface-bottom');
});
