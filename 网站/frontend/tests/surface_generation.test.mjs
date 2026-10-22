import test from 'node:test';
import assert from 'node:assert/strict';
import {generationPayload,renderGenerationSummary,generationPage} from '../surface_generation.mjs';

test('single face needs only its own source and preserves explicit crop options',()=>{
 const payload=generationPayload([{side:'back',enabled:true,uploadId:'xyz',origin:'upload',options:{dx_mm:.3}},{side:'front',enabled:false}],{length_mm:50,grid_mode:'preserve'});
 assert.equal(payload.kind,'surface_generation');
 assert.deepEqual(payload.faces,[{side:'back',upload_id:'xyz',options:{dx_mm:.3,length_mm:50,grid_mode:'preserve'}}]);
 assert.equal('reference_id' in payload,false);
});
test('completed simulation and selected NPZ stage remain explicit',()=>{
 const result=generationPayload([{side:'front',enabled:true,origin:'task',jobId:'sim',variable:'a_sd',stage:'2',options:{}}],{});
 assert.equal(result.faces[0].source_job_id,'sim');assert.equal(result.faces[0].stage,2);
 assert.equal(result.faces[0].variable,'a_sd');
 assert.throws(()=>generationPayload([{side:'front',enabled:true,origin:'upload',stage:0,uploadId:'x'}],{}),/正整数/);
});
test('no face and missing sources cannot submit',()=>{
 assert.throws(()=>generationPayload([],{}),/至少/);
 assert.throws(()=>generationPayload([{side:'front',enabled:true}],{}),/来源/);
});
test('result reports actual dimensions and interpolation instead of nominal size only',()=>{
 const html=renderGenerationSummary({faces:[{side:'front',source_name:'<source>',source_variable:'F_filled',value_mode:'height',matrix_shape:[60,167],size_x_mm:49.8,size_y_mm:17.7,requested_length_mm:50,actual_length_mm:49.8,actual_width_mm:17.7,grid_mode:'preserve',resampled:false,dx_mm:.3,dy_mm:.3,point_count:10020,missing_filled_count:12}]});
 assert.match(html,/49.8/);assert.match(html,/未自动配准/);assert.match(html,/double/);
 assert.match(html,/最近邻填补 12/);assert.match(html,/&lt;source&gt;/);assert.doesNotMatch(html,/<source>/);
 assert.match(renderGenerationSummary({faces:[{side:'back',resampled:true}]}),/双线性重采样/);
});
test('independent workflow exposes all agreed inputs and clear output contract',()=>{
 const html=generationPage();
 for(const label of ['190 mm','60 mm','50 mm','自定义','完整来源','裁剪 X 起始偏移','裁剪 Y 起始偏移','原模拟 XY','Z_filled','F_filled','surface_bundle.zip','最近邻填补'])assert.ok(html.includes(label),label);
 assert.match(html,/单面即可运行/);assert.match(html,/value="preserve"/);
 assert.equal((html.match(/data-face="/g)||[]).length,2);
});
