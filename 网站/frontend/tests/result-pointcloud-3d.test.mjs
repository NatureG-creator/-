import test from 'node:test';
import assert from 'node:assert/strict';
import {processedCsvPreview,resultQuantity} from '../result_pointcloud_3d.mjs';
import {pointcloudModel,pointcloudSection} from '../pointcloud_3d.mjs';

const csv='x_mm,y_mm,height_mm,relative_corrosion_depth_mm\n10,4,0.1,0.3\n10.3,4,0.4,0\n10,4.3,-0.1,0.5\n10.3,4.3,0.2,0.2\n';
test('full saved CSV retains all original nodes, negative height and coordinate origin',()=>{
 const data=processedCsvPreview(csv,4),model=pointcloudModel(data);
 assert.deepEqual(data.points,[[10,4,.1],[10.3,4,.4],[10,4.3,-.1],[10.3,4.3,.2]]);
 assert.equal(data.points.length,4);assert.deepEqual(pointcloudSection(model,'X',1).z,[-.1,.2]);
 assert.match(data.note,/颜色为Z高程/);assert.match(data.note,/MAT保持不变/);
});
test('exported regional CSV uses its saved coordinates without resampling or recentering',()=>{
 const regional=csv.replace('height_mm,relative_corrosion_depth_mm','z_mm,corrosion_depth_mm');
 assert.deepEqual(processedCsvPreview(regional,4).points,processedCsvPreview(csv,4).points);
});
test('wrong columns, stale count, missing values and holes cannot silently become a surface',()=>{
 assert.throws(()=>processedCsvPreview(csv,5),/点数/);
 assert.throws(()=>processedCsvPreview(csv.replace('height_mm','unknown')),/列定义/);
 assert.throws(()=>processedCsvPreview(csv.replace('0.1','')),/无效/);
 assert.throws(()=>processedCsvPreview(csv.replace('10.3,4.3,0.2,0.2\n','')),/缺点/);
 assert.throws(()=>processedCsvPreview(csv+'10,4,0.1,0.3\n'),/重复XY/);
});
test('height and depth views use their saved columns without changing either array',()=>{
 const data=processedCsvPreview(csv,4),before=structuredClone(data),ranges={referenceHeight:.4,heightRange:[-.1,.4],depthRange:[0,.5]};
 const height=resultQuantity(data,'height',ranges),depth=resultQuantity(data,'depth',ranges);
 assert.deepEqual(height.points,before.points);assert.deepEqual(depth.points.map(p=>p[2]),[.3,0,.5,.2]);
 assert.equal(pointcloudModel(height).inwardPositive,false);assert.equal(pointcloudModel(depth).inwardPositive,true);
 assert.equal(pointcloudModel(depth).relativeDepth,true);assert.deepEqual(depth.color_bounds_mm,[0,.5]);
 assert.match(depth.note,/原完整处理表面最高点/);assert.match(depth.note,/不是相对未腐蚀面的总深度/);
 assert.deepEqual(data,before);
});
test('regional depth retains its original zero and full-surface color scale',()=>{
 const data={points:[[10,4,.1],[11,4,.2],[10,5,.3],[11,5,.4]],relative_depth_mm:[.8,.7,.6,.5],grid:true};
 const d=resultQuantity(data,'depth',{referenceHeight:.9,depthRange:[0,.9]});
 assert.deepEqual(d.points.map(p=>p[2]),[.8,.7,.6,.5]);assert.equal(Math.min(...d.points.map(p=>p[2])),.5);
 assert.deepEqual(pointcloudModel(d).colorBounds,[0,.9]);assert.match(d.note,/H_top=0.9 mm/);
});
test('missing or invalid saved depth cannot be replaced by a newly inferred reference',()=>{
 const data=processedCsvPreview(csv,4);
 for(const relative_depth_mm of [undefined,[.1],[-.1,0,.2,.3],[NaN,0,.2,.3]])assert.throws(()=>resultQuantity({...data,relative_depth_mm},'depth'),/已保存相对深度/);
 assert.throws(()=>resultQuantity(data,'unknown'),/只能选择/);
});
