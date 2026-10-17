import test from 'node:test';
import assert from 'node:assert/strict';
import {morphologyPayload,renderMorphologyResult} from '../morphology.mjs';

test('mode and source are explicit; geometry only fills missing source metadata',()=>{
 assert.deepEqual(morphologyPayload({mode:'detail',uploadId:'abc',geometry:{space_xy_um:25,space_z_um:25}}),{kind:'morphology_analysis',analysis_mode:'detail',upload_id:'abc',cell_geometry:{space_xy_um:25,space_z_um:25}});
 assert.throws(()=>morphologyPayload({mode:'fake',jobId:'123'}),/模式/);
 assert.throws(()=>morphologyPayload({mode:'ga'}),/来源/);
});
test('result distinguishes reference normal curve from passed validation and escapes metadata',()=>{
 const html=renderMorphologyResult({metadata:{source_name:'<script>',mode_label:'精细形貌分析'},valid_count:33,log_depth:{normality_note:'拒绝正态假设',shapiro_p:0.0000036},log_ratio:{},warnings:['旧文件未冻结配置']});
 assert.match(html,/正态参考/);assert.match(html,/拒绝正态/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});
