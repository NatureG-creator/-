import test from 'node:test';
import assert from 'node:assert/strict';
import {pointcloudModel,pointcloudSection,coincidentSection,commonReferenceSummary,cropSelection,draftReference,commonCropSnapshot} from '../pointcloud_3d.mjs';

const data=()=>({grid:true,point_count:200,points:[[12,7,-.3],[10,5,.2],[12,5,.1],[10,7,-.1]],note:'relative heights'});
test('grid reconstruction retains negative elevations and nonzero coordinate origins',()=>{
 const original=data(),before=structuredClone(original),m=pointcloudModel(original);
 assert.deepEqual(m.x,[10,12]);assert.deepEqual(m.y,[5,7]);assert.deepEqual(m.grid,[[.2,.1],[-.1,-.3]]);
 assert.deepEqual(pointcloudSection(m,'X',1),{index:1,coordinate:7,coords:[10,12],z:[-.1,-.3],min:-.3,max:-.1});
 assert.deepEqual(pointcloudSection(m,'Y',1).z,[.1,-.3]);assert.equal(m.total,200);
 assert.deepEqual(original,before);
});
test('scattered raw points never invent a surface or interpolated section',()=>{
 const m=pointcloudModel({...data(),grid:false});assert.equal(m.grid,null);
 assert.throws(()=>pointcloudSection(m,'X',0),/散点/);
});
test('invalid XYZ, incomplete grids and duplicate XY are rejected',()=>{
 assert.throws(()=>pointcloudModel({points:[[1,2,NaN]]}),/有效XYZ/);
 const missing=data();missing.points.pop();assert.throws(()=>pointcloudModel(missing),/缺点/);
 const duplicate=data();duplicate.points.push(duplicate.points[0]);assert.throws(()=>pointcloudModel(duplicate),/重复XY/);
});
test('section index is clamped without extrapolating coordinates or heights',()=>{
 const m=pointcloudModel(data());assert.equal(pointcloudSection(m,'X',100).coordinate,7);
 assert.equal(pointcloudSection(m,'Y',-4).coordinate,10);
 assert.throws(()=>pointcloudSection(m,'Z',0),/方向/);
});

const common=()=>({numerical_chain_verified:true,physical_pristine_reference_verified:false,reference_column_count:200,reference_ratio:.2,
 reference_height_mm:-.014810324737678,reference_min_height_mm:-.057,reference_max_height_mm:.154,
 reference_x_range_mm:[0,59.7],reference_y_range_mm:[0,18],local_x_range_mm:[69.9,117.6],local_y_range_mm:[.3,18],mean_depth_mm:.371971,max_depth_mm:.69667});
test('common-frame view keeps negative inward-positive H without rebasing or clipping',()=>{
 const source={...data(),inward_positive:true,common_reference:common()},before=structuredClone(source),m=pointcloudModel(source);
 assert.equal(m.inwardPositive,true);assert.deepEqual(m.points,source.points);assert.deepEqual(source,before);
 const text=commonReferenceSummary(common());assert.match(text,/第1～200列/);assert.match(text,/59.7/);
 assert.match(text,/H_flat=-0.01481032 mm/);assert.match(text,/未知损失未补偿/);assert.match(text,/向内为正/);
});
test('full and local sections coincide only at existing common coordinates',()=>{
 const m=pointcloudModel(data());assert.deepEqual(coincidentSection(m,'X',7+1e-12).z,[-.1,-.3]);
 assert.deepEqual(coincidentSection(m,'Y',12).z,[.1,-.3]);assert.equal(coincidentSection(m,'X',6),null);
});
test('common-frame display rejects missing verification and pristine-reference claims',()=>{
 for(const change of [{physical_pristine_reference_verified:true},{numerical_chain_verified:false},{reference_column_count:199},{reference_ratio:.3}]){
  assert.throws(()=>pointcloudModel({...data(),common_reference:{...common(),...change}}),/已验证/);
 }
});

const sourceGrid=()=>({x:[10,11,12,13],y:[-2,-1,0],grid:[[-.3,-.2,0,.1],[-.1,.2,.4,.5],[0,.1,.3,.8]]});
test('crop draft uses existing closed-interval nodes and retains actual dimensions',()=>{
 const g=sourceGrid(),before=structuredClone(g),crop=cropSelection(g,{length:2.2,width:1.2,centerX:11.5,centerY:-1});
 assert.deepEqual(crop.requested,{x:[10.4,12.6],y:[-1.6,-.4]});
 assert.deepEqual(crop.actual,{x:[11,12],y:[-1,-1]});assert.equal(crop.pointCount,2);assert.equal(crop.exportable,false);
 assert.ok(Math.abs(crop.coverage-1)<1e-14);assert.deepEqual(g,before);
});
test('crop draft reports partial coverage and no-node regions without extrapolation',()=>{
 const g=sourceGrid(),crop=cropSelection(g,{length:4,width:2,centerX:13,centerY:-1});
 assert.deepEqual(crop.shown,{x:[11,13],y:[-2,0]});assert.equal(crop.coverage,.5);assert.equal(crop.pointCount,9);
 assert.equal(cropSelection(g,{length:.1,width:.1,centerX:10.5,centerY:-1.5}).pointCount,0);
 assert.equal(cropSelection(g,{length:1,width:1,centerX:100,centerY:100}).shown,null);
});
test('crop node boundaries match exporter floating-point comparison exactly',()=>{
 const g={x:[.29999999999999993,.6],y:[0,1],grid:[[1,2],[3,4]]};
 const c=cropSelection(g,{length:.1,width:1,centerX:.35,centerY:.5});
 assert.equal(c.requested.x[0],.3);assert.equal(c.pointCount,0);
});
test('draft reference uses the complete first N columns and leaves verified values intact',()=>{
 const g=sourceGrid(),before=structuredClone(g),verified=Object.freeze({height:-.014810324737677995,columns:200,ratio:.2});
 const r=draftReference(g,2,.25);assert.equal(r.status,'draft');assert.equal(r.min,-.3);assert.equal(r.max,.2);assert.equal(r.height,-.175);
 assert.deepEqual(r.x,[10,11]);assert.deepEqual(r.y,[-2,0]);assert.deepEqual(g,before);
 assert.equal(verified.height,-.014810324737677995);assert.equal(draftReference(g,4,0).height,-.3);assert.equal(draftReference(g,4,1).height,.8);
});
test('invalid draft inputs reject only the draft without mutating source arrays',()=>{
 const g=sourceGrid(),before=structuredClone(g);
 for(const columns of [0,5,1.5,''])assert.throws(()=>draftReference(g,columns,.2),/列数/);
 for(const ratio of [-.1,1.1,Infinity,''])assert.throws(()=>draftReference(g,2,ratio),/比例/);
 for(const length of [0,-1,Infinity,''])assert.throws(()=>cropSelection(g,{length,width:1}),/正数/);
 assert.throws(()=>cropSelection(g,{length:1,width:1,centerX:NaN}),/中心/);assert.deepEqual(g,before);
});

const exportSource=()=>({view:'common_reference',source_job_id:'aaaaaaaaaaaaaaaa',common_reference:{...common(),section_grid:sourceGrid(),cache_key:'verified-cache',complete_surface_sha256:'full-hash',depth_sha256:'depth-hash',original_thickness_mm:6}});
test('confirmed crop snapshot uses real nodes and only the fixed verified reference',()=>{
 const source=exportSource(),before=structuredClone(source),s=commonCropSnapshot(source,{length:2,width:2,centerX:11,centerY:-1});
 assert.equal(s.body.source_kind,'common_reference');assert.equal(s.body.confirmation.point_count,9);
 assert.deepEqual(s.body.confirmation.actual_bounds_mm,{x:[10,12],y:[-2,0]});
 assert.equal(s.body.confirmation.reference.reference_ratio,.2);assert.equal(s.body.confirmation.reference.reference_column_count,200);
 assert.equal(s.body.confirmation.reference.reference_height_mm,source.common_reference.reference_height_mm);
 assert.equal('draft_reference' in s.body,false);assert.deepEqual(source,before);
});
test('parameter, source and provenance changes invalidate the confirmation snapshot',()=>{
 const source=exportSource(),p={length:2,width:2,centerX:11,centerY:-1},key=commonCropSnapshot(source,p).key;
 assert.notEqual(commonCropSnapshot(source,{...p,centerX:11.1}).key,key);
 assert.notEqual(commonCropSnapshot({...source,source_job_id:'bbbbbbbbbbbbbbbb'},p).key,key);
 assert.notEqual(commonCropSnapshot({...source,common_reference:{...source.common_reference,complete_surface_sha256:'changed'}},p).key,key);
 assert.throws(()=>commonCropSnapshot(source,{...p,width:.1}),/不足两个/);
 assert.throws(()=>commonCropSnapshot({...source,common_reference:{...source.common_reference,reference_ratio:.25}},p),/20%/);
});
test('relative depth has a distinct quantity and does not reuse the common H reference',()=>{
 const source={...data(),value_kind:'relative_depth',color_bounds_mm:[0,1]};
 const m=pointcloudModel(source);assert.equal(m.relativeDepth,true);assert.equal(m.inwardPositive,true);assert.deepEqual(m.colorBounds,[0,1]);
 assert.throws(()=>pointcloudModel({...source,common_reference:common()}),/不能混作/);
 for(const color_bounds_mm of [[1,0],[0,NaN],[0]])assert.throws(()=>pointcloudModel({...source,color_bounds_mm}),/色标范围/);
});
