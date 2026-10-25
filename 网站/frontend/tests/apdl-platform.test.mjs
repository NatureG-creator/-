import test from 'node:test';
import assert from 'node:assert/strict';
import {apdlDefaults,buildApdlPayload,renderApdlResult,loadedApdlDraft,createApdlDraftState} from '../apdl.mjs';
import {renderPlatformReport,platformFields} from '../apdl_platform.mjs';

function draft(){const d=apdlDefaults();Object.assign(d.options,{corrosion_mode:'single_top',platform_enabled:true,platform_top_mean_depth_mm:'.8',thickness_layer_mode:'intermediate_nodes',intermediate_node_layers:'10'});d.top={origin:'upload',upload_id:'a',source_kind:'measured',mapping:{dx_mm:'.3',dy_mm:'.3'}};return d;}
test('platform payload records exact lengths and converts intermediate nodes to element layers',()=>{
 const p=buildApdlPayload(draft());
 assert.equal(p.options.layers,11);assert.equal(p.options.intermediate_node_layers,10);
 assert.equal(p.options.platform_fixed_mm,2.5);assert.equal(p.options.platform_loaded_mm,2.5);
 assert.equal(p.options.platform_top_mean_depth_mm,.8);assert.equal(p.options.platform_bottom_mean_depth_mm,null);
});

test('empirical reference selects a completed cloud task without requiring a manual mean or matrix mapping',()=>{
 const d=apdlDefaults();Object.assign(d.options,{corrosion_mode:'single_top',platform_enabled:true,platform_reference_mode:'empirical_190'});
 d.top={source_job_id:'b244ce81367e4817'};
 const payload=buildApdlPayload(d);
 assert.equal(payload.options.platform_reference_mode,'empirical_190');
 assert.deepEqual(payload.top_source,{source_job_id:'b244ce81367e4817',source_kind:'measured'});
 assert.equal(payload.options.platform_top_mean_depth_mm,null);
 assert.equal(apdlDefaults().options.platform_reference_mode,'manual_mean');
 d.options.corrosion_mode='double_symmetric';assert.throws(()=>buildApdlPayload(d),/仅支持单面/);
});

test('empirical precheck requires an explicitly empirical numerically verified report',()=>{
 const d=apdlDefaults();Object.assign(d.options,{corrosion_mode:'single_top',platform_enabled:true,platform_reference_mode:'empirical_190'});d.top={source_job_id:'b244ce81367e4817'};
 const state=createApdlDraftState(d),payload=buildApdlPayload(d);
 const p={enabled:true,calibration_method:'empirical_reference_preserved',physical_pristine_reference_verified:false,fixed_flat_length_mm:2.5,loaded_flat_length_mm:2.5,platform_separation_mm:6,reference_calibrations:{top:{numerical_chain_verified:true}},faces:{top:{active:true,measured_mean_depth_mm:null}}};
 const result={options:payload.options,stats:{platforms:p}};
 assert.equal(state.acceptPrecheck(result,state.revision,payload),payload);
 p.physical_pristine_reference_verified=true;assert.throws(()=>state.acceptPrecheck(result,state.revision,payload),/未确认经验参考/);
});

test('empirical result discloses the light corrosion assumption and never calls its mean a measured target',()=>{
 const p={enabled:true,calibration_method:'empirical_reference_preserved',platform_bottom_z_mm:0,platform_top_z_mm:6,platform_separation_mm:6,reference_calibrations:{top:{source_job_id:'source',reference_height_mm:.1,full_reproduction_max_error_mm:1e-13}},faces:{top:{calibrated_sample_mean_depth_mm:.37}}};
 const html=renderPlatformReport(p);
 for(const text of ['20%经验参考','真实零腐蚀面未验证','不做均值二次平移','输出经验平均深度','单面模型假设'])assert.ok(html.includes(text),text);
 assert.doesNotMatch(html,/均值校准：/);
});
test('platform payload rejects missing measured values, incompatible mode and invalid node counts',()=>{
 for(const changes of [{platform_top_mean_depth_mm:''},{platform_top_mean_depth_mm:true},{local_corrosion:true},{mesh_type:'solid187_tetra'},{intermediate_node_layers:'2.5'},{intermediate_node_layers:true},{platform_loaded_mm:0}]){
  const d=draft();Object.assign(d.options,changes);assert.throws(()=>buildApdlPayload(d));
 }
});
test('old backend cannot silently drop requested platforms or intermediate-node counting',()=>{
 const d=draft(),state=createApdlDraftState(d),p=buildApdlPayload(d);
 assert.throws(()=>state.acceptPrecheck({options:{tensile_direction:'X'}},state.revision,p),/服务端未确认/);
 const noPlatforms=buildApdlPayload({...d,options:{...d.options,platform_enabled:false}});
 assert.throws(()=>state.acceptPrecheck({options:{layers:10}},state.revision,noPlatforms),/中间节点/);
});

test('precheck requires the new mean-calibration method and a matching reported mean',()=>{
 const d=draft(),state=createApdlDraftState(d),payload=buildApdlPayload(d);
 const p={enabled:true,calibration_method:'sample_mean_translation',fixed_flat_length_mm:2.5,loaded_flat_length_mm:2.5,platform_separation_mm:6,faces:{top:{active:true,measured_mean_depth_mm:.8,calibrated_sample_mean_depth_mm:.8}}};
 const result={options:payload.options,stats:{platforms:p}};
 assert.equal(state.acceptPrecheck(result,state.revision,payload),payload);
 delete p.calibration_method;assert.throws(()=>state.acceptPrecheck(result,state.revision,payload),/尚未采用实测平均深度校准/);
 p.calibration_method='sample_mean_translation';p.faces.top.calibrated_sample_mean_depth_mm=.5;
 assert.throws(()=>state.acceptPrecheck(result,state.revision,payload),/平均深度与实测输入不一致/);
});
test('saved configuration retains platform values and legacy drafts default to disabled',()=>{
 assert.equal(loadedApdlDraft(draft()).options.platform_top_mean_depth_mm,'.8');
 assert.equal(loadedApdlDraft({options:{layers:8}}).options.platform_enabled,false);
 assert.equal(buildApdlPayload({...draft(),options:{...draft().options,platform_enabled:false,thickness_layer_mode:'element_layers',layers:8}}).options.layers,8);
});
test('historical platform report retains its old formula and is never presented as mean calibrated',()=>{
 const p={enabled:true,tensile_direction:'X',fixed_flat_length_mm:2.5,loaded_flat_length_mm:2.5,transition_length_each_mm:.3,source_axial_range_mm:[2.8,62.5],platform_bottom_z_mm:0,platform_top_z_mm:6,platform_separation_mm:6,fixed_platform_spacing_mm:2.5/9,loaded_platform_spacing_mm:2.5/9,faces:{top:{active:true,measured_mean_depth_mm:.8,normalized_outward_min_height_mm:-.6,normalized_platform_reference_height_mm:.2,calibrated_sample_mean_depth_mm:.5}}};
 const html=renderPlatformReport(p);assert.match(html,/2.5/);assert.match(html,/0.3/);assert.match(html,/历史算法/);assert.match(html,/未按新公式重算/);assert.match(html,/校准后采样平均深度/);
 assert.match(renderApdlResult({stats:{platforms:p}}),/两侧平台与参考高度核验/);
 assert.equal(renderPlatformReport(null),'');
});

test('new platform report and input help consistently explain mean translation and its scope',()=>{
 const p={enabled:true,calibration_method:'sample_mean_translation',tensile_direction:'X',source_axial_range_mm:[2.8,3.4],faces:{top:{active:true,measured_mean_depth_mm:.8,input_sample_mean_depth_mm:.3,depth_shift_mm:.5,calibrated_sample_mean_depth_mm:.8,mean_calibration_error_mm:0}}};
 const html=renderPlatformReport(p);
 for(const label of ['均值校准','原采样平均深度','向内深度平移量','均值误差','连接段不计入均值'])assert.ok(html.includes(label),label);
 assert.doesNotMatch(html,/历史算法|不保证|最低高程/);
 const fields=platformFields({input:(key,label,help)=>`${label} ${help}`,check:()=>'',select:()=>''});
 assert.match(fields,/原深度 − 腐蚀区采样平均深度 \+ 实测平均深度/);
 assert.match(fields,/新增平台与连接段不参与均值/);
 assert.doesNotMatch(fields,/min\(h\)|不保证/);
});
