import test from 'node:test';
import assert from 'node:assert/strict';
import {selectedStressStrainSources} from '../apdl_stress_strain.mjs';

const row=(id,label,checked=true)=>({checkbox:{checked,dataset:{jobId:id}},label:{value:label}});

test('selection preserves user labels and task identities without inferring days',()=>{
 assert.deepEqual(selectedStressStrainSources([row('a','  腐蚀 30 天  '),row('b','原样'),row('c','',false)]),[
  {job_id:'a',label:'腐蚀 30 天'},{job_id:'b',label:'原样'}]);
});

test('selection rejects missing labels, control characters and invalid curve counts',()=>{
 for(const rows of [[],[row('a','a')],[row('a','a'),row('b',' ')],
  [row('a','a'),row('b','b'.repeat(81))],[row('a','a'),row('b','b\nc')],
  Array.from({length:21},(_,i)=>row(String(i),'curve'))]){
  assert.throws(()=>selectedStressStrainSources(rows));
 }
 assert.equal(selectedStressStrainSources(Array.from({length:20},(_,i)=>row(String(i),'curve'))).length,20);
});
