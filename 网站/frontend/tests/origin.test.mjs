import test from 'node:test';
import assert from 'node:assert/strict';
import {originCandidates,originPayload,originDefaults,renderOriginResult,renderOriginSettings,renderOriginSources,mountOrigin} from '../origin.mjs';
test('Origin result exposes actual rendering limitations as escaped text',()=>{
 const html=renderOriginResult({state:'completed',summary:{warnings:['色标字体<template>']}});
 assert.match(html,/色标字体&lt;template&gt;/);
});
test('only successful candidates, recommended first, preserve group index',()=>{
 const groups=[{label:'A',recommended_id:'b',candidates:[{id:'a',status:'ok'},{id:'bad',status:'failed'},{id:'b',status:'completed'}]},{label:'B',candidates:[{id:'c',status:'success'}]}];
 assert.deepEqual(originCandidates({groups}).map(c=>[c.group_index,c.model_id]),[[0,'b'],[0,'a'],[1,'c']]);
});
test('plot payload uses source and typed options without fitting request',()=>{
 assert.deepEqual(originPayload('source',{group_index:2,model_id:'linear'},'curve',{x_min:'',font_size:'12',grid:true,formats:['png']}),{source_job_id:'source',group_index:2,model_id:'linear',plot_type:'curve',options:{x_min:null,font_size:12,grid:true,formats:['png']}});
 assert.throws(()=>originPayload('source',null,'curve',{}));
 assert.throws(()=>originPayload('source',{group_index:0,model_id:'a'},'curve',{font_size:'oops'}));
});
test('settings use server defaults, escape text and hide curve-inapplicable fields',()=>{
 const html=renderOriginSettings({title:'<script>',font_size:13,azimuth:40,z_label:'Z',line_width:2,formats:['png']},'curve');
 assert.match(html,/&lt;script&gt;/);assert.match(html,/value="13"/);assert.doesNotMatch(html,/data-origin-option="azimuth"|data-origin-option="z_label"/);
 const surface=renderOriginSettings({azimuth:40,z_label:'Z',formats:['png']},'surface');assert.match(surface,/data-origin-option="azimuth"/);
});
test('origin result escapes metadata and allows editing completed jobs only',()=>{
 assert.match(renderOriginResult({state:'completed',summary:{source_job_id:'<bad>',plot_type:'curve'}}),/data-origin-open/);
 assert.doesNotMatch(renderOriginResult({state:'failed',summary:{}}),/data-origin-open/);
 assert.match(renderOriginResult({state:'completed',summary:{source_job_id:'<bad>'}}),/&lt;bad&gt;/);
 const queued=renderOriginResult({state:'queued',spec:{source_job_id:'pending-source',plot_type:'surface'}});assert.match(queued,/pending-source/);assert.match(queued,/三维响应面/);
});
test('group selector initially offers recommended successful candidates from first group only',()=>{
 const summary={groups:[{label:'<A>',recommended_id:'best',candidates:[{id:'other',status:'ok'},{id:'best',status:'ok'}]},{label:'B',candidates:[{id:'second',status:'ok'}]}]};
 const html=renderOriginSources(summary,originCandidates(summary));assert.match(html,/data-origin-group/);assert.match(html,/&lt;A&gt;/);assert.ok(html.indexOf('best')<html.indexOf('other'));assert.doesNotMatch(html,/second/);
});
test('reopen posts only to completed Origin task endpoint and reports failure',async()=>{
 let callback;const button={disabled:false,addEventListener:(event,fn)=>{callback=fn;}},note={textContent:''},calls=[];
 await mountOrigin({querySelector:selector=>selector==='[data-origin-message]'?note:button},{job:{kind:'origin_plot',id:'abc'},post:async(path,body)=>{calls.push([path,body]);throw new Error('license unavailable');}});
 await callback({target:button});assert.deepEqual(calls,[['/api/origin/jobs/abc/open',{}]]);assert.match(note.textContent,/license unavailable/);assert.equal(button.disabled,false);
});
test('running fitting task never probes or creates an Origin task',async()=>{
 await mountOrigin({querySelector:()=>null},{job:{kind:'fitting',state:'running'},get:()=>assert.fail('no probe'),post:()=>assert.fail('no submit')});
});
test('surface hides curve line styles and retains observed point color',()=>{
 const defaults={line_width:2,line_style:'solid',line_color:'#111111'};
 assert.doesNotMatch(renderOriginSettings(defaults,'surface'),/data-origin-option="line_width"|data-origin-option="line_style"/);
 assert.match(renderOriginSettings(defaults,'surface'),/线\/观测点颜色/);
 assert.match(renderOriginSettings(defaults,'curve'),/data-origin-option="line_width"/);
 assert.match(renderOriginSettings(defaults,'curve'),/data-origin-option="line_style"/);
});
test('surface labels map predictors onto X Y and response onto Z, preserving explicit plot labels',()=>{
 const defaults={x_label:'X',y_label:'Y',z_label:'Y',dpi:300};
 assert.deepEqual(originDefaults(defaults,{fitting_mode:'multivariate2',selection:{x1_column:0,x2_column:1,y_column:2}}),{x_label:'X1',y_label:'X2',z_label:'Y',dpi:300});
 assert.equal(originDefaults(defaults,{fitting_mode:'multivariate2',plot:{x_label:'X',y_label:'Y'}}).y_label,'X2');
 const summary={fitting_mode:'multivariate2',selection:{x1_label:'时间',x2_label:'浓度',y_label:'腐蚀深度'},plot:{y_label:'显式第二轴'}};
 assert.deepEqual(originDefaults(defaults,summary),{x_label:'时间',y_label:'显式第二轴',z_label:'腐蚀深度',dpi:300});
 assert.equal(defaults.y_label,'Y');
});
