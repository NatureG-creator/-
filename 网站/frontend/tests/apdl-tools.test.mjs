import test from 'node:test';
import assert from 'node:assert/strict';
import {commandDraft, replaceCommand, resetCommand, importCommandTemplate, curveSvg,
        customCommandStatus} from '../apdl_tools.mjs';

const snapshot={source_job_id:'0123456789abcdef',revision:'abc',files:{
 'main.inp':'/PREP7', 'materials.mac':'MP,EX,1,200000', 'boundary.mac':'D,1,UX,0',
 'solve.mac':'SOLVE', 'post.mac':'/POST1'}};

test('edited command drafts preserve original, switching files and resetting are exact',()=>{
 const draft=commandDraft(snapshot);
 replaceCommand(draft,'materials.mac','MP,EX,1,190000');
 assert.equal(snapshot.files['materials.mac'],'MP,EX,1,200000');
 assert.equal(draft.files['main.inp'],'/PREP7');
 resetCommand(draft,'materials.mac');
 assert.deepEqual(draft.files,snapshot.files);
});
test('template imports only command set and cannot replace source identity',()=>{
 const draft=commandDraft(snapshot);
 importCommandTemplate(draft,JSON.stringify({files:{...snapshot.files,'solve.mac':'TIME,1\nSOLVE'},source_job_id:'other'}));
 assert.equal(draft.source_job_id,snapshot.source_job_id);
 assert.match(draft.files['solve.mac'],/TIME,1/);
 assert.throws(()=>importCommandTemplate(draft,JSON.stringify({files:{'../bad':'x'}})));
});
test('material/experiment plots reject invalid coordinates and show axes',()=>{
 assert.match(curveSvg([{name:'Material',points:[[0,300],[.01,400]]}], 'Plastic strain','Stress / MPa'),/Stress \/ MPa/);
 assert.match(curveSvg([{name:'Material',points:[[0,300],[.01,400]]}], 'e','s'),/polyline/);
 assert.throws(()=>curveSvg([{name:'bad',points:[[0,NaN]]}], 'e','s'));
});
test('custom process exit is not shown as validated physical solve',()=>{
 assert.match(customCommandStatus({execution_mode:'custom_commands',solve_state:'process_finished'}),/未自动物理校核/);
});
import {taskPayload} from '../task_io.mjs';
test('custom command task keeps its own name and directory without reading main panel',()=>{
 const payload={execution_mode:'custom_commands',case_name:'edited case',export_directory:'D:/custom'};
 assert.equal(taskPayload('/api/apdl/jobs',payload),payload);
});
