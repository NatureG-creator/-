import test from 'node:test';
import assert from 'node:assert/strict';
import {apdlDefaults,buildApdlPayload,renderApdlResult,loadedApdlDraft,createApdlDraftState} from '../apdl.mjs';
import {renderPlatformReport} from '../apdl_platform.mjs';

function draft(){const d=apdlDefaults();Object.assign(d.options,{corrosion_mode:'single_top',platform_enabled:true,platform_top_mean_depth_mm:'.8',thickness_layer_mode:'intermediate_nodes',intermediate_node_layers:'10'});d.top={origin:'upload',upload_id:'a',source_kind:'measured',mapping:{dx_mm:'.3',dy_mm:'.3'}};return d;}
test('platform payload records exact lengths and converts intermediate nodes to element layers',()=>{
 const p=buildApdlPayload(draft());
 assert.equal(p.options.layers,11);assert.equal(p.options.intermediate_node_layers,10);
 assert.equal(p.options.platform_fixed_mm,2.5);assert.equal(p.options.platform_loaded_mm,2.5);
 assert.equal(p.options.platform_top_mean_depth_mm,.8);assert.equal(p.options.platform_bottom_mean_depth_mm,null);
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
test('saved configuration retains platform values and legacy drafts default to disabled',()=>{
 assert.equal(loadedApdlDraft(draft()).options.platform_top_mean_depth_mm,'.8');
 assert.equal(loadedApdlDraft({options:{layers:8}}).options.platform_enabled,false);
 assert.equal(buildApdlPayload({...draft(),options:{...draft().options,platform_enabled:false,thickness_layer_mode:'element_layers',layers:8}}).options.layers,8);
});
test('platform report and results disclose transition, separation and mean-depth distinction',()=>{
 const p={enabled:true,tensile_direction:'X',fixed_flat_length_mm:2.5,loaded_flat_length_mm:2.5,transition_length_each_mm:.3,source_axial_range_mm:[2.8,62.5],platform_bottom_z_mm:0,platform_top_z_mm:6,platform_separation_mm:6,fixed_platform_spacing_mm:2.5/9,loaded_platform_spacing_mm:2.5/9,faces:{top:{active:true,measured_mean_depth_mm:.8,normalized_outward_min_height_mm:-.6,normalized_platform_reference_height_mm:.2,calibrated_sample_mean_depth_mm:.5}}};
 const html=renderPlatformReport(p);assert.match(html,/2.5/);assert.match(html,/0.3/);assert.match(html,/不保证/);assert.match(html,/校准后采样平均深度/);
 assert.match(renderApdlResult({stats:{platforms:p}}),/两侧平台与参考高度核验/);
 assert.equal(renderPlatformReport(null),'');
});
