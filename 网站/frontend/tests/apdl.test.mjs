import test from 'node:test';
import assert from 'node:assert/strict';
import * as apdl from '../apdl.mjs';
import {apdlDefaults,buildApdlPayload,availableSurfaceFiles,renderApdlResult,createFaceUploadManager,applyApdlPreset} from '../apdl.mjs';

test('结果卡区分求解后处理和未核验RST，不把未核验显示成不适用',()=>{
 const pending=renderApdlResult({run_mode:'build',build_state:'pending',stage_states:{geometry:'running'}});
 assert.match(pending,/正在生成几何与网格/);assert.doesNotMatch(pending,/APDL 输入包已生成/);
 assert.match(renderApdlResult({run_mode:'build',build_state:'pending',stage_states:{reading:'running'}}),/正在读取 APDL 来源/);
 assert.match(renderApdlResult({run_mode:'build',build_state:'pending',stage_states:{build:'running'}}),/正在写入 APDL 输入包/);
 assert.match(renderApdlResult({build_state:'built',solve_state:'running'}),/MAPDL 正在求解/);
 assert.match(renderApdlResult({build_state:'built',solve_state:'postprocessing'}),/正在后处理与校核/);
 const html=renderApdlResult({build_state:'built',solve_state:'solved',results:{validation_state:'needs_review',rst_validation:{state:'unverified',reason:'未解析二进制 RST'},checks:{rst_consistency:null,nodal_coordinates:true}}});
 assert.match(html,/RST 内容尚未核验/);assert.match(html,/节点坐标与网格一致/);assert.match(html,/尚未核验/);
 assert.doesNotMatch(html,/MAPDL 正在求解|>校核通过</);
 const failed=renderApdlResult({build_state:'failed',solve_state:'not_started',failure_stage:'geometry',error:'几何无效'});
 assert.match(failed,/APDL 建模失败/);assert.doesNotMatch(failed,/MAPDL 求解失败/);
});

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

// 与实际 input/change 事件共用的草稿入口；不依赖失焦才保存输入。
function draftState(){assert.equal(typeof apdl.createApdlDraftState,'function');return apdl.createApdlDraftState();}
test('同类型任务A切换B时清除旧阶段和MAT文件',()=>{
 const state=draftState(),d=state.draft;d.options.corrosion_mode='single_top';d.top.source_job_id='A';d.top.source_stage='2';d.top.source_file='old.mat';
 state.update('source','source_job_id','B','top');let p=buildApdlPayload(d);
 assert.equal(p.top_source.source_stage,undefined);assert.equal(p.top_source.source_file,undefined);
 d.top.source_kind='measured';d.top.source_job_id='old';d.top.source_file='old.mat';
 state.update('source','source_job_id','new','top');p=buildApdlPayload(d);assert.equal(p.top_source.source_file,undefined);
});
test('来源读取方式和类型改变都清除旧来源限定字段',()=>{
 for(const [key,value] of [['origin','upload'],['source_kind','measured']]){
  const state=draftState(),s=state.draft.top;s.source_job_id='A';s.source_stage='2';s.source_file='old.mat';s.upload_id='old-upload';
  state.update('source',key,value,'top');assert.equal(s.source_job_id,'');assert.equal(s.source_stage,undefined);assert.equal(s.source_file,undefined);
  if(key==='origin')assert.equal(s.upload_id,undefined);
 }
});
test('未失焦原始映射字符串在上传、加载与刷新异步完成后仍可用于渲染和payload',async()=>{
 for(const operation of ['upload','loadJob','refresh']){
  const state=draftState(),d=state.draft,pending=deferred();d.options.corrosion_mode='single_top';d.top.source_kind='measured';d.top.source_job_id='A';
  const completion=pending.promise.then(()=>apdl.apdlMappingDisplay(d.top));
  state.update('map','dx_mm','0.3500','top');state.update('map','dy_mm','0.4500','top');state.update('map','reference_height','-','top');
  pending.resolve();const display=await completion;assert.equal(display.dx_mm,'0.3500',operation);assert.equal(display.reference_height,'-',operation);
  state.update('map','reference_height','2.7500','top');const p=buildApdlPayload(d);assert.equal(p.top_source.mapping.dx_mm,.35);assert.equal(p.top_source.mapping.reference_height,2.75);
 }
});
test('来源、阶段、文件、变量、映射和模式改变取消配准确认',()=>{
 for(const [scope,key,value,face] of [['source','source_job_id','B','top'],['source','source_stage','2','top'],['source','source_file','new.mat','bottom'],['map','variable','Z_filled','top'],['map','flip_x',true,'bottom'],['map','dx_mm','0.4','top'],['option','corrosion_mode','single_top']]){
  const state=draftState();state.draft.registration_confirmed=true;state.update(scope,key,value,face);assert.equal(state.draft.registration_confirmed,false,`${scope}.${key}`);
 }
});
test('材料、加载与同值同步保留配准确认，但真正改值使预检令牌失效',()=>{
 const state=draftState();state.draft.registration_confirmed=true;
 state.acceptPrecheck({registration_signature:'token'},state.revision,{});state.update('option','E_MPa','200000');assert.equal(state.draft.registration_confirmed,true);assert.equal(state.precheck,null);
 state.update('option','target_displacement_mm','0.2');assert.equal(state.draft.registration_confirmed,true);
 state.draft.top.mapping.dx_mm=.3;state.update('map','dx_mm','0.3','top');assert.equal(state.draft.registration_confirmed,true);assert.equal(state.draft.top.mapping.dx_mm,'0.3');
});
test('实测um和height切模拟后显示与payload固定mm及正深度且不展示旧间距',()=>{
 assert.equal(typeof apdl.apdlMappingDisplay,'function');const d=apdlDefaults();d.options.corrosion_mode='single_top';d.top.source_job_id='sim';Object.assign(d.top.mapping,{unit:'um',value_mode:'height',dx_mm:'88',dy_mm:'99',reference_height:'-'});
 const display=apdl.apdlMappingDisplay(d.top),p=buildApdlPayload(d);assert.equal(display.unit,'mm');assert.equal(display.value_mode,'depth');assert.equal(display.dx_mm,'');assert.equal(display.dy_mm,'');assert.equal(p.top_source.mapping.unit,'mm');assert.equal(p.top_source.mapping.value_mode,'depth');assert.equal(p.top_source.mapping.dx_mm,undefined);
 assert.equal(d.top.mapping.unit,'um');assert.equal(d.top.mapping.dx_mm,'88');
});
test('预检只转传后端签名，任何草稿修改拒绝陈旧结果',()=>{
 const state=draftState(),payload={run_mode:'build'},version=state.revision;
 assert.equal(state.acceptPrecheck({registration_signature:'backend-signature'},version,payload),payload);assert.equal(payload.registration_signature,'backend-signature');
 state.update('control','case_name','新名称');assert.equal(state.precheck,null);assert.throws(()=>state.acceptPrecheck({registration_signature:'old'},version,{}),/配置发生变化/);
 const flat={};state.acceptPrecheck({},state.revision,flat);assert.equal(flat.registration_signature,undefined);
});
