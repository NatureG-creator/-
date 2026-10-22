# Assumption Ledger — independent surface generation
<!-- ASK mode: never -->

| ID | Under-determined by the request | Chosen | Class | Source |
|----|--------------------------------|--------|-------|--------|
| A-001 | 默认尺寸处理 | 保留原网格；裁剪到目标区域内的完整间隔，实际跨度单独报告；50 mm 可从长表面裁剪 | semantic | user |
| A-002 | 不足目标长度 | 严格拒绝，不缩放、不平铺；完整尺寸选项可保留名义190文件的实际189.3 mm | semantic | user |
| A-003 | 精确尺寸模式 | 双线性插值，端点精确、间隔均匀且不超过请求间距；记录实际间距和重采样 | semantic | default |
| A-004 | 双面关系 | 各面独立裁剪导出，无自动配准或拼接；公共尺寸为默认值，每面可覆盖长度、宽度、方向与偏移；网格模式与目标间距共用 | semantic | user / sweep |
| A-005 | MAT 数值含义 | 保留所选高程/深度含义；单位统一mm，显式符号与方向设置，NPZ沿用现有首金属层深度规则 | semantic | default |
| A-006 | XYZ重复XY和缺失格 | 相同XY的Z取均值并报告；线性插值，默认遇未覆盖格拒绝；用户显式允许后最近邻填充并报告数量 | semantic | default |
| A-007 | 来源接口 | 每面选择上传MAT/NPZ/XYZ或已完成模拟（手动刷新任务列表，上传不依赖任务列表）；已完成模拟使用冻结物理间距；外部文件预填mm、0.3mm间距，可直接使用或编辑，预检报告实际几何 | interface | sweep |
| A-008 | 输出契约 | front/Z_filled、back/F_filled；每MAT只含二维double变量，元数据放旁文件；矩阵行Y列X | interface | user |
| A-009 | 裁剪定位 | 默认居中；可输入距来源最小X/Y的偏移；保留网格时向区域内取整 | semantic | default |
| A-010 | 初始尺寸 | 默认完整来源；预设190/60/50必须由用户选择，宽度留空沿用完整宽度 | interface | default |
| A-011 | NPZ轴和网格 | NPZ的[X,Y,Z]状态先提取深度再转为行Y列X；不得用尺寸字段拉伸模拟，来源几何优先 | semantic | default |
| A-012 | 原始XYZ定义域 | XYZ坐标按输入单位统一mm，网格从最小XY向内生成，跨度不足一个间隔拒绝；非矩形扫描默认拒绝缺失格，显式最近邻填充可补边缘 | semantic | default |
| A-013 | 已完成模拟的阶段 | 留空读取最终perfect_a快照；显式阶段读取a_sd历史数组，若无可读历史则拒绝；外部NPZ的阶段指所选变量内部存储顺序，perfect_a只有一个最终快照 | semantic | sweep |
| A-014 | 重采样标记 | XYZ线性网格化始终标记source_resampled和resampled；grid_mode只描述之后的裁剪是否再次插值，界面分别说明 | semantic | sweep |
| A-015 | 转置物理几何 | MAT、XYZ和NPZ转置均交换XY及间距，保留原物理尺度；输入间距指转置前的行列 | semantic | sweep |
| A-016 | MAT变量默认值 | 优先唯一Z_filled/F_filled，否则只有一个候选时自动选择；多候选需手选，UI与后端一致 | semantic | sweep |
| A-017 | MAT版本 | 本入口支持SciPy可读的传统MAT（v4/v5至v7.2），不支持v7.3/HDF5；上传识别即明确提示用MATLAB另存-v7 | interface | sweep |
