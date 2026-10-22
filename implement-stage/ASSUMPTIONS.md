# Assumption Ledger — independent surface generation
<!-- ASK mode: never -->

| ID | Under-determined by the request | Chosen | Class | Source |
|----|--------------------------------|--------|-------|--------|
| A-001 | 默认尺寸处理 | 保留原网格；裁剪到目标区域内的完整间隔，实际跨度单独报告；50 mm 可从长表面裁剪 | semantic | user |
| A-002 | 不足目标长度 | 严格拒绝，不缩放、不平铺；完整尺寸选项可保留名义190文件的实际189.3 mm | semantic | user |
| A-003 | 精确尺寸模式 | 双线性插值，端点精确、间隔均匀且不超过请求间距；记录实际间距和重采样 | semantic | default |
| A-004 | 双面关系 | 各面独立裁剪导出，无自动配准或拼接 | semantic | user |
| A-005 | MAT 数值含义 | 保留所选高程/深度含义；单位统一mm，显式符号与方向设置，NPZ沿用现有首金属层深度规则 | semantic | default |
| A-006 | XYZ重复XY和缺失格 | 相同XY的Z取均值并报告；线性插值，默认遇未覆盖格拒绝；用户显式允许后最近邻填充并报告数量 | semantic | default |
| A-007 | 来源接口 | 每面选择上传MAT/NPZ/XYZ或已完成模拟；已完成模拟使用冻结物理间距，外部文件要求确认单位与间距 | interface | default |
| A-008 | 输出契约 | front/Z_filled、back/F_filled；每MAT只含二维double变量，元数据放旁文件；矩阵行Y列X | interface | user |
| A-009 | 裁剪定位 | 默认居中；可输入距来源最小X/Y的偏移；保留网格时向区域内取整 | semantic | default |
| A-010 | 初始尺寸 | 默认完整来源；预设190/60/50必须由用户选择，宽度留空沿用完整宽度 | interface | default |
| A-011 | NPZ轴和网格 | NPZ的[X,Y,Z]状态先提取深度再转为行Y列X；不得用尺寸字段拉伸模拟，来源几何优先 | semantic | default |
| A-012 | 原始XYZ定义域 | XYZ坐标按输入单位统一mm，网格从最小XY向内生成，跨度不足一个间隔拒绝；非矩形扫描默认拒绝缺失格，显式最近邻填充可补边缘 | semantic | default |
