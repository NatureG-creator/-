import test from 'node:test';
import assert from 'node:assert/strict';
import {previewGeometry,previewSummary,previewSection,previewMinimum,referenceCaption} from '../apdl_preview_3d.mjs';

function result(options={}){
 return {options:{thickness_mm:6,origin_x_mm:-10,origin_y_mm:25,dx_mm:10,dy_mm:20,tensile_direction:'X',boundary_mode:'poisson_free',target_displacement_mm:.2,...options},stats:{nx:3,ny:2,length_mm:20,width_mm:20},corrosion_region:{x_range_mm:[-5,5],y_range_mm:[25,45],nx:2,ny:2},preview:{x_mm:[-10,0,10],y_mm:[25,45],top_depth:[[0,1,2],[1,2,3]],bottom_depth:[[.1,.2,.3],[.4,.5,.6]]}};
}

test('physical origin, dimensions and non-flat corner coupling follow X boundary rules',()=>{
 const m=previewGeometry(result());
 assert.deepEqual(m.bounds,[[-10,10],[25,45],[0,6]]);
 assert.deepEqual(m.fixed,[-10,-10]);assert.deepEqual(m.loaded,[10,10]);
 assert.deepEqual(m.corners.map(c=>c.point),[[-10,25,.1],[-10,45,.4]]);
 assert.match(m.corners[1].rule,/20 × UZ − \(0.3\) × UY/);
 assert.match(previewSummary(m),/UX=\+0.2 mm/);
 assert.equal(m.complete,true);
});
test('Y clamped ranges cover grip lengths; corner constraints are not added',()=>{
 const m=previewGeometry(result({tensile_direction:'Y',boundary_mode:'clamped_grips',grip_length_fixed_mm:3,grip_length_loaded_mm:4}));
 assert.deepEqual(m.fixed,[25,28]);assert.deepEqual(m.loaded,[41,45]);assert.deepEqual(m.corners,[]);
 assert.equal(m.dof,'UY');assert.equal(m.tdof,'UX');
 assert.match(previewSummary(m),/UY=0，UX=0，UZ=0/);
});
test('Poisson-free Y uses first and last transverse bottom corners',()=>{
 const m=previewGeometry(result({tensile_direction:'Y',grip_length_fixed_mm:9,grip_length_loaded_mm:9}));
 assert.deepEqual(m.fixed,[25,25]);assert.deepEqual(m.loaded,[45,45]);
 assert.deepEqual(m.corners.map(c=>c.point),[[-10,25,.1],[10,25,.3]]);
 assert.match(m.corners[1].rule,/20 × UZ − \(0.2\) × UX/);
});
test('legacy constraints use bottom and top at the far transverse corner',()=>{
 for(const axis of ['X','Y']){
  const m=previewGeometry(result({boundary_mode:'legacy_recommended',tensile_direction:axis}));
  assert.deepEqual(m.corners.map(c=>c.point),axis==='X'?[[-10,45,.4],[-10,45,5]]:[[10,25,.3],[10,25,4]]);
  assert.equal(m.corners[1].rule,`${m.tdof}=0，UZ=0`);
 }
});
test('flat bottom uses a Z-only second corner and zero-length grips mean planes',()=>{
 const r=result({boundary_mode:'poisson_free'});r.preview.bottom_depth=[[0,0,0],[0,0,0]];
 assert.equal(previewGeometry(r).corners[1].rule,'UZ=0');
 const m=previewGeometry(result({boundary_mode:'clamped_grips'}));
 assert.deepEqual(m.fixed,[-10,-10]);assert.deepEqual(m.loaded,[10,10]);
});
test('legacy stride coordinates retain physical spacing and flag missing far edges',()=>{
 const r=result();delete r.preview.x_mm;delete r.preview.y_mm;
 r.stats.nx=193;r.stats.ny=83;r.stats.length_mm=1920;r.stats.width_mm=1640;
 const m=previewGeometry(r);
 assert.deepEqual(m.x,[-10,20,50]);assert.deepEqual(m.y,[25,65]);assert.equal(m.complete,false);
});
test('local corrosion preview carries actual patch bounds and reports sampling size',()=>{
 const m=previewGeometry(result({local_corrosion:true}));
 assert.deepEqual(m.region.x_range_mm,[-5,5]);
 assert.match(previewSummary(m),/局部腐蚀区域/);
 assert.match(previewSummary(m),/2 × 2 个原始表面采样点/);
});
test('local corrosion preview reports applied rotation and flips',()=>{
 const m=previewGeometry({...result({local_corrosion:true}),corrosion_region:{x_range_mm:[-5,5],y_range_mm:[25,45],nx:2,ny:2,rotation_deg:90,flip_x:true,flip_y:true}});
 assert.match(previewSummary(m),/旋转 90°，沿 X 翻转，沿 Y 翻转/);
});

test('movable X sections preserve real coordinates and subtract both face depths',()=>{
 const r=result(),before=structuredClone(r),m=previewGeometry(r),s=previewSection(m,1);
 assert.deepEqual(s.coords,[-10,0,10]);assert.equal(s.coordinate,45);
 assert.deepEqual(s.top,[5,4,3]);assert.deepEqual(s.bottom,[.4,.5,.6]);
 assert.equal(s.min,2.4);assert.equal(s.at,2);
 const p=previewMinimum(m);assert.equal(p.index,1);assert.deepEqual(p.point,[10,45,3]);assert.deepEqual(p.bottom,[10,45,.6]);
 assert.deepEqual(r,before);
});
test('movable Y sections index columns and retain nonzero origins',()=>{
 const m=previewGeometry(result({tensile_direction:'Y'})),s=previewSection(m,2);
 assert.deepEqual(s.coords,[25,45]);assert.equal(s.coordinate,10);
 assert.deepEqual(s.top,[4,3]);assert.deepEqual(s.remaining,[3.7,2.4]);
 assert.equal(previewMinimum(m).index,2);
 assert.equal(previewSection(m,99).index,2);
});
test('reference captions distinguish empirical single-face assumptions from manual mean calibration',()=>{
 const r=result();r.stats.platforms={calibration_method:'empirical_reference_preserved',reference_calibrations:{top:{reference_height_mm:-.014810324737678}}};
 assert.match(referenceCaption(previewGeometry(r)),/经验参考面 H_flat=-0.0148103 mm → 模型 Z=6 mm/);
 assert.match(referenceCaption(previewGeometry(r)),/未知损失未补偿/);
 assert.match(referenceCaption(previewGeometry(r)),/单面模型假设/);
 r.stats.platforms.calibration_method='sample_mean_translation';
 assert.match(referenceCaption(previewGeometry(r)),/手动实测均值/);
 assert.doesNotMatch(referenceCaption(previewGeometry(r)),/经验参考面/);
});
