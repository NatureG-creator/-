import test from 'node:test';
import assert from 'node:assert/strict';
import {apdlDefaults,buildApdlPayload,applyApdlPreset} from '../apdl.mjs';
import {fractureDefaults,validateFractureDraft,renderFractureResult} from '../apdl_fracture.mjs';

const options=()=>({...fractureDefaults,damage_model:'gissmo',material_model:'multilinear_iso',large_deflection:true,mesh_type:'solid185_hex',boundary_mode:'poisson_free',plastic_curve:[[0,300],[.5,650]],corrosion_mode:'flat'});

test('damage is off by default and an old preset clears it',()=>{
 const draft=apdlDefaults();assert.equal(draft.options.damage_model,'none');
 draft.options.damage_model='gissmo';
 assert.equal(applyApdlPreset(draft,{id:'elastic_flat',options:{material_model:'elastic'}}).options.damage_model,'none');
});
test('damage tables are numeric, ordered, and separate from plastic hardening',()=>{
 const o=options();validateFractureDraft(o);assert.equal(o.damage_failure_curve.length,5);
 for(const change of [{loading_time_s:0},{damage_failure_curve:'[[0,-1],[1,1]]'}, {damage_output_intervals:5},{large_deflection:false},{damage_damping_per_s:-1},{plastic_curve:[[0,300],[.1,200]]}]){
  assert.throws(()=>validateFractureDraft({...options(),...change}));
 }
});
test('payload preserves damage settings and input tables',()=>{
 const draft=apdlDefaults();Object.assign(draft.options,options());
 const payload=buildApdlPayload(draft,'build');assert.equal(payload.options.damage_model,'gissmo');
 assert.equal(payload.options.density_tonne_mm3,7.85e-9);assert.ok(Array.isArray(payload.options.damage_size_curve));
});
test('result distinguishes complete fracture from isolated deletion and escapes content',()=>{
 const summary={results:{fracture:{parameter_basis:'example',fracture_confirmed:false,deleted_elements:1,note:'<script>'},warnings:[]}};
 let html=renderFractureResult(summary,{id:'abc'});assert.match(html,/src="\/api\/jobs\/abc\/view\/engineering_stress_strain.png"/);assert.match(html,/href="\/api\/jobs\/abc\/download\/force_displacement.csv"/);assert.match(html,/尚未确认完整断裂/);assert.match(html,/示例参数/);assert.ok(!html.includes('<script>'));
 summary.results.fracture.fracture_confirmed=true;
 assert.match(renderFractureResult(summary,{id:'abc'}),/已通过数值断开检查/);
});
