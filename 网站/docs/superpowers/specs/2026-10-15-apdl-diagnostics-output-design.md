# APDL材料、内部自检、网格质量与保存策略设计

## 已批准范围与约束

用户已批准按上一轮建议实施四项并同步GitHub。基线54edc67e9e1ab2aba1cfb11434e9e28d81232057，继续codex/performance-comparison及现有草稿PR1。原CA/GA/MATLAB、49点MISO、网格连接和双面装配公式、边界/加载/NSUBST/NLGEOM/收敛设置不变。默认保存模式仍为OUTRES,ALL,ALL。无真实MAPDL，不伪称求解或科学验收。

## 方案选择

采用在现有分文件命令流上增加独立诊断宏与结构化报告的方案。单纯增加网页提示无法检查实际建模结果；重写建模、改求解器或重采样会超出本次范围。原材料宏和边界宏应逐字与原生成结果对照，原科学代码不移植、不修改。

## 数据与界面

新增options.result_save_mode：all（默认全过程完整）、last（每步曲线+末步完整场）、selected（每步曲线+指定加载比例场）。field_output_times默认[0.25,0.5,0.75,1]，selected要求1–20个有限严格递增非重复数、0<t<=1且包含1；其他模式保留该草稿但不启用。比例是TIME=1静力加载步的无量纲加载比例，不是物理秒。指定时刻按OUTRES规则保存目标时刻或其后的首个收敛子步，不强迫求解器改变时间步。

界面说明RST保存策略与export_full_field末步节点CSV是独立选项。曲线所需NSOL/RSOL始终保存全部子步。last/selected使用OUTRES,ALL,NONE后逐项打开NSOL/RSOL及ESOL；MISO的NLDAT继续保存全部子步，用于材料筛查。all保留原OUTRES,ALL,ALL。

## 材料覆盖

预检输出材料类型、曲线末塑性应变/应力、delta/L、log1p(delta/L)、末点总应变估算last_plastic+last_stress/E及对应均匀延伸。超过仅提示风险，不阻止、不修改曲线；未超过也不能保证腐蚀热点被覆盖。弹性及BISO没有有限MISO表上界，显示不适用。

MISO后处理中读取NL,EPEQ，采用ETABLE的元素节点最大值作为筛查代理，逐保存结果集输出material_coverage_history.csv：time,max_element_nodal_epeq,element_id,centroid_x,centroid_y,centroid_z。保留每步NLDAT。明确这是元素节点结果筛查，不冒充未经核验的积分点极值；未提示超表不代表积分点全部覆盖。记录首次提示的保存结果集与位置。文件缺失/损坏只能显示未核验或报错，不能补零。原nodal_results.csv的EPPL,EQV仍保持原语义。

## 命令流自检

单独宏在网格输入后验证实际节点/单元数量和编号范围，在原边界创建后验证GRIP_FIXED/GRIP_LOADED数量、所在端面及互不重叠。期望数量源于实际nx/ny/layers。失败打印APDL_SELF_CHECK_FAILED标记并退出，不继续SOLVE；外部执行检查识别该标记。实际求解才生成apdl_self_check.csv，不能在仅生成模型时制造通过证据。自检报告使用独立6列CSV：stage,node_count,element_count,fixed_count,loaded_count,passed，共网格和边界两阶段记录。原6列曲线和9列节点结果定义保持不变。

## 网格质量

输入前显式启用SHPP,ON（沿用默认检查），保留CHECK并导出SHPP,STATUS/SUMMARY到mesh_quality_report.txt。Python额外只读计算角点scaled Jacobian、边长比、最差单元ID/位置，分块控制内存。阈值仅作几何预警，不代替ANSYS判据，不自动修网格、不改变积分方案、不放宽质量限制。仅生成模型时标precheck_only；原始MAPDL报告只有实际执行才有，文本存在也不自动等于质量验收通过。

## 解析、兼容与验证

旧任务缺新字段按原模式解析，保持来源签名、进程监管和RST unverified行为。新输入包记录diagnostics schema版本和三个诊断宏/保存策略，求解结果检查实际自检CSV及诊断文件；曲线/节点既有严格检查继续生效。输出目录已有诊断结果拒绝复用。失败任务也能下载原始质量、自检及材料筛查文件。

测试先RED后GREEN：49点及材料/边界/求解物理设置不变、三保存模式、非法时间点、正交/严重剪切网格、材料估算边界、自检失败门控及CSV损坏/缺失、筛查与实际曲线对应、旧任务兼容、前端类型/草稿/预设、真实网页预检/输入包。独立逐任务审阅、完整回归、GitHub树和本地对齐。真实MAPDL对照仍单列限制。

## 官方依据

- OUTRES：https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/ans_cmd/Hlp_C_OUTRES.html
- SHPP：https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/ans_cmd/Hlp_C_SHPP.html
- ETABLE：https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/ans_cmd/Hlp_C_ETABLE.html （MAX为元素节点最大值，不能直接称积分点最大值）
- SOLID185：https://ansyshelp.ansys.com/public/Views/Secured/corp/v242/en/ans_elem/Hlp_E_SOLID185.html
