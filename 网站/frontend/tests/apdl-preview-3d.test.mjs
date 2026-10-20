import test from 'node:test';
import assert from 'node:assert/strict';
import {previewGeometry,previewSummary} from '../apdl_preview_3d.mjs';

function result(options={}){
 return {options:{thickness_mm:6,origin_x_mm:-10,origin_y_mm:25,dx_mm:10,dy_mm:20,tensile_direction:'X',boundary_mode:'poisson_free',target_displacement_mm:.2,...options},stats:{nx:3,ny:2,length_mm:20,width_mm:20},preview:{x_mm:[-10,0,10],y_mm:[25,45],top_depth:[[0,1,2],[1,2,3]],bottom_depth:[[.1,.2,.3],[.4,.5,.6]]}};
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
