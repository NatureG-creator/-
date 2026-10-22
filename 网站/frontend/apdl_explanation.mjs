const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=value=>value==null||!Number.isFinite(Number(value))?'未取得':Number(value).toLocaleString('zh-CN',{maximumSignificantDigits:7});

export function apdlResultStatus(job={}){
 const e=job.summary?.result_explanation;
 if(!e)return null;
 if(e.loading_complete)return {label:e.outcome==='needs_review'?'已达到目标 · 存在未解释错误':'加载已完成 · 结果待复核',tone:'warning',message:e.title};
 if(e.outcome==='not_requested')return {label:'输入包已生成',tone:'neutral',message:e.conclusion};
 return {label:job.state==='interrupted'||job.state==='stopped'?'已停止 · 查看完成范围':'未完成 · 查看原因',tone:'failed',message:e.title};
}

export function renderApdlExplanation(e){
 if(!e)return '';
 const last=e.last_converged,m=e.material_screening;
 const phase={reading:'读取输入',geometry:'几何与网格',build:'生成输入包',solver:'MAPDL 求解',postprocess:'后处理与结果校核'};
 const facts=[['目标位移',`${fmt(e.target_displacement_mm)} mm`],['已保存末步位移',`${fmt(e.final_displacement_mm)} mm`],['末步加载比例',`${fmt(e.final_time)}（1 表示全部加载）`],['最后收敛子步',last?`载荷步 ${last.load_step} / 子步 ${last.substep}`:'日志中未找到明确完成记录'],['已保存曲线点数',fmt(e.point_count)],['末步加载端反力',`${fmt(e.final_load_N)} N`],['自动缩小步长次数',fmt(e.bisection_count)],['MAPDL 退出码',e.exit_code==null?'未记录':String(e.exit_code)]];
 return `<section class="apdl-explanation" aria-label="结果说明与异常原因"><h4>这次计算究竟完成了什么？</h4><p class="outcome-summary">${esc(e.conclusion)}</p><dl class="outcome-facts">${facts.map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>
 <p class="help-line">“收敛”表示该加载步满足求解器的数值条件；“加载完成”表示算到目标位移；“结果验收”还要核对材料、网格、边界和 RST。三者分别判断。</p>
 ${e.original_error&&!e.loading_complete?`<p class="error-hint"><strong>未完成的直接原因${e.failure_stage?'（'+esc(phase[e.failure_stage]||e.failure_stage)+'）':''}：</strong>${esc(e.original_error)}</p>`:''}
 ${e.original_error&&e.loading_complete&&e.failure_stage==='postprocess'?`<p class="error-hint"><strong>后处理或校核失败的直接原因：</strong>${esc(e.original_error)}。目标加载已达到，数值文件仍需按此原因检查。</p>`:''}
 ${e.recovered_distortion?'<p class="outcome-recovery"><strong>已恢复的试算错误：</strong>中途出现单元畸变，ANSYS 自动缩小步长后重新收敛，并完成全部目标加载。该错误保留为警告。</p>':''}
 <h4>警告与错误：原因、影响和处理方法</h4>
 ${(e.issues||[]).map(issue=>`<article class="outcome-issue ${issue.severity==='error'?'outcome-error':''}"><h5>${esc(issue.severity==='error'?'错误记录':'警告')} · ${esc(issue.title)}</h5><p><strong>原因：</strong>${esc(issue.cause)}</p><p><strong>影响：</strong>${esc(issue.impact)}</p><p><strong>建议：</strong>${esc(issue.action)}</p><details><summary>原始证据 · ${esc(issue.evidence?.file)} 第 ${esc(issue.evidence?.line)} 行（同类记录 ${esc(issue.count)} 次，可能含并行重复）</summary><pre>${esc(issue.evidence?.text)}</pre></details></article>`).join('')||'<p>未找到可识别的日志警告或错误。日志缺失或未匹配到异常，不代表验收通过。</p>'}
 ${m?`<article class="outcome-issue"><h5>材料曲线实际覆盖范围</h5><p>输入曲线最后塑性应变：<strong>${fmt(m.limit)}</strong>；已保存历史中的最大单元节点等效塑性应变：<strong>${fmt(m.maximum)}</strong>。</p>${m.first_time!=null?`<p>首次明确超出曲线：加载比例 <strong>${fmt(m.first_time)}</strong>，单元 <strong>${esc(m.first_element)}</strong>，重心坐标 ${esc((m.first_centroid_mm||[]).map(fmt).join(' / '))} mm。</p><p>说明局部变形已超出材料数据支持范围；求解器仍可继续计算，但后段响应需要材料数据和网格复核。</p>`:'<p>该历史未提示超表，仍需核对积分点结果。</p>'}<p class="help-line">以上读取元素节点筛查 CSV，未在此重新核验其网格来源，也不能作为积分点最大值或材料验收结论。</p></article>`:''}
 ${e.curve_error?`<p class="error-hint">曲线读取或校核原因：${esc(e.curve_error)}</p>`:''}
 ${e.original_error?`<details class="outcome-original"><summary>原任务记录与失败信息（保留原文）</summary><p>原状态：${esc(e.original_state||'未记录')}。${e.loading_complete?'这是历史运行记录；当前加载完成情况按上面的日志与曲线复核说明判断。':'已有部分文件不代表目标加载完成。'}</p><pre>${esc(e.original_error)}</pre></details>`:''}
 <p class="help-line">${esc(e.note)}</p></section>`;
}
