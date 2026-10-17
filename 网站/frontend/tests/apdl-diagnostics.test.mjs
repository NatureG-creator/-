import test from 'node:test';
import assert from 'node:assert/strict';
import * as apdl from '../apdl.mjs';

test('结果保存默认为完整模式，选定比例明确转换为数值且不改草稿',()=>{
 const d=apdl.apdlDefaults();
 assert.equal(apdl.buildApdlPayload(d).options.result_save_mode,'all');
 d.options.result_save_mode='selected';d.options.field_output_times='0.25, 0.5, 0.75, 1';
 const before=structuredClone(d),p=apdl.buildApdlPayload(d);
 assert.deepEqual(p.options.field_output_times,[.25,.5,.75,1]);assert.deepEqual(d,before);
});
test('选定保存比例拒绝乱序重复越界缺末步及非有限值',()=>{
 for(const raw of ['0.5,0.25,1','0.5,0.5,1','0,1','0.5','NaN,1','1.1,1','', '0.2,,1']){
  const d=apdl.apdlDefaults();d.options.result_save_mode='selected';d.options.field_output_times=raw;
  assert.throws(()=>apdl.buildApdlPayload(d),/比例/);
 }
 const d=apdl.apdlDefaults();d.options.result_save_mode='unknown';assert.throws(()=>apdl.buildApdlPayload(d),/保存模式/);
});
test('末步模式不激活选定比例草稿且保留末步CSV开关',()=>{
 const d=apdl.apdlDefaults();d.options.result_save_mode='last';d.options.field_output_times='未完成';d.options.export_full_field=false;
 const p=apdl.buildApdlPayload(d);assert.equal(p.options.result_save_mode,'last');assert.equal(p.options.export_full_field,false);assert.equal(d.options.field_output_times,'未完成');
 assert.deepEqual(p.options.field_output_times,[.25,.5,.75,1]);
});
test('诊断展示区分估算和实际自检，不将未核验显示通过',()=>{
 assert.equal(typeof apdl.renderApdlDiagnostics,'function');
 const html=apdl.renderApdlDiagnostics({material_coverage:{status:'estimate_only',target_log_strain:.17477,last_plastic_strain:.137798,estimated_last_total_strain:.14115,exceeds_estimated_coverage:true},mesh_quality:{state:'precheck_only',min_scaled_jacobian:.001,worst_elements:[]},output_policy:{result_save_mode:'last'}});
 assert.match(html,/材料覆盖/);assert.match(html,/均匀/);assert.match(html,/积分点/);assert.match(html,/网格质量/);assert.match(html,/未运行/);assert.doesNotMatch(html,/自检通过/);
});
test('真实元素节点筛查显示首次超表位置，且不冒称积分点通过',()=>{
 const html=apdl.renderApdlDiagnostics({material_coverage:{status:'estimate_only',material_model:'multilinear_iso',screening:{state:'flagged',max_element_nodal_epeq:.2,last_plastic_strain:.137798,first_flag:{time:.5,element_id:7,centroid_mm:[1,2,3]}}},self_check:{state:'passed'},mesh_quality:{native_report:{file:'mesh_quality_report.txt',state:'needs_review'}},output_policy:{result_save_mode:'all'}});
 assert.match(html,/元素节点筛查提示超表/);assert.match(html,/首次/);assert.match(html,/单元 7/);assert.match(html,/0.5/);assert.match(html,/1 \/ 2 \/ 3/);assert.match(html,/自检通过/);assert.doesNotMatch(html,/积分点通过/);
 const clean=apdl.renderApdlDiagnostics({material_coverage:{screening:{state:'no_flag',max_element_nodal_epeq:.05}}});
 assert.match(clean,/不能证明积分点全部覆盖/);
});
test('材料末点精度边界明确显示待复核而不伪称覆盖通过',()=>{
 const html=apdl.renderApdlDiagnostics({material_coverage:{screening:{state:'no_flag',near_limit_point_count:2,comparison_note:'按CSV导出11有效位判断明确超出；边界内无法确定。'}}});
 assert.match(html,/2 个结果集/);assert.match(html,/11有效位/);assert.match(html,/待复核/);assert.doesNotMatch(html,/覆盖通过/);
});
