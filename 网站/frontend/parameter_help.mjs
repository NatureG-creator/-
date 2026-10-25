import {cropSelection,draftReference} from './pointcloud_3d.mjs?v=20261025-height-depth-sync';

const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=v=>Number.isFinite(Number(v))?Number(v).toLocaleString('zh-CN',{maximumSignificantDigits:8}):String(v??'');
const show=v=>typeof v==='object'?JSON.stringify(v):String(v??'留空');
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const text=(x,y,s,extra='')=>`<text x="${x}" y="${y}" ${extra}>${esc(s)}</text>`;
const svg=(body,title)=>`<svg viewBox="0 0 440 230" role="img" aria-label="${esc(title)}"><rect width="440" height="230" rx="8" fill="#f3f7f1"/>${body}</svg>`;
const line=(x1,y1,x2,y2,color='#276e50',extra='')=>`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${color}" ${extra}/>`;
const pointcloudNotes={
 'preprocessing.grid_resolution_mm':['将散乱点映射为规则XY网格的物理间距，单位mm。','间距变小通常使网格更密、内存和处理量增加；改变插值与坑边界采样，不会增加真实扫描信息。'],
 'preprocessing.trim_edge_rows':['网格化后剔除外侧的行列数。','改变实际保留区域，边缘坑可能被排除；与四周比例裁边属于不同步骤。'],
 'preprocessing.trim_legacy_asymmetric':['保留历史前侧删k、后侧删k+1的非对称裁边约定。','关闭会改变保留矩阵的边界和形状，历史结果不能直接混用。'],
 'preprocessing.main_gaussian_sigma':['主流程高斯滤波的尺度，按网格单元计。','增大会抑制细小起伏，也可能降低窄坑峰值、改变极值和后续指标；不是分水岭专用sigma。'],
 'preprocessing.remove_edge_ratio':['从XY包围框每一侧删除的边缘比例。','改变裁边点云范围；比例必须小于0.5，不能当成总共删除的比例。'],
 'preprocessing.invert_z_on_load':['读取原始扫描时是否执行Z取负。','决定高程符号方向，影响后续处理；与共同坐标视图“向内为正”的显示说明应分别核对。'],
 'preprocessing.reverse_z_after_edge_removal':['裁边反转脚本是否执行Z新=Z最大+Z最小−Z旧。','反射高程起伏，保持数值范围；不是为表面增加实际厚度。'],
 'preprocessing.interpolation_method':['散乱XYZ点投影到规则网格时的插值方法。','改变格点高程的估计方法；nearest、linear、natural的平滑性不同，实际覆盖范围仍由扫描决定。'],
 'preprocessing.missing_fill_method':['规则网格出现缺失值时采用的填补方法。','填补的是未覆盖格的估计值，不能当成新增的实测点。'],
 'reference.flat_column_count':['完整扫描左侧参与经验参考面统计的列数N。','改变H_min、H_max的统计区域，可能改变参考高度和经验深度；较多列不一定更可靠，不能混入明显腐蚀区。'],
 'reference.flat_height_ratio':['参考区极差中的相对位置r，0.2就是20%，不是第20百分位。','H_flat=H_min+r×(H_max−H_min)。固定参考区时r增大使H_flat增大；共同高程向内为正时，d=H−H_flat相应减小。'],
 'reference.corrosion_column_count':['完整扫描中央用于原流程均匀腐蚀分量统计的列数M。','改变中央统计区的最高H及H_corroded−H_flat；不等于局部扫描的列数，也不会直接裁剪现有共同坐标缓存。'],
 'pit_detection.min_prominence':['极值相对邻域均值的最低突出程度。','降低通常允许更多浅小起伏通过筛选；最终坑数还受距离、邻域和分水岭控制。'],
 'pit_detection.min_distance':['两个保留坑中心之间的最小网格距离。','增大通常使相近候选竞争并被筛掉；换算物理距离还需乘网格间距。'],
 'pit_detection.neighborhood':['极值筛选所使用的方形邻域行列数。','改变“相对于邻域”的比较范围；当前接口要求两个相同的正整数。'],
 'pit_detection.edge_margin':['极值检测时跳过的最外层网格数量。','增大会减少边缘参与检测的范围，不会删除源扫描文件。'],
 'pit_detection.depth_reference_mode':['当前仅支持global_minimum：按传入分析矩阵的全局最小值定义坑深基准。','它属于局部坑深定义，不是完整扫描的20%经验面；当前后端不接受任意新模式。'],
 'pit_detection.diameter_mode':['当前仅支持mean_xy_span：用坑边界X/Y跨度的平均值定义坑径。','边界改变会改变坑径和径深相关指标；不是等面积圆直径。'],
 'watershed.threshold':['背景条件为distance > r×max(distance)，distance为到种子点的距离。','在距离场固定时r增大，满足背景条件的范围减少；实际边界还依赖梯度、种子和分水岭，不能仅凭阈值预言坑数。'],
 'watershed.gaussian_sigma':['计算分水岭梯度前的高斯平滑尺度。','改变梯度和分割边界；与主流程高斯平滑分别设置。'],
 'watershed.local_contrast_window':['局部标准差stdfilt使用的窗口边长。','改变局部对比度估计，继而影响梯度屏障位置。'],
 'watershed.local_contrast_factor':['局部梯度阈值=系数×局部对比度。','梯度低于该阈值的位置被赋为屏障值；增大系数通常会使更多位置满足屏障条件。'],
 'watershed.gradient_barrier_value':['给低于局部阈值的梯度位置赋予的屏障数值。','改变梯度场中的屏障强度；最终分割需重新运行算法，说明图不替代分水岭结果。'],
 'watershed.gradient_operator':['计算X/Y梯度的算子。','影响梯度响应与边界，当前接受sobel、prewitt、central、intermediate、roberts。'],
 'watershed.boundary_holes':['提取区域轮廓时是否包含内部孔洞边界。','改变轮廓提取方式；noholes忽略内孔，holes包含内孔，后续代码仍按既定方式选取轮廓。'],
 'distribution.depth_mm_to_um':['mm到μm的单位换算系数。','与Python六指标接口联动时固定为1000；改变它会改变数值单位，不能当成调参提速。'],
 'distribution.sjb_reciprocal_numerator':['对数比值变换log(分子/sjb)的分子。','当前六指标接口要求为1；改变会整体平移对数指标，不能任意修改。'],
 'distribution.hist_bin_width':['直方图每个区间的宽度。','改变分箱外观和每箱计数；不会增加坑样本，也不会单独改变原始样本拟合的μ和σ。'],
 'distribution.hist_normalization':['直方图柱高所采用的归一化定义。','pdf表示概率密度，count表示数量；更换定义会改变纵轴含义，需要与拟合曲线的单位相匹配。'],
 'distribution.hist_face_color':['直方图的RGB颜色，三个分量均在0～1。','只改变柱体显示颜色，不改变坑样本及拟合参数。'],
 'distribution.fit_distribution':['分布拟合的模型。','当前代码从拟合对象读取mu和sigma，接口只支持Normal；不能只修改文本来引入其他分布。'],
 'distribution.fit_curve_points':['绘制拟合密度曲线时的采样点数。','只控制理论曲线绘制的疏密，不增加实测样本。'],
 'distribution.fit_line_width':['分布拟合曲线的绘制线宽。','影响图形外观，不改变拟合得到的μ和σ。'],
 'figure.surface_clim':['保留的历史曲面色标范围。','当前新主流程按实际正深度自动生成色标，不读取此历史范围；修改不会改变当前主流程的结果。'],
 'apdl.dx_mm':['点云文本导出时X向坐标间距。','改变导出坐标的物理尺度；不是对原矩阵自动重采样。未显式覆盖时跟随点云网格间距。'],
 'apdl.dy_mm':['点云文本导出时Y向坐标间距。','改变导出坐标的物理尺度；应与矩阵行方向采样一致。未显式覆盖时跟随点云网格间距。'],
 'apdl.grid_matrix_variable':['读取并导出的二维高程矩阵变量名。','Z_filled或F_filled对应不同来源；不会自动把高程转换成腐蚀深度。'],
 'apdl.x_start_mm':['导出X坐标的起点。','整体平移导出坐标，不改变矩阵高程；错用起点可能影响后续两面配准。'],
 'apdl.y_start_mm':['导出Y坐标的起点。','整体平移导出坐标，不改变矩阵高程；应与X起点及间距共同核对。'],
 'apdl.delimiter':['坐标文本中数值列之间的分隔符。','影响后续软件如何拆分列，不改变内部double矩阵。'],
 'apdl.precision':['文本导出格式，例如%.6f表示保留6位小数。','影响文本舍入误差，不改变原始矩阵；应按几何精度需要设置。'],
 'apdl.newline':['文本导出的换行约定，pc或unix。','影响文本文件兼容性，不改变几何和数值定义。'],
};

export function referenceAnalysis(common,{columns,ratio,corrosionColumns=168}){
 if(columns==null||columns===''||ratio==null||ratio==='')throw new Error('请填写参考列数与极差比例');
 const grid=common.section_grid,r=draftReference(grid,columns,ratio),m=Number(corrosionColumns);
 if(!Number.isInteger(m)||m<1||m>grid.x.length)throw new Error('中央统计列数须为当前完整矩阵范围内的正整数');
 const start=Math.round((grid.x.length-(m-1))/2),stop=start+m;
 if(start<0||stop>grid.x.length)throw new Error('中央统计区超出当前完整矩阵');
 let centralMax=-Infinity;for(const row of grid.grid)for(let j=start;j<stop;j++)centralMax=Math.max(centralMax,row[j]);
 return {...r,centralX:[grid.x[start],grid.x[stop-1]],centralColumns:[start+1,stop],centralMax,uniformComponent:centralMax-r.height,
  delta:r.height-common.reference_height_mm,localMeanDepth:common.mean_depth_mm+common.reference_height_mm-r.height};
}

export function gaProbabilityPreview({basePx=.5,basePm=.5,decayRate=.2,maxgen=101}={}){
 if(![basePx,basePm,decayRate,maxgen].every(Number.isFinite)||!Number.isInteger(maxgen)||maxgen<1)throw new Error('概率公式需要有限系数和正整数maxgen');
 if(maxgen===1)return [];
 const count=Math.min(60,maxgen-1);
 return Array.from({length:count},(_,i)=>{const gen=count===1?1:1+i*(maxgen-2)/(count-1);return {gen,px:clamp(basePx*Math.exp(-decayRate*gen/maxgen),.6,.95),pm:clamp(basePm+(.3-basePm)*gen/maxgen,.01,.3)};});
}

function family(d){
 const k=d.key,l=d.label||'',s=k+' '+l;
 if(/^(reference\.|preview\.(ratio|columns))/.test(k))return 'reference';
 if(/preview\.(length|width|centerX|centerY)|measured-region-(length|width|center)|region-(length|width|center)|override_(length|width|offset)|offset_[xy]|patch_(x|y)|目标.*[长宽]|裁剪.*[长宽]/i.test(s))return 'crop';
 if(/material_model|plastic_curve|E_MPa|poisson|yield|tangent|strain_type|strain_unit|stress_unit/.test(k))return 'material';
 if(/platform|thickness|layers|中间节点|原始厚度|剩余厚度/.test(s))return 'layers';
 if(/(^GEOMETRY_CONFIG\.)|(^preprocessing.grid_resolution)|grid_[wln]|grid_mode|space_[xyz]|target_d[xy]|cell_[xyz]|dx_mm|dy_mm|(^apdl.[xy]_start)|nx$|ny$/.test(k))return 'grid';
 if(/sigma_column|validation|folds|验证方式|验证.*分组/.test(s))return 'validation';
 if(/seed|种子/.test(s))return 'seed';
 if(k==='mode'||/sim-run-mode|MULTI_CASE_CONFIG.run_mode|workers|threads|reuse_process_pool|arch$|use_taichi|workload|运行模式|计算模式|池生命周期/.test(s))return 'compute';
 if(/maxgen|nind|selected_count|bits_per_param|(^|\.)F$|^GA_CONFIG|交叉|变异|probability|p_[hvop]|alpha|cl_threshold|CA_CONFIG/.test(s))return 'ga';
 if(/sigma|smooth|平滑|gaussian/.test(s))return 'smooth';
 if(/threshold|min_prominence|min_distance|neighborhood|watershed|pit_detection|分水岭|极值|对比度/.test(s))return 'pits';
 if(/trim|edge|remove_edge|裁边|invert_z|reverse_z|反转/.test(s))return 'trim';
 if(/hist_|distribution|分布|柱宽/.test(s))return 'histogram';
 if(/figure|FIGURE|font|cmap|color|dpi|linewidth|line_width|marker|plot|title|[xy]_label|[xy]_unit|[xy]_scale|图宽|图高|图形|配色/.test(s))return 'style';
 if(/load|displacement|boundary|grip|substep|nsubst|solver|求解|位移|夹持/.test(s))return 'load';
 if(/fit|prediction|formula|model|loss|metric|x_column|y_column|拟合|回归|预测/.test(s))return 'fit';
 return 'flow';
}

const familyNotes={
 reference:['经验参考面的统计设置。','改变候选参考位置或统计区域；已验证20%缓存仍保留，只有显式运行新的处理任务才会产生新结果。'],
 crop:['以物理坐标定义要保留的矩形区域。','影响保留的节点和覆盖范围。共同坐标裁剪保留原节点，修改后需要重新确认才能导出。'],
 grid:['几何尺寸、离散网格或坐标间距的设置。','影响网格规模或坐标尺度；节点/元胞、mm/μm应按当前模块区分，实际范围由预检校核。'],
 material:['材料本构或试验曲线解释所使用的输入。','影响后续材料转换或有限元应力响应；说明图不进行有限元求解，材料应采用实测值。'],
 layers:['原板厚度、平台或厚度方向离散的设置。','影响后续几何或网格预检。原始厚度、腐蚀损失、剩余厚度是不同量，只有基准明确时才能组合。'],
 validation:['拟合数据权重或训练/验证划分的设置。','影响评价方式或样本划分；分组与时间顺序需按实验设计确定，说明图仅演示划分。'],
 seed:['控制对应流程的随机序列起点。','改变种子可能改变随机划分或寻优轨迹；同种子的一致性仍依赖引擎、配置和运行环境。'],
 compute:['计算后端、并行或运行方式的设置。','影响调度、资源或执行路径。更多进程不保证更快；此处不会调整正在运行的任务。'],
 ga:['CA–GA计算或搜索控制参数。','影响新任务的搜索空间、演化规则、评价规模或停止条件；修改后需重新验证结果。'],
 smooth:['对网格起伏进行平滑的尺度或开关。','改变细节与噪声的保留程度；观察图是参数作用示意，真实峰值和坑数要重新处理后确定。'],
 pits:['候选坑、梯度或区域分割的判定参数。','影响候选筛选和边界，可能传递到坑深、坑径及分布指标；不能由单个阈值直接预测真实坑数。'],
 trim:['边缘排除或高程符号处理的设置。','影响保留范围或方向约定；不会修改原始扫描文件。'],
 histogram:['统计样本的分箱、单位或分布呈现设置。','应区分样本数据、单位变换、拟合模型与外观；说明图不重新拟合当前实验数据。'],
 style:['当前模块的图形呈现设置。','通常影响图形显示或导出外观；是否进入科学计算以参数目录中的使用范围为准。'],
 load:['有限元载荷、约束或求解控制设置。','影响边界条件、求解过程或结果保存；示意中的箭头不是已经求得的位移场或应力场。'],
 fit:['数据映射、函数拟合或预测的设置。','影响后续使用的数据、拟合条件或预测范围；真实系数和误差需要明确提交拟合任务后得到。'],
 flow:['当前模块使用的输入、选项或数据管理字段。','按当前选项进入该模块已有的预检或显示流程；不会因为打开说明而提交任务。'],
};

const moduleNotes={
 'visual-variable':['上传文件中要读取的数组或数据变量。','决定读取哪一个保存变量；应核对形状、单位和高程/深度含义，不会自动把未知变量当成腐蚀深度。'],
 'visual-stage':['读取已有模拟结果中的哪个阶段快照。','只改变展示的数据阶段，不推进、恢复或重跑原模拟。'],
 'library-folder':['成果库当前浏览或另存成果所使用的目录。','切换目录不移动原任务或修改数值；真正归档/另存仍需使用原有操作按钮。'],
 'include-hidden-jobs':['是否把已隐藏的任务也列入运行记录。','只改变列表筛选，不取消隐藏、不删除数据，也不停止或恢复任务。'],
 'apdl.corrosion_mode':['选择无腐蚀平板、单面、双面对称或双面独立等几何模式。','决定正反面形貌的来源和几何组合；双面对称是复用同一深度场，不代表两份独立测量。'],
 'apdl.surface_grid_mode':['双面形貌使用严格同网格，还是共同XY映射。','严格模式保留匹配的原节点；共同XY模式按物理范围交集进行显式双线性映射，不外推。'],
 'benchmark-threads_per_worker':['基准中每个计算进程允许使用的线程数量。','与进程数相乘计入CPU预算；只影响新建基准方案，不调整正在运行的科学任务。'],
 'benchmark-cpu_budget':['本次基准允许使用的逻辑CPU预算。','预检约束进程×线程规模；不能据此保证没有共享缓存或内存竞争。'],
 'benchmark-repeats':['预热之后用于计时统计的重复次数。','更多重复可观察耗时离散程度，也增加基准成本；不是CA步数或GA代数。'],
 'benchmark-seeds':['本次基准要依次评估的随机种子列表。','增加种子会增加总工作量，并帮助判断结果或性能是否依赖某一个种子。'],
 'seed-mode':['新任务使用固定种子，或提交时自动生成种子的方式。','固定种子便于复核；自动种子使不同提交使用不同随机轨迹，具体种子仍应随任务保存。'],
 'GEOMETRY_CONFIG.grid_w':['CA网格X方向的元胞数量。','与Y向数量、厚度层数相乘得到三维元胞总数；改变X向覆盖和计算规模，物理长度还需乘面内元胞尺寸。'],
 'GEOMETRY_CONFIG.grid_l':['CA网格Y方向的元胞数量。','影响Y向覆盖与三维元胞总数，物理长度还需乘面内元胞尺寸；不是单位为mm的试件宽度。'],
 'GEOMETRY_CONFIG.grid_n':['CA计算域厚度方向的元胞层数。','与厚向元胞尺寸共同决定CA计算域深度；它与腐蚀前钢板原始厚度分别记录。'],
 'GA_CONFIG.bits_per_param':['每个待反演参数使用的二进制编码位数。','b位提供2^b个编码级别；增加位数提高搜索离散精细程度，并增加染色体长度。'],
 'GA_CONFIG.base_px':['交叉概率公式的基础系数；实际概率还经过随代数变化及截断。','当前px=clip(base_px×exp(−decay_rate×gen/maxgen),0.6,0.95)。例如base_px=0.5时实际被下限截为0.6，不能将基础值直接当成实际概率。'],
 'GA_CONFIG.base_pm':['变异概率公式的基础系数；实际概率还经过线性变化及截断。','当前pm=clip(base_pm+(0.3−base_pm)×gen/maxgen,0.01,0.3)。例如基础值0.5会被上限截为0.3。'],
 'GA_CONFIG.decay_rate':['交叉概率指数项的变化速率。','通过exp(−rate×gen/maxgen)影响交叉概率，但受到0.6～0.95的截断限制；不会直接改变CA演化步数。'],
 'GA_CONFIG.sigma_share':['小生境共享中参数向量欧氏距离的阈值σ。','通过max(1−距离/σ,0)影响共享权重与选择适应度，作用是保持搜索多样性；不是表面高斯滤波sigma。'],
 'CA_CONFIG.alpha_passive':['氯离子因子参与钝化概率修正的系数。','现有规则含p_passive_base×(1−alpha_passive×cl_factor)；影响CA状态转变，不能按名称简单理解成“越大越钝化”。'],
 'CA_CONFIG.initial_d':['个体CA初始化时扩散参数场的基础值。','影响初始扩散条件和后续演化，单位与意义沿用模型定义；不是实验腐蚀深度。'],
 'CA_CONFIG.initial_cl':['个体CA初始化时氯离子浓度场的基础值。','影响初始浓度及后续扩散、腐蚀条件；修改会改变模型初始条件。'],
 'CA_CONFIG.initial_enhancement_steps':['启用初期增强因子的CA步数k0，0表示不启用。','在k≤k0时使用随步数衰减的附加因子；影响初期概率规则。'],
 'CA_CONFIG.initial_enhancement_beta':['初期增强因子的起始系数β。','与k0共同决定1+(β−1)×(k0−k+1)/k0；k0=0时该增强不启用。'],
 'CA_CONFIG.convex_height_limit':['凸起相关破坏判定使用的高度上限。','影响凸起点判定和后续状态转变，采用既定模型尺度；不能等同于原始板厚。'],
 'MULTI_CASE_CONFIG.enabled':['是否启用多工况任务编排。','只控制提交方式；各工况仍使用自己的目标、种子和冻结配置。'],
 'MULTI_CASE_CONFIG.run_mode':['选择单工况或批量工况的编排方式。','影响创建哪些独立任务，不会把各工况的腐蚀形貌自动合并。'],
 'MULTI_CASE_CONFIG.parallel_case_workers':['同时运行的独立工况数量上限。','还需与每个工况内部的并行进程数共同核对CPU和内存预算。'],
 'MULTI_CASE_CONFIG.sequential_enabled':['是否启用按顺序执行工况的入口。','影响工况调度方式；不会改变每个工况内部的物理规则。'],
 'MULTI_CASE_CONFIG.parallel_enabled':['是否启用并行执行独立工况的入口。','允许工况并行会增加同时资源需求，不保证总耗时按工况数等比例缩短。'],
 'MULTI_CASE_CONFIG.cases':['独立工况的清单，包括名称、目标来源和对应设置。','决定各工况任务的输入和追溯关系；修改清单不会修改正在运行任务的冻结规格。'],
 'ACTIVE_STAGE_TARGET_DATA':['多阶段实测六指标目标矩阵，每行对应一个阶段。','列顺序为平均腐蚀深度、不均匀深度、对数径深比μ、对数坑深μ、对数径深比σ、对数坑深σ；前两列单位μm。'],
 'SINGLE_STAGE_TARGET_DATA':['单阶段反演使用的一行六指标目标。','按同一六指标顺序参与误差评价，不是六个可互换的无单位数值。'],
 'apdl.E_MPa':['弹性模量E，表示弹性段应力—应变曲线的斜率，单位MPa。','影响材料刚度；在给定几何、弹性小变形条件下会影响力—位移响应。它不是屈服强度。'],
 'apdl.poisson_ratio':['泊松比ν，单轴弹性状态下ν=−横向应变/轴向应变。','控制横向收缩与三维弹性耦合，当前范围为−1<ν<0.5；不能从曲线外观猜测。'],
 'apdl.yield_MPa':['BISO材料开始进入塑性的屈服应力，单位MPa。','改变弹塑性转折位置；应结合弹性模量和试验数据设置。'],
 'apdl.tangent_MPa':['BISO屈服后应力—总应变曲线的切线模量Et。','控制屈服后的硬化斜率，要求0≤Et<E；不是塑性应变表中的独立应力值。'],
 'apdl.plastic_curve':['MISO材料的[塑性应变,真实应力MPa]二维曲线。','用于多线性硬化；塑性应变首点为0、之后递增。输入曲线不是已求得的结构响应。'],
 'apdl.layers':['厚度方向的实体单元层数。','N层单元对应N+1层节点平面、N−1层中间节点；更多层会增加单元数。'],
 'apdl.intermediate_node_layers':['厚度两外表面之间的中间节点层数。','K层中间节点对应K+2层节点平面、K+1层单元；按中间节点模式时使用。'],
 'apdl.thickness_mm':['试件腐蚀前的原始板厚，单位mm。','剩余厚度须在一致基准下扣除正反面腐蚀损失；不能把点云起伏直接当成板厚。'],
 'apdl.platform_reference_mode':['平台参考面采用手动实测均值，或已有验证的经验参考链。','手动均值校准与经验参考链采用不同的来源依据；切换后应重新预检，原始数据不会因此被覆盖。'],
 'apdl.platform_top_mean_depth_mm':['正面相对原始参考面的实测平均腐蚀深度。','手动模式用整体平移将输入正面深度均值校准到此值，保留局部起伏；经验参考模式不使用该手动值。'],
 'apdl.platform_bottom_mean_depth_mm':['反面相对原始参考面的实测平均腐蚀深度。','手动双面模式分别校准反面均值；与正面损失共同影响剩余厚度。'],
 'fit.folds':['随机K折交叉验证划分的折数。','每轮留一折验证、其他折训练；分组或按时间验证需要遵守相应划分约束。'],
 'fit.sigma_column':['观测Y标准差σ所在的数据列。','影响加权残差或拟合权重；σ需为有依据的观测不确定度，不能为了得到更好分数任意填写。'],
 'fit.prediction_min':['预测曲线X范围的下界。','超出训练数据范围属于外推；改变绘制范围不等于新增了实验数据。'],
 'fit.prediction_max':['预测曲线X范围的上界。','超出训练数据范围属于外推；远端预测可靠性不能仅由拟合曲线平滑程度判断。'],
 'fit.seed':['拟合验证中随机划分使用的种子。','影响随机划分的可重复性；不改变原始观测数据。'],
};

function additionalNotes(d){
 const k=d.key,leaf=k.split('.').at(-1);
 if(/^(STAGE_GA_CONFIG|SINGLE_STAGE_GA_CONFIG)\./.test(k))return ({
  F:['每个个体一次CA模拟的演化步数上限。','改变模拟演化长度及评价工作量；F不是遗传算法的代数，调整它可能改变形貌结果。'],
  nind:['每代参与遗传搜索的种群个体数量。','影响评价次数与搜索多样性；不是并行进程数，不能据此线性推算完整任务耗时。'],
  selected_count:['每代选择并保留的个体数设置。','影响下一代构成和搜索行为，需要与种群数量共同满足原实现的约束。'],
  maxgen:['遗传迭代的终止代号上界。','当前实现使用range(当前代号,maxgen)，上界不包含；新任务通常从1开始，101对应标号1～100。恢复任务从保存的代号继续。'],
  parallel_workers:['一个工况内部并行评价个体的worker数量。','影响进程调度和资源，严格模式使用单进程；不能把新增worker当作改变F或种群数量。'],
 })[leaf];
 if(k.startsWith('FIGURE_CONFIG.')){
  if(/figsize|panel_size/.test(leaf))return [`${d.label}设置对应图或子图的宽高，单位英寸。`,'影响画布和排版尺寸；像素大小还与DPI有关，不改变科学数组。'];
  if(/dpi/.test(leaf))return [`${d.label}设置位图每英寸的像素数。`,'同一物理图幅下，增大DPI增加像素和文件体积，不增加实测数据分辨率。'];
  if(/cmap/.test(leaf))return [`${d.label}选择数值映射到颜色的配色方案。`,'改变颜色表达，不改变原始高程或深度；仍需核对色标范围和单位。'];
  if(/elev|azim/.test(leaf))return [`${d.label}设置三维观察角度，单位度。`,'改变观察方向，不旋转或重新配准原始数据坐标。'];
  return [`${d.label}属于对应绘图入口的外观设置。`,'影响图形呈现，是否被当前任务使用以目录范围说明为准。'];
 }
 if(k.startsWith('PATH_CONFIG.')||k==='ROOT')return [`${d.label}指定相应类别的数据路径或任务根位置。`,'影响新任务的文件定位或成果位置，不改变数值单位与算法；运行中任务继续沿用其冻结位置。'];
 if(k.startsWith('FRACTURE_CONFIG.'))return [`${d.label}是独立材料/断裂分析使用的设置。${({y0:'用于断裂应变预测关系中的基准项。',fixed_k_sp:'固定K_sp时用于识别对应η_sp。',fixed_eta_sp:'固定η_sp时用于识别对应K_sp。',minimum_experiment_samples:'规定进行分析所需的最少试验样本数。',curve_points:'规定生成曲线的采样点数。',curve_drop_ratio:'规定峰值之后响应下降的判定比例。',curve_sustain_points:'规定下降判定需要连续满足的点数。'})[leaf]||''}`,'只在相应独立脚本或分析入口使用，当前CA/GA计算链不消费此字段。'];
 if(!d.help){
  if(/来源|源任务|数据源/.test(d.label))return [`${d.label}用于选择后续读取的数据或已有任务。`,'改变后续输入的来源与追溯关系；应重新核对单位、变量和来源范围，不修改被选中的原始文件。'];
  if(/目录|路径|文件夹|自定义名称|任务名称/.test(d.label))return [`${d.label}用于识别任务或定位输入/成果。`,'影响组织和保存位置，不改变科学公式或原始数值。'];
  if(/单位/.test(d.label))return [`${d.label}说明对应数值使用的物理单位。`,'影响后续数值解释或单位转换；不能通过修改单位标签来代替有依据的数据换算。'];
  if(/显示|视图|竖向比例|观察|色标/.test(d.label))return [`${d.label}控制当前观察界面的呈现。`,'改变可见内容、视角或比例，不直接改变保存的科学数组；放大显示不等于实际尺寸变化。'];
  if(/列|映射/.test(d.label))return [`${d.label}指定表格字段在本次流程中的用途。`,'影响哪个字段被当作自变量、响应量、分组或坐标；需按实验定义选择，不能只按曲线外观猜测。'];
 }
 return null;
}

function referenceDiagram(common,a){
 const g=common.section_grid,row=g.grid[Math.floor(g.y.length/2)],lo=Math.min(...row,a.height,common.reference_height_mm)-.03,hi=Math.max(...row,a.height,common.reference_height_mm)+.03;
 const x=v=>42+(v-g.x[0])/(g.x.at(-1)-g.x[0])*370,y=v=>48+(v-lo)/(hi-lo)*142;
 const profile=row.map((v,i)=>i%Math.max(1,Math.ceil(row.length/220))===0||i===row.length-1?`${x(g.x[i])},${y(v)}`:'').filter(Boolean).join(' ');
 return svg(text(16,18,'实测完整矩阵；H向内为正、图中向下')+text(16,35,'橙：候选参考区　紫：中央统计区')+
  `<rect x="${x(a.x[0])}" y="48" width="${x(a.x[1])-x(a.x[0])}" height="142" fill="#dca855" opacity=".23"/><rect x="${x(a.centralX[0])}" y="48" width="${x(a.centralX[1])-x(a.centralX[0])}" height="142" fill="#9474b6" opacity=".13"/><polyline points="${profile}" fill="none" stroke="#276e50" stroke-width="2"/>`+
  line(42,y(common.reference_height_mm),412,y(common.reference_height_mm),'#167e9e','stroke-dasharray="6 4"')+line(42,y(a.height),412,y(a.height),'#bc317c','stroke-dasharray="2 4"')+
  text(42,209,`${fmt(g.x[0])} mm`)+text(412,209,`${fmt(g.x.at(-1))} mm`,'text-anchor="end"'), '当前实测参考区、中央统计区与候选参考面');
}

function diagram(d,f,values,common,analysis){
 const n=Number(d.value),k=d.key,v=Number.isFinite(n)?n:1;
 if(['GA_CONFIG.base_px','GA_CONFIG.base_pm','GA_CONFIG.decay_rate'].includes(k)){
  const points=gaProbabilityPreview({basePx:Number(values['GA_CONFIG.base_px']??.5),basePm:Number(values['GA_CONFIG.base_pm']??.5),decayRate:Number(values['GA_CONFIG.decay_rate']??.2),maxgen:Number(values[values['sim-run-mode']==='single'?'SINGLE_STAGE_GA_CONFIG.maxgen':'STAGE_GA_CONFIG.maxgen']??101)});
  const curve=key=>points.map((p,i)=>`${45+i*345/Math.max(1,points.length-1)},${185-p[key]*130}`).join(' ');
  return svg(text(18,22,'按现有公式计算 · 非寻优或模拟结果')+line(45,185,400,185)+line(45,55,45,185)+`<polyline points="${curve('px')}" fill="none" stroke="#167e9e" stroke-width="2"/><polyline points="${curve('pm')}" fill="none" stroke="#bc317c" stroke-width="2"/>`+text(18,214,points.length?`首代px=${fmt(points[0].px)}，pm=${fmt(points[0].pm)}；蓝交叉，粉变异`:'maxgen=1，当前循环没有演化代'),'实际交叉和变异概率公式');
 }
 if(f==='reference'&&analysis)return referenceDiagram(common,analysis);
 if(f==='reference')return svg(text(18,22,'极差位置示意 · 不是实测高程')+line(80,55,80,185,'#6f7f74','stroke-width="3"')+line(72,55,88,55)+line(72,185,88,185)+text(100,59,'H_min（r=0）')+text(100,189,'H_max（r=1）')+line(45,55+clamp(Number(values.ratio??.2),0,1)*130,380,55+clamp(Number(values.ratio??.2),0,1)*130,'#bc317c','stroke-width="2"')+text(18,218,`N=${values.columns??200}列；r=${fmt(values.ratio??.2)}；不是百分位数`),'经验参考高度公式示意');
 if(f==='crop'){
  const g=common?.section_grid;if(g){const p=values.crop,s=cropSelection(g,p),x=z=>35+(z-g.x[0])/(g.x.at(-1)-g.x[0])*370,y=z=>65+(z-g.y[0])/(g.y.at(-1)-g.y[0])*110,b=s.shown;
   return svg(text(18,22,'实测坐标范围与裁剪节点 · XY俯视')+`<rect x="35" y="65" width="370" height="110" fill="#dcebdc" stroke="#a8bda7"/>`+(b?`<rect x="${x(b.x[0])}" y="${y(b.y[0])}" width="${x(b.x[1])-x(b.x[0])}" height="${y(b.y[1])-y(b.y[0])}" fill="#187947" opacity=".25" stroke="#187947" stroke-dasharray="5 3"/>`:'')+text(18,205,`${s.rows}×${s.columns}=${s.pointCount}原节点，覆盖${fmt(s.coverage*100)}%`),'当前实测坐标裁剪范围');}
  return svg(text(18,22,'范围关系示意 · 未获得对应实测矩阵')+`<rect x="35" y="55" width="365" height="125" fill="#dcebdc" stroke="#88a88e"/><rect x="${80+clamp(v,-50,100)}" y="80" width="${clamp(Math.abs(v)*3,35,160)}" height="65" fill="#187947" opacity=".3"/>`+text(18,214,`当前${d.label}：${show(d.value).slice(0,40)}`),'裁剪范围参数示意');
 }
 if(f==='grid'){
  const gx=Number(values['GEOMETRY_CONFIG.grid_w']),gy=Number(values['GEOMETRY_CONFIG.grid_l']),gz=Number(values['GEOMETRY_CONFIG.grid_n']);
  const count=/GEOMETRY/.test(k)&&[gx,gy,gz].every(z=>Number.isInteger(z)&&z>0)?gx*gy*gz:null;
  const cells=clamp(Math.round(k.includes('grid_resolution')?4/Math.max(v,.05):Math.log2(Math.abs(v)+2)*2),3,18);
  return svg(text(18,22,count?`当前设置：${gx}×${gy}×${gz}=${fmt(count)}元胞`:'网格关系示意 · 不重采样源数据')+Array.from({length:cells+1},(_,i)=>line(55+i*320/cells,55,55+i*320/cells,185,'#719c81')+line(55,55+i*130/cells,375,55+i*130/cells,'#719c81')).join('')+text(18,216,`当前${d.label}：${show(d.value).slice(0,42)}`),'网格与当前离散设置');
 }
 if(f==='smooth'||f==='trim'){
  const strength=clamp(Math.abs(v),0,10),curve=(filtered)=>Array.from({length:100},(_,i)=>`${30+i*3.8},${110+30*Math.sin(i*.1)+(filtered?15/(1+strength):15)*Math.sin(i*1.25)}`).join(' ');
  return svg(text(18,22,f==='smooth'?'合成起伏示意 · 不是C17处理结果':'符号/裁边关系示意 · 非重新处理')+`<polyline points="${curve(false)}" fill="none" stroke="#adb9ad"/><polyline points="${curve(true)}" fill="none" stroke="#276e50" stroke-width="2"/>`+(f==='trim'?`<rect x="30" y="50" width="${clamp(Math.abs(v)*10,10,120)}" height="125" fill="#b86b53" opacity=".2"/>`:'')+text(18,210,`参数=${show(d.value).slice(0,35)}；真实形貌需显式重新处理`),'参数对合成起伏或边缘的作用示意');
 }
 if(f==='pits'){
  const threshold=clamp(v,0,1),radius=/min_distance|neighborhood|window/.test(k)?clamp(Math.abs(v)*2,10,70):25;
  return svg(text(18,22,'种子与判定范围示意 · 不代表实际坑数')+`<circle cx="140" cy="115" r="${radius}" fill="#cee5d7" stroke="#276e50"/><circle cx="300" cy="115" r="${radius}" fill="#e5d7ed" stroke="#88549c"/>`+text(136,119,'A')+text(296,119,'B')+line(60,185,380,185,'#9bb0a0')+line(60+threshold*320,178,60+threshold*320,194,'#b05b45','stroke-width="3"')+text(18,215,`当前${d.label}：${show(d.value).slice(0,40)}`),'候选种子、邻域或阈值示意');
 }
 if(f==='layers'){
  const intermediate=values['apdl.thickness_layer_mode']==='intermediate_nodes',layers=Number(intermediate?Number(values['apdl.intermediate_node_layers'])+1:values['apdl.layers']??(k.includes('layers')?v:8)),num=clamp(Math.round(layers||1),1,16);
  return svg(text(18,22,'厚度/平台关系示意 · 不是已生成网格')+`<path d="M45 70 L180 70 L210 100 L340 100 L370 70 L405 70 L405 180 L45 180 Z" fill="#dce8dc" stroke="#276e50"/>`+Array.from({length:num+1},(_,i)=>line(45,105+i*70/num,405,105+i*70/num,'#7aa18a')).join('')+text(18,214,Number.isInteger(layers)&&layers>0?`${layers}层单元；${layers+1}层节点平面（示意最多画16层）`:`当前${d.label}：${show(d.value).slice(0,30)}`),'平台、腐蚀区与厚度分层关系');
 }
 if(f==='histogram'||f==='style'){
  const arr=Array.isArray(d.value)?d.value:null,rgb=arr?.length===3&&arr.every(z=>Number.isFinite(z)&&z>=0&&z<=1)?`rgb(${arr.map(z=>Math.round(z*255)).join(',')})`:'#8cbca4';
  const bins=k.includes('bin_width')?clamp(Math.round(2/Math.max(v,.02)),3,30):10,width=340/bins,font=/font_size/.test(k)?clamp(v,6,25):12;
  const stroke=/line.*width|linewidth/.test(k)?clamp(v,.2,8):2,markers=/marker|cross_size/.test(k)?clamp(Math.sqrt(Math.abs(v)),1,10):0;
  const curve=Array.from({length:50},(_,i)=>`${45+i*6.8},${180-100*Math.exp(-(((i/49-.5)*4)**2))}`).join(' ');
  return svg(text(18,22,'合成样本/外观示意 · 非实测统计')+Array.from({length:bins},(_,i)=>{const h=100*Math.exp(-(((i/bins-.5)*4)**2));return `<rect x="${45+i*width}" y="${180-h}" width="${width-1}" height="${h}" fill="${rgb}"/>`;}).join('')+`<polyline points="${curve}" fill="none" stroke="#905338" stroke-width="${stroke}"/>`+(markers?`<circle cx="215" cy="80" r="${markers}" fill="#a14f69"/>`:'')+text(35,207,`当前值：${show(d.value).slice(0,44)}`,`font-size="${font}"`),'统计分箱或绘图样式示意');
 }
 if(f==='material'){
  if(k==='apdl.poisson_ratio')return svg(text(18,22,'泊松比定义 · 形变夸张示意，不作定量应变')+`<rect x="175" y="60" width="90" height="110" fill="none" stroke="#aabbaa" stroke-dasharray="5 4"/><rect x="${175+clamp(v,-1,.5)*25}" y="45" width="${90-clamp(v,-1,.5)*50}" height="140" fill="#dce8dc" stroke="#276e50"/>`+text(18,215,`ν=${fmt(v)}；ν=−ε横向/ε轴向`),'泊松比与横向收缩的定义');
  const curve=Array.isArray(d.value)&&d.value.length>1&&d.value.every(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite))?d.value:null;
  let pts;
  if(curve)pts=curve.map(p=>`${45+(p[0]-curve[0][0])/(curve.at(-1)[0]-curve[0][0]||1)*345},${185-(p[1]-Math.min(...curve.map(z=>z[1])))/(Math.max(...curve.map(z=>z[1]))-Math.min(...curve.map(z=>z[1]))||1)*130}`).join(' ');
  else{const E=Number(values['apdl.E_MPa']??210000),yieldStress=Number(values['apdl.yield_MPa']??345),Et=Number(values['apdl.tangent_MPa']??1000);if(!(E>0&&yieldStress>0&&Et>=0&&Et<E))throw new Error('材料示意要求E>0、屈服应力>0、0≤Et<E');const elastic=values['apdl.material_model']==='elastic',limit=Math.max(2*yieldStress/E,.01),stress=e=>elastic?E*e:e<=yieldStress/E?E*e:yieldStress+Et*(e-yieldStress/E),max=stress(limit);pts=Array.from({length:61},(_,i)=>`${45+i*345/60},${185-stress(i*limit/60)/max*130}`).join(' ');}
  return svg(text(18,22,curve?'当前输入的材料曲线 · 非求解响应':'材料曲线关系示意 · 非本次有限元结果')+line(45,185,400,185)+line(45,185,45,45)+`<polyline points="${pts}" fill="none" stroke="#276e50" stroke-width="2"/>`+text(18,214,curve?`${curve.length}个输入点；请核对塑性应变与应力单位`:`当前${d.label}：${show(d.value).slice(0,35)}`),'材料本构与当前设置');
 }
 if(f==='validation'){
  const folds=clamp(Math.round(Number(k.includes('folds')?v:values[k.split('.')[0]+'.folds']??values['fit.folds']??5)),2,10);
  return svg(text(18,22,'验证划分示意 · 不代表当前样本数量')+Array.from({length:folds},(_,i)=>Array.from({length:folds},(_,j)=>`<rect x="${50+j*340/folds}" y="${50+i*120/folds}" width="${335/folds}" height="${110/folds}" fill="${i===j?'#b97459':'#b9d9c5'}"/>`).join('')).join('')+text(18,213,`示意${folds}折：棕色验证、绿色训练；分组/时间需另行约束`),'训练验证划分示意');
 }
 if(f==='load')return svg(text(18,22,'载荷与约束示意 · 不进行求解')+`<rect x="70" y="85" width="285" height="60" fill="#dce8dc" stroke="#276e50"/>`+Array.from({length:8},(_,i)=>line(55,65+i*12,70,75+i*12,'#6b8274')).join('')+line(355,115,405,115,'#ba624b','stroke-width="3"')+`<path d="M395 108 L405 115 L395 122" fill="none" stroke="#ba624b"/>`+text(18,210,`当前${d.label}：${show(d.value).slice(0,40)}`),'边界与加载设置示意');
 const stages=f==='ga'?['参数/种群','CA演化','适应度→选择']:f==='compute'?['任务输入','进程/设备','评价与保存']:f==='seed'?['随机种子','随机序列','当前流程']:f==='fit'?['选择数据','函数/条件','拟合/验证']:['当前输入','预检/显示','新任务或成果'];
 return svg(text(18,22,'作用链示意 · 不运行科学计算')+stages.map((s,i)=>`<rect x="${15+i*145}" y="75" width="120" height="65" rx="6" fill="${i===1?'#d6e7dc':'#e5eee1'}" stroke="#9eb6a4"/>`+text(75+i*145,112,s,'text-anchor="middle"')+(i<2?text(144+i*145,112,'→'):'')).join('')+text(18,185,`当前值：${show(d.value).slice(0,55)}`)+text(18,214,'实际输出以显式预检与运行结果为准'),'当前参数进入流程的位置');
}

export function explainParameter(d,values={},common=null){
 const f=family(d),specific=pointcloudNotes[d.key]||moduleNotes[d.key]||moduleNotes[d.key.replace(/^mv\./,'fit.')]||additionalNotes(d),notes=specific||familyNotes[f];
 let meaning=notes[0],effect=notes[1],analysis=null,error='',facts=[];
 if(d.help&&d.help!==d.label&&d.help!==d.key)meaning=specific?meaning:d.help;
 if(d.key.startsWith('figure.')&&!pointcloudNotes[d.key]){meaning=`${d.label}控制对应MATLAB诊断图的呈现。`;effect='只影响对应图的显示或导出，不改变数值矩阵；并非所有外观项都被每一张图使用。';}
 if(d.scope?.includes('本任务未使用')||d.scope?.includes('本模拟不使用'))effect=`当前CA/GA计算链不读取此项。${d.scope}；可保存给对应独立分析使用。`;
 if(f==='reference'){
  if(common){try{analysis=referenceAnalysis(common,{columns:values.columns??200,ratio:values.ratio??.2,corrosionColumns:values.corrosionColumns??168});facts=[`候选 H_flat=${analysis.height.toFixed(8)} mm；ΔH=${fmt(analysis.delta)} mm`,`已验证20%面=${common.reference_height_mm.toFixed(8)} mm（保留）`,`固定局部形貌按候选面平移后的经验深度均值=${fmt(analysis.localMeanDepth)} mm`,`原流程中央第${analysis.centralColumns.join('～')}列：H_max−H_flat=${fmt(analysis.uniformComponent)} mm`];}catch(e){error=e.message;}}
  else facts=['当前没有对应试件的共同坐标矩阵；先查看公式示意。','载入共同坐标预览后，自动更新实测区域和候选数值。'];
  effect+=' 调整r不改变表面起伏的形状，也不改变原始厚度；候选值不是已验证的新基准。';
 }
 let image='';try{image=diagram(d,f,values,common,analysis);}catch(e){error=e.message;image=svg(text(18,80,'当前输入无法生成对应图示')+text(18,110,error.slice(0,48)),'输入校核提示');}
 return {family:f,meaning,effect,facts,error,diagram:image,
  boundary:f==='reference'?'这里的即时数值是对保存矩阵的候选参考关系核算；不覆盖20%缓存，不提交新处理任务。已验证指数值链一致；参考区有轻微腐蚀，未知损失未补偿，不代表真实零腐蚀面。':f==='crop'&&common?'裁剪图按已有坐标节点核算；说明面板的修改沿用原入口的确认失效规则。':'图中注明示意的部分不是真实重算结果。参数生效范围沿用原入口，打开说明不会启动任务。'};
}

const aliases={'sim-mode':'mode','sim-seed':'GA_CONFIG.seed','targets':'ACTIVE_STAGE_TARGET_DATA'};
export function controlKey(el){
 if(el.dataset.param)return el.dataset.param;
 if(aliases[el.id])return aliases[el.id];
 if(el.dataset.draft)return 'preview.'+el.dataset.draft;
 if(el.dataset.option)return 'apdl.'+el.dataset.option;
 for(const key of ['fit','surface','origin','material','baseline','morphology','multi'])if(el.dataset[key])return key+'.'+el.dataset[key];
 const attribute=Array.from(el.attributes).find(a=>a.name.startsWith('data-')&&!['data-type','data-kind','data-baseline'].includes(a.name));
 return attribute?attribute.name.slice(5)+(attribute.value?'.'+attribute.value:''):el.id||el.type;
}
function read(el){if(el.type==='checkbox'||el.type==='radio')return el.checked;if(el.type==='number'||el.type==='range')return el.value===''?null:Number(el.value);try{if(/^(\[|\{|true$|false$)/.test(el.value))return JSON.parse(el.value);}catch{}return el.value;}

export function mountParameterHelp(root,{catalog=()=>[]}={}){
 const drawer=document.createElement('aside');drawer.className='parameter-help';drawer.hidden=true;drawer.setAttribute('aria-label','参数图文说明');
 drawer.innerHTML='<header><div><small>参数图文说明 · 实时联动</small><h3 data-help-title></h3></div><button type="button" class="button secondary" data-help-close aria-label="关闭参数说明">关闭</button></header><div class="parameter-help-body"><p data-help-module></p><label>当前值（与原参数同步）<span data-help-editor></span></label><p data-help-status class="help-line" role="status"></p><div data-help-graphic></div><h4>这个参数表示什么</h4><p data-help-meaning></p><h4>会影响什么</h4><p data-help-effect></p><div data-help-facts class="parameter-help-facts" role="status"></div><p data-help-boundary class="notice"></p><button type="button" class="button secondary" data-help-common hidden>载入当前试件共同坐标预览</button><details><summary>字段与定义来源</summary><code data-help-key></code><p data-help-source></p></details></div>';
 document.body.append(drawer);const q=s=>drawer.querySelector(s);let source=null,editor=null,common=null,commonJob='',pending=false,suppressFocus=false,pointerDown=false;
 const eligible=el=>el?.matches?.('input:not([type="hidden"]):not([type="search"]):not([type="submit"]):not([type="button"]),select,textarea')&&!el.closest('.parameter-help')&&!el.id?.includes('search')&&!!el.closest('.panel');
 function descriptor(el){const key=controlKey(el),kind=el.dataset.kind||'',item=catalog(kind).find(i=>i.path===key),panel=el.closest('.panel');
  const ownLabel=el.closest('label')||el.closest('.field')?.querySelector('label')||el.labels?.[0],labelCopy=ownLabel?.cloneNode(true);labelCopy?.querySelectorAll('input,select,textarea,small').forEach(e=>e.remove());
  const label=item?.label||el.getAttribute('aria-label')||labelCopy?.textContent.trim().replace(/\s+/g,' ').slice(0,100)||el.getAttribute('placeholder')||key;
  const box=el.closest('.field,.parameter,.fitting-model,.check-field')||ownLabel?.parentElement;
  const helper=el.getAttribute('aria-describedby')?.split(/\s+/).map(id=>document.getElementById(id)?.textContent||'').join(' ')||box?.querySelector('small,.help-line')?.textContent||'';
  return {key,label,value:read(el),type:el.type,help:item?.help||helper,scope:String(item?.scope||''),module:panel?.getAttribute('aria-label')||panel?.querySelector('h2,h3')?.textContent||panel?.id||'工作站',kind};
 }
 function valuesFor(d){const values={};for(const el of source.closest('.panel').querySelectorAll('input,select,textarea'))values[controlKey(el)]=read(el);
  const local=source.closest('#fitting-content,#multivariate-panel,[data-face]');if(local)for(const el of local.querySelectorAll('input,select,textarea'))values[controlKey(el)]=read(el);values[d.key]=read(source);
  const isPreview=d.key.startsWith('preview.'),columnsKey=isPreview?'preview.columns':'reference.flat_column_count',ratioKey=isPreview?'preview.ratio':'reference.flat_height_ratio';values.columns=Object.hasOwn(values,columnsKey)?values[columnsKey]:200;values.ratio=Object.hasOwn(values,ratioKey)?values[ratioKey]:.2;values.corrosionColumns=Object.hasOwn(values,'reference.corrosion_column_count')?values['reference.corrosion_column_count']:168;
  values.crop=d.key.startsWith('measured-region')?{length:values['measured-region-length'],width:values['measured-region-width'],centerX:source.closest('.panel').querySelector('#measured-region-center-x')?.value??'',centerY:source.closest('.panel').querySelector('#measured-region-center-y')?.value??''}:{length:values['preview.length']??50,width:values['preview.width']??18,centerX:source.closest('.panel').querySelector('[data-draft="centerX"]')?.value??'',centerY:source.closest('.panel').querySelector('[data-draft="centerY"]')?.value??''};return values;}
 function refresh(){if(!source)return;if(!source.isConnected){close(false);source=null;return;}
  if(!source.closest('.panel')?.classList.contains('active')||source.closest('[hidden]')){close(false);return;}
  const d=descriptor(source),values=valuesFor(d),sameCropSource=!d.key.startsWith('measured-region')||document.querySelector('#measured-region-source')?.value===commonJob+'|common_reference';
  const real=sameCropSource&&(d.key.startsWith('reference.')||d.key.startsWith('preview.')||d.key.startsWith('measured-region'))?common:null,r=explainParameter(d,values,real);
  q('[data-help-title]').textContent=d.label;q('[data-help-module]').textContent=d.module+' · '+(source.disabled?'当前参数停用或只读':'修改只作用于当前界面草稿')+(real?' · 保存矩阵来源 '+commonJob:'');
  q('[data-help-key]').textContent=d.key;q('[data-help-source]').textContent=(d.kind?'来自当前计算参数目录和已核对的流程定义。':'来自当前模块的控件标签、已有说明与流程定义。')+(d.scope?' 使用范围：'+d.scope:'');
  if(editor&&source.type==='file')editor.value=source.files?.[0]?.name||'尚未选择文件';
  if(editor&&document.activeElement!==editor&&source.type!=='file'){editor.value=source.value;editor.checked=source.checked;}if(editor)editor.disabled=source.disabled||source.type==='file'||source.readOnly;
  const invalid=source.validity&&!source.validity.valid||source.closest('.parameter')?.dataset.invalid==='true';
  q('[data-help-status]').textContent=invalid?'当前值不满足原控件约束，请修正后再预检。':r.error||'随当前值更新图文；没有提交计算。';q('[data-help-status]').classList.toggle('error-hint',!!r.error||invalid);
  q('[data-help-graphic]').innerHTML=r.diagram;q('[data-help-meaning]').textContent=r.meaning;q('[data-help-effect]').textContent=r.effect;q('[data-help-boundary]').textContent=r.boundary;
  q('[data-help-facts]').replaceChildren(...r.facts.map(s=>{const p=document.createElement('p');p.textContent=s;return p;}));
  q('[data-help-common]').hidden=!!common||!['reference','crop'].includes(r.family)||!document.querySelector('#pointcloud-3d-panel [data-kind]');
 }
 function schedule(){if(pending||drawer.hidden)return;pending=true;requestAnimationFrame(()=>{pending=false;refresh();});}
 function open(el){if(!eligible(el))return;if(source===el&&!drawer.hidden){schedule();return;}source=el;drawer.hidden=false;
  editor=el.type==='file'?document.createElement('input'):el.cloneNode(true);for(const a of Array.from(editor.attributes))if(a.name==='id'||a.name==='name'||a.name==='aria-describedby'||a.name.startsWith('data-'))editor.removeAttribute(a.name);
  editor.setAttribute('aria-label','说明面板当前值');editor.value=el.type==='file'?(el.files?.[0]?.name||'尚未选择文件'):el.value;editor.checked=el.checked;editor.disabled=el.disabled||el.type==='file'||el.readOnly;
  q('[data-help-editor]').replaceChildren(editor);
  const origin=el,mirror=editor;for(const name of ['input','change'])mirror.addEventListener(name,()=>{if(source!==origin||!origin.isConnected)return;if(origin.type==='checkbox'||origin.type==='radio')origin.checked=mirror.checked;else origin.value=mirror.value;origin.dispatchEvent(new Event(name,{bubbles:true}));schedule();});
  refresh();q('.parameter-help-body').scrollTop=0;
 }
 function close(restore=true){drawer.hidden=true;if(restore&&source?.isConnected&&!source.disabled){suppressFocus=true;source.focus();suppressFocus=false;}}
 const onFocus=event=>{if(!suppressFocus&&!pointerDown&&eligible(event.target))open(event.target);};
 const onClick=event=>{pointerDown=false;const el=eligible(event.target)?event.target:event.target.closest?.('label')?.control;if(eligible(el))open(el);else schedule();};
 // Let the original pointer click finish before a drawer can cover its target.
 root.addEventListener('pointerdown',()=>{pointerDown=true;},true);
 document.addEventListener('pointerup',()=>queueMicrotask(()=>{pointerDown=false;}),true);
 document.addEventListener('pointercancel',()=>{pointerDown=false;},true);
 root.addEventListener('keydown',()=>{pointerDown=false;},true);
 root.addEventListener('focusin',onFocus,true);document.addEventListener('click',onClick,true);root.addEventListener('input',schedule,true);root.addEventListener('change',schedule,true);
 root.addEventListener('pointcloud-preview-loading',()=>{common=null;commonJob='';schedule();});
 root.addEventListener('pointcloud-preview-ready',event=>{common=event.detail.common_reference?.numerical_chain_verified===true?event.detail.common_reference:null;commonJob=event.detail.source_job_id||'';schedule();});
 q('[data-help-close]').addEventListener('click',()=>close());document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!drawer.hidden)close();});
 q('[data-help-common]').addEventListener('click',()=>{const select=document.querySelector('#pointcloud-3d-panel [data-kind]');select.value='common_reference';select.dispatchEvent(new Event('change',{bubbles:true}));q('[data-help-status]').textContent='正在读取当前来源已有的共同坐标缓存…';});
 const toggle=document.createElement('button');toggle.type='button';toggle.className='button secondary';toggle.textContent='参数图文说明';toggle.id='parameter-help-toggle';document.querySelector('.top-actions')?.prepend(toggle);
 toggle.addEventListener('click',()=>{if(!drawer.hidden){close();return;}const el=source?.isConnected&&source.closest('.panel')?.classList.contains('active')?source:Array.from(root.querySelectorAll('.panel.active input,.panel.active select,.panel.active textarea')).find(e=>eligible(e)&&!e.disabled);if(el)open(el);});
 return {close,refresh};
}
