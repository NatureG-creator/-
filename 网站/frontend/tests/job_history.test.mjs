import test from 'node:test';
import assert from 'node:assert/strict';
import {historyControls,bindHistoryActions,resumeNotice,historyDay,historyDates,checkpointNotice} from '../job_history.mjs';

test('new PyCharm snapshots explain individual resume while legacy remains stage-only',()=>{
  const job={spec:{config:{mode:'pycharm'}},checkpoint:{backend:'pycharm',saved:{stage:1,generation:3,generation_completed:2,completed_individuals:7}}};
  assert.match(resumeNotice(job),/复用已保存个体评价/);
  assert.match(checkpointNotice(job),/第 3 代已保存 7 个体/);
  assert.equal(checkpointNotice({}), '');
  assert.match(resumeNotice({spec:job.spec}),/中断阶段.*重新计算/);
});

test('history dates use Shanghai calendar days and newest first',()=>{
  assert.equal(historyDay({created_at:'2026-10-17T17:00:00Z'}),'2026-10-18');
  assert.deepEqual(historyDates([{created_at:'2026-10-16'},{created_at:'2026-10-18'},{created_at:'2026-10-18'}]),['2026-10-18','2026-10-16']);
});

const id='a'.repeat(16);
function fakeButton(action){
  return {dataset:{historyAction:action,jobId:id},disabled:false,
    addEventListener(event,handler){this.click=handler;}};
}

test('active records have no destructive or hide controls; hidden records can be restored',()=>{
  assert.equal(historyControls({id,state:'running'}),'');
  assert.match(historyControls({id,state:'failed'}),/data-history-action="hide"/);
  assert.match(historyControls({id,state:'interrupted',history_hidden:true}),/data-history-action="unhide"/);
});

test('canceling permanent deletion sends no request',async()=>{
  const button=fakeButton('delete'),requests=[];
  bindHistoryActions({querySelectorAll:()=>[button]},{post:(...args)=>requests.push(args),
    confirmDelete:()=>false,refresh:()=>{},report:()=>{}});
  await button.click();
  assert.deepEqual(requests,[]);
  assert.equal(button.disabled,false);
});

test('confirmed deletion sends the matching ID and clears selection only after success',async()=>{
  const button=fakeButton('delete'),events=[];
  bindHistoryActions({querySelectorAll:()=>[button]},{post:async(path,body)=>{events.push([path,body]);},
    confirmDelete:text=>{assert.match(text,/检查点/);assert.match(text,new RegExp(id));return true;},
    onDeleted:deleted=>events.push(deleted),refresh:()=>events.push('refresh'),report:()=>{}});
  await button.click();
  assert.deepEqual(events,[[`/api/jobs/${id}/delete`,{confirm_job_id:id}],id,'refresh']);
});

test('a rejected deletion keeps the current result and shows its reason',async()=>{
  const button=fakeButton('delete'),events=[];
  bindHistoryActions({querySelectorAll:()=>[button]},{post:async()=>{throw new Error('被其他任务引用');},
    confirmDelete:()=>true,onDeleted:()=>assert.fail('must preserve result'),refresh:()=>assert.fail('must not refresh'),
    report:(...args)=>events.push(args)});
  await button.click();
  assert.deepEqual(events,[['被其他任务引用',true]]);
  assert.equal(button.disabled,false);
});

test('hide and restore do not request deletion',async()=>{
  for(const action of ['hide','unhide']){
    const button=fakeButton(action),requests=[];
    bindHistoryActions({querySelectorAll:()=>[button]},{post:async(...args)=>requests.push(args),
      confirmDelete:()=>assert.fail('no delete confirmation'),refresh:()=>{},report:()=>{}});
    await button.click();
    assert.deepEqual(requests,[[`/api/jobs/${id}/${action}`,{}]]);
  }
});

test('PyCharm resume explanation promises completed stages only',()=>{
  const text=resumeNotice({spec:{config:{mode:'pycharm'}}});
  assert.match(text,/已完成阶段/);
  assert.match(text,/中断阶段.*重新计算/);
  assert.match(resumeNotice({spec:{config:{mode:'strict'}}}),/随机状态/);
});
