"""Pinned original GitHub APDL settings; presets never imply solver validation."""
import copy

ORIGINAL_CURVE = [[0,332.87],[0.00017,350.3],[0.000313,366.19],[0.000508,379.66],[0.000746,390.83],[0.001043,400.05],[0.001403,407.29],[0.001815,410.74],[0.002406,409.89],[0.002991,407.96],[0.003519,409.16],[0.004071,410.17],[0.004664,411.13],[0.005253,411.17],[0.005856,412.37],[0.006419,414.25],[0.00695,416.31],[0.007453,418.03],[0.007939,419.85],[0.008407,422.07],[0.012502,437.92],[0.016974,453.65],[0.020958,466.57],[0.025291,479.23],[0.029206,489.7],[0.033588,500.36],[0.037514,509.03],[0.041951,517.94],[0.045928,525.45],[0.050386,533.2],[0.054466,539.57],[0.058981,546.38],[0.063111,552.24],[0.067743,558.3],[0.071951,563.35],[0.076622,568.95],[0.080853,573.45],[0.085624,578.5],[0.089967,582.78],[0.094773,587.41],[0.099175,591.55],[0.104109,595.73],[0.108575,599.4],[0.113586,603.65],[0.118122,606.99],[0.123237,610.89],[0.127868,614.16],[0.133057,617.66],[0.137798,621.16]]
ORIGINAL_PATH = '段师兄腐蚀工作/05基于腐蚀扫面以及对应元胞生成面的APDL网格生成_包括双面装配组合生成腐蚀数据_能够生成apdl腐蚀试件计算所需点云数据/APDL_推荐（双面）运行包/03_APDL建模求解/model3_recommended.inp'

def get_presets():
    return copy.deepcopy([
        dict(id='elastic_flat',name='无腐蚀弹性板 · 基础验证',
             options=dict(corrosion_mode='flat',material_model='elastic',E_MPa=206000,
                          poisson_ratio=.3,length_mm=100,width_mm=20,thickness_mm=6,
                          nx=11,ny=5,layers=3,target_displacement_mm=.1,large_deflection=False,
                          boundary_mode='poisson_free',substeps=10,min_substeps=1,max_substeps=450),
             notes=['EA/L解析参考仅用于小变形弹性自由泊松伸缩工况。']),
        dict(id='github_original_double',name='GitHub原双面脚本 · 49点MISO',
             options=dict(corrosion_mode='double_independent',thickness_mm=6,dx_mm=.3,dy_mm=.3,
                          nx=193,ny=60,layers=8,E_MPa=185226,poisson_ratio=.3,
                          material_model='multilinear_iso',plastic_curve=ORIGINAL_CURVE,
                          allow_negative_slope=True,target_displacement_mm=11,
                          large_deflection=True,boundary_mode='legacy_recommended',
                          substeps=100,max_substeps=450,min_substeps=50),
             top_mapping=dict(variable='Z_filled',unit='mm',value_mode='height',reference_mode='maximum',
                              layout='yx',dx_mm=.3,dy_mm=.3,center_crop_columns=193),
             bottom_mapping=dict(variable='F_filled',unit='mm',value_mode='height',reference_mode='maximum',
                                 layout='yx',dx_mm=.3,dy_mm=.3,center_crop_columns=193),
             provenance=dict(repository='NatureG-creator/-',ref='76b2aa206fc3b677766908c4a821297303644779',
                             apdl_blob='eb0457cfde976f2bae16b255ebbf0bae78486dd4',
                             preprocess_blob='97965bfaa3db04633d2d57a1a5c6a67b8588e3dc',
                             path=ORIGINAL_PATH),
             notes=['原始多线性曲线含下降段，明确保留负斜率，未平滑。',
                    '原预处理对每面中心裁剪193列后取max(height)-height，不做空间翻面；新Z坐标与原宏仅差整体平移。',
                    '原始60行、193列对应57.6×17.7mm；网页按实际行列计算尺寸，不限制60行。',
                    '原宏声明Area=120但未用于其力位移输出。网页名义应力按实际width×thickness计算。',
                    '原单面包无独立求解宏；单面由同一实体生成器将另一面设为平面。',
                    '这是原始参数预设，尚未通过本机MAPDL实际求解验证。'])
    ])
