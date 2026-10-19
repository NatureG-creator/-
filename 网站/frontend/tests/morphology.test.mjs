import test from 'node:test';
import assert from 'node:assert/strict';
import {morphologyPayload,morphologyBatchPayload,renderMorphologyResult,renderMorphologyComparison,morphologyModeNote,hasMorphologyArchive,normalizeMorphologyExportFormats} from '../morphology.mjs';

test('legacy tasks do not advertise absent ZIP files',()=>{
 assert.equal(hasMorphologyArchive({files:[]}),false);
 assert.equal(hasMorphologyArchive({files:[{name:'ga/analysis_arrays.npz'}]}),false);
 assert.equal(hasMorphologyArchive({files:[{name:'morphology_bundle.zip'}]}),true);
});
test('both modes explain the shared input and different analysis rules',()=>{
 assert.match(morphologyModeNote('both'),/同一.*NPZ/);
 assert.match(morphologyModeNote('both'),/GA.*精细/);
});

test('mode and source are explicit; geometry only fills missing source metadata',()=>{
 assert.deepEqual(morphologyPayload({mode:'detail',uploadId:'abc',geometry:{space_xy_um:25,space_z_um:25}}),{kind:'morphology_analysis',analysis_mode:'detail',upload_id:'abc',cell_geometry:{space_xy_um:25,space_z_um:25}});
 assert.throws(()=>morphologyPayload({mode:'fake',jobId:'123'}),/模式/);
 assert.throws(()=>morphologyPayload({mode:'ga'}),/来源/);
});
test('external NPZ stage is included and must be a positive integer',()=>{
 assert.deepEqual(morphologyPayload({mode:'both',uploadId:'abc',sourceStage:2}),{kind:'morphology_analysis',analysis_mode:'both',upload_id:'abc',source_stage:2});
 assert.throws(()=>morphologyPayload({mode:'ga',uploadId:'abc',sourceStage:1.5}),/正整数/);
});
test('batch stages require an external NPZ and preserve all-stage selection',()=>{
 assert.deepEqual(morphologyBatchPayload({mode:'detail',uploadId:'abc',stages:'all'}),{kind:'morphology_analysis',analysis_mode:'detail',upload_id:'abc',source_stages:'all'});
 assert.deepEqual(morphologyBatchPayload({mode:'ga',uploadId:'abc',stages:[1,3]}).source_stages,[1,3]);
 assert.throws(()=>morphologyBatchPayload({mode:'ga',jobId:'x',stages:'all'}),/外部 NPZ/);
 assert.throws(()=>morphologyBatchPayload({mode:'ga',uploadId:'abc',stages:[0]}),/正整数列表/);
});
test('batch result renders stage comparison rows',()=>{
 const html=renderMorphologyResult({source_name:'stages.npz',npz_variable:'a_sd',npz_stages:[1,2],stages:[{stage:1,report:{valid_count:3,six_metrics:[1.2,2.3],metadata:{mode_label:'精细形貌分析'}}},{stage:2,report:{valid_count:4,six_metrics:[1.4,2.5],metadata:{mode_label:'精细形貌分析'}}}]});
 assert.match(html,/阶段批量分析/);assert.match(html,/>1<.*>3</s);assert.match(html,/>2<.*>4</s);
});
test('result distinguishes reference normal curve from passed validation and escapes metadata',()=>{
 const html=renderMorphologyResult({metadata:{source_name:'<script>',mode_label:'精细形貌分析'},valid_count:33,log_depth:{normality_note:'拒绝正态假设',shapiro_p:0.0000036},log_ratio:{},warnings:['旧文件未冻结配置']});
 assert.match(html,/正态参考/);assert.match(html,/拒绝正态/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>/);
});

test('paired payload and result preserve both explicit analysis modes',()=>{
 assert.equal(morphologyPayload({mode:'both',jobId:'abc'}).analysis_mode,'both');
 const html=renderMorphologyResult({modes:{ga:{metadata:{mode_label:'GA 同口径验收'}},detail:{metadata:{mode_label:'精细形貌分析'}}}});
 assert.match(html,/GA 同口径验收/);assert.match(html,/精细形貌分析/);
});

test('paired result includes a direct comparison table and shared-source note',()=>{
 const html=renderMorphologyComparison({ga:{metadata:{source_name:'sample.npz',source_sha256:'abc',window_size:5},valid_count:8,log_depth:{mean:1.2}},detail:{metadata:{source_name:'sample.npz',source_sha256:'abc',window_size:9},valid_count:12,log_depth:{mean:1.6}}});
 assert.match(html,/双模式对照/);assert.match(html,/同一冻结来源：sample\.npz/);assert.match(html,/有效坑数/);assert.match(html,/8/);assert.match(html,/12/);
});

test('export format selection is unique and rejects an empty choice',()=>{
 assert.deepEqual(normalizeMorphologyExportFormats(['pdf','pdf','svg']),['pdf','svg']);
 assert.throws(()=>normalizeMorphologyExportFormats([]),/至少选择/);
 assert.throws(()=>normalizeMorphologyExportFormats(['exe']),/至少选择/);
});
