import test from 'node:test';
import assert from 'node:assert/strict';
import {referenceAnalysis,explainParameter,controlKey,gaProbabilityPreview} from '../parameter_help.mjs';

const common=()=>({section_grid:{x:Array.from({length:10},(_,i)=>i),y:[0,1],grid:[Array.from({length:10},(_,i)=>i),Array.from({length:10},(_,i)=>i+.5)]},reference_height_mm:.3,mean_depth_mm:3});
const descriptor=(key,value,label=key)=>({key,value,label,help:'',scope:'',module:'test'});
test('reference what-if follows the exact extreme-range formula and central-column rule',()=>{
 const c=common(),before=structuredClone(c),a=referenceAnalysis(c,{columns:2,ratio:.4,corrosionColumns:4});
 assert.ok(Math.abs(a.height-.6)<1e-14);assert.deepEqual(a.centralColumns,[5,8]);assert.equal(a.centralMax,7.5);
 assert.ok(Math.abs(a.uniformComponent-6.9)<1e-14);assert.ok(Math.abs(a.localMeanDepth-2.7)<1e-14);assert.deepEqual(c,before);
});
test('raising ratio shifts reference and depths in opposite directions without changing shape',()=>{
 const c=common(),a=referenceAnalysis(c,{columns:2,ratio:.2,corrosionColumns:4}),b=referenceAnalysis(c,{columns:2,ratio:.3,corrosionColumns:4});
 assert.ok(Math.abs((b.height-a.height)-.15)<1e-14);assert.ok(Math.abs((b.localMeanDepth-a.localMeanDepth)+.15)<1e-14);
 assert.equal(c.reference_height_mm,.3);
});
test('invalid reference and central-column values are rejected rather than silently normalized',()=>{
 for(const change of [{columns:0},{columns:11},{columns:null},{ratio:1.2},{ratio:null},{corrosionColumns:20}])assert.throws(()=>referenceAnalysis(common(),{columns:2,ratio:.2,corrosionColumns:4,...change}));
});
test('no saved matrix produces only a clearly labeled reference schematic',()=>{
 const r=explainParameter(descriptor('reference.flat_height_ratio',.2),{columns:200,ratio:.2});
 assert.match(r.meaning,/不是第20百分位/);assert.match(r.diagram,/不是实测高程/);assert.equal(r.facts.some(s=>s.includes('候选 H_flat=')),false);
});
test('reference help preserves the verified plane and labels candidate numerical analysis',()=>{
 const r=explainParameter(descriptor('reference.flat_height_ratio',.4),{columns:2,ratio:.4,corrosionColumns:4},common());
 assert.match(r.diagram,/实测完整矩阵/);assert.ok(r.facts.some(s=>s.includes('H_flat=0.60000000')));assert.match(r.boundary,/不覆盖20%缓存/);
});
test('watershed explanation follows the executable inequality, not the reversed old comment',()=>{
 const r=explainParameter(descriptor('watershed.threshold',.3));assert.match(r.meaning,/distance > r/);assert.match(r.effect,/背景条件的范围减少/);
});
test('unused simulation fields cannot imply an effect on active CA GA evaluation',()=>{
 const r=explainParameter({...descriptor('FIGURE_CONFIG.surface_dpi',300),scope:'独立科研出图预留，本任务未使用'});
 assert.match(r.effect,/当前CA\/GA计算链不读取/);
});
test('all diagram families label numerical scope and escape user-controlled text',()=>{
 for(const key of ['preview.length','GEOMETRY_CONFIG.grid_w','preprocessing.main_gaussian_sigma','pit_detection.min_distance','preprocessing.trim_edge_rows','distribution.hist_bin_width','figure.font_size','apdl.E_MPa','apdl.layers','fit.folds','apdl.displacement_mm','GA_CONFIG.seed','STAGE_GA_CONFIG.parallel_workers','STAGE_GA_CONFIG.nind','fit.custom_formula','unknown']){
  const r=explainParameter(descriptor(key,key==='unknown'?'<script>bad</script>':2));assert.match(r.diagram,/role="img"/);assert.ok(r.meaning.length>8&&r.effect.length>8);assert.doesNotMatch(r.diagram,/<script>/);assert.doesNotMatch(r.diagram,/NaN|Infinity/);
 }
});
test('live style and reference changes visibly change the diagram',()=>{
 assert.notEqual(explainParameter(descriptor('figure.boundary_line_width',1)).diagram,explainParameter(descriptor('figure.boundary_line_width',5)).diagram);
 assert.notEqual(explainParameter(descriptor('reference.flat_height_ratio',.2),{ratio:.2}).diagram,explainParameter(descriptor('reference.flat_height_ratio',.4),{ratio:.4}).diagram);
});
test('known dedicated controls and draft fields resolve to their parameter identities',()=>{
 assert.equal(controlKey({dataset:{},id:'sim-seed'}),'GA_CONFIG.seed');assert.equal(controlKey({dataset:{draft:'ratio'}}),'preview.ratio');assert.equal(controlKey({dataset:{option:'layers'}}),'apdl.layers');
 assert.equal(controlKey({dataset:{mv:'folds'},id:'mv-folds',attributes:[{name:'data-mv',value:'folds'}]}),'mv.folds');
});
test('probability teaching uses the real clipping limits and exclusive maxgen',()=>{
 const p=gaProbabilityPreview();assert.equal(p[0].gen,1);assert.equal(p.at(-1).gen,100);
 assert.ok(p.every(v=>v.px===.6&&v.pm===.3));assert.deepEqual(gaProbabilityPreview({maxgen:1}),[]);
 const q=gaProbabilityPreview({basePx:2,basePm:0,decayRate:0,maxgen:3});assert.ok(q.every(v=>v.px===.95));assert.ok(Math.abs(q[0].pm-.1)<1e-14);
 assert.throws(()=>gaProbabilityPreview({maxgen:1.5}));
});
