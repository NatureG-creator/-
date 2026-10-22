import test from 'node:test';
import assert from 'node:assert/strict';
import {renderApdlExplanation,apdlResultStatus} from '../apdl_explanation.mjs';
import {renderApdlResult,renderApdlDiagnostics} from '../apdl.mjs';

const explanation={outcome:'completed_with_warnings',loading_complete:true,recovered_distortion:true,
 title:'目标加载已完成 · 存在警告，结果待复核',conclusion:'日志和曲线确认 11 mm',target_displacement_mm:11,
 final_displacement_mm:11,final_time:1,final_load_N:56895.9,point_count:57,bisection_count:3,exit_code:1,
 last_converged:{load_step:1,substep:57},original_state:'failed',original_error:'exit 1',
 issues:[{title:'中途单元畸变，切步后已恢复收敛',severity:'warning',cause:'试算变形过大',impact:'已恢复',
 action:'检查问题单元',evidence:{file:'mapdl.out',line:666957,text:'<unsafe>'},count:8}],
 material_screening:{limit:.137798,maximum:1.457157135,first_time:.395,first_element:15424,first_centroid_mm:[30.15,23.25,.759]},
 note:'未核验 RST 二进制内容'};

test('历史失败但加载完成的任务显示具体完成范围和可追溯异常说明',()=>{
 const html=renderApdlResult({solve_state:'failed',build_state:'built',result_explanation:explanation},{state:'failed'});
 for(const text of ['目标加载已完成','57','11','原因：','影响：','建议：','666957','0.137798','1.457157','0.395','15424','原任务记录'])assert.ok(html.includes(text),text);
 assert.match(html,/&lt;unsafe&gt;/);assert.doesNotMatch(html,/<unsafe>/);
 assert.doesNotMatch(html,/未调用 MAPDL 时/);
 assert.doesNotMatch(html,/>MAPDL 求解失败</);
 assert.equal(apdlResultStatus({summary:{result_explanation:explanation}}).tone,'warning');
});

test('未完成任务直接显示失败阶段和错误，缺失数值不冒充0',()=>{
 const e={outcome:'incomplete',loading_complete:false,title:'目标加载未完成',failure_stage:'postprocess',original_error:'缺少 nodal_results.csv'};
 const html=renderApdlExplanation(e);
 assert.match(html,/未完成的直接原因（后处理与结果校核）/);
 assert.match(html,/缺少 nodal_results.csv/);assert.match(html,/未取得/);
 assert.equal(apdlResultStatus({state:'failed',summary:{result_explanation:e}}).tone,'failed');
});

test('不把无解释字段旧任务和未执行求解的输入包显示成数值求解成功',()=>{
 assert.equal(apdlResultStatus({state:'failed'}),null);
 assert.equal(renderApdlExplanation(null),'');
 assert.equal(apdlResultStatus({summary:{result_explanation:{outcome:'not_requested'}}}).label,'输入包已生成');
});

test('已有报告但未验收时说明文件已生成，不再声称未运行或自检通过',()=>{
 const html=renderApdlDiagnostics({mesh_quality:{},material_coverage:{}},{diagnostic_files:['mesh_quality_report.txt','apdl_self_check.csv']});
 assert.match(html,/原生质量报告已生成/);
 assert.match(html,/自检 CSV 已生成，尚未独立校核/);
 assert.doesNotMatch(html,/尚未运行或尚未提供真实自检文件|自检通过/);
});
