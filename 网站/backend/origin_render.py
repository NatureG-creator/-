"""Runs in a dedicated Python process, owning a new Origin.Application instance."""
from pathlib import Path
import csv
import json
import math
import sys

from .origin_plotting import _read, load_origin_snapshot, normalise_origin_options
from .runner import _atomic_json


def _number(obj,prop,value,evidence):
    obj.set_float(prop,value)
    actual=obj.get_float(prop)
    if not math.isfinite(actual) or not math.isclose(actual,value,rel_tol=.001,abs_tol=.001):
        raise RuntimeError(f'Origin未接受设置{prop}: requested={value}, actual={actual}')
    evidence[prop]=actual


def _text(layer,name,text,size,font,evidence):
    label=layer.label(name)
    if label is None:
        layer.lt_exec(f'label -{name.lower()} Placeholder;' if name.lower() in {'xb','yl','zb'} else f'label -n {name} Placeholder;')
        label=layer.label(name)
    if label is None:raise RuntimeError(f'Origin无法创建文本对象{name}')
    label.text=text
    _number(label,'fsize',size,evidence)
    _number(label,'font',font,evidence)
    return label


def _csv(path,header,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(header);w.writerows(rows)


def _place(layer,label,xf,yf):
    coordinates=[]
    for axis,fraction in [('x',xf),('y',yf)]:
        lo,hi,_=layer.axis(axis).limits
        if layer.get_int(axis+'.reverse'):fraction=1-fraction
        value=10**(math.log10(lo)+fraction*(math.log10(hi)-math.log10(lo))) if layer.axis(axis).scale==2 else lo+fraction*(hi-lo)
        coordinates.append(value)
    label.set_int('attach',1)
    label.set_float('x',coordinates[0]);label.set_float('y',coordinates[1])


def _sheet(op,name,data,columns):
    sheet=op.new_sheet('w',lname=name)
    for i,key in enumerate(columns):sheet.from_list(i,data[key],key.upper())
    return sheet


def _plot_style(plot,options):
    plot.color=options['line_color']
    plot.transparency=100-options['opacity']
    plot.symbol_size=options['symbol_size']
    plot.symbol_kind={'circle':2,'square':1,'triangle':3,'none':0}[options['symbol']]
    plot.symbol_interior=1 if options['symbol']!='none' else 0


def _record_owner(op,job_dir):
    import psutil
    source=Path(__file__).with_name('origin_owner.c')
    op.lt_float(f'run.LoadOC("{source}",16)')
    value=op.lt_float('CorrosionOriginProcessID()')
    if not math.isfinite(value) or value<=0 or int(value)!=value:raise RuntimeError('Origin所属进程握手失败，未执行绘图')
    process=psutil.Process(int(value))
    if process.name().lower()!='origin64.exe':raise RuntimeError('Origin返回的进程身份无效')
    _atomic_json(Path(job_dir)/'origin_process.json',dict(pid=process.pid,create_time=process.create_time(),ownership='OriginC GetCurrentProcessId in dedicated COM instance'))
    _atomic_json(Path(job_dir)/'origin_launch.json',dict(state='identified'))


def _surface_titles(op,layer,out,o,font):
    import xml.etree.ElementTree as ET
    path=out/'origin_axis_theme.xml'
    if not op.lt_int(f'CorrosionOriginExportTheme("{path}")'):raise RuntimeError('Origin不能读取三维坐标轴主题')
    tree=ET.parse(path)
    for axis in ('x','y','z'):
        titles=tree.getroot().find(f'Root/Axes/{axis.upper()}/Titles')
        if titles is None:raise RuntimeError('Origin三维坐标轴标题主题不兼容')
        for title in titles:
            for key,value in [('Text',o[axis+'_label']+(f' ({o[axis+"_unit"]})' if o[axis+'_unit'] else '')),
                              ('Font/Size',o['font_size']),('Font/Face',int(font)),('LinkToVars',0)]:
                node=title.find(key)
                if node is None:raise RuntimeError(f'Origin三维标题缺少字段{key}')
                node.text=str(value)
            title.find('Text').text=r'\f:'+o['font_family']+'('+title.find('Text').text+')'
    for axis in tree.getroot().findall('Root/Spectrums/Spectrum1/DimAxes/DimAxis2/NewAxes/*'):
        for key,value in [('Title/Text',o['colorbar_title']),('Title/Font/Size',o['legend_size']),('Title/Font/Face',int(font)),('Title/LinkToVars',0),
                          ('Labels/MajorLabels/Font/Size',o['tick_size']),('Labels/MajorLabels/Font/Face',int(font))]:
            node=axis.find(key)
            if node is not None:node.text=str(value)
        title=axis.find('Title/Text')
        if title is not None:title.text=r'\f:'+o['font_family']+'('+o['colorbar_title']+')'
    root=tree.getroot().find('Root')
    # Apply only title branches. Full theme roundtrips would reset matrix color levels.
    for child in list(root):
        if child.tag not in {'Axes','Spectrums'}:root.remove(child)
    axes=root.find('Axes')
    for axis in list(axes):
        if axis.tag not in {'X','Y','Z'}:axes.remove(axis);continue
        for child in list(axis):
            if child.tag!='Titles':axis.remove(child)
    spectrum=root.find('Spectrums')
    if spectrum is not None:
        def keep_path(node,path):
            if not path:return
            for child in list(node):
                if child.tag==path[0] or path[0]=='*':keep_path(child,path[1:])
                else:node.remove(child)
        dimension=spectrum.find('Spectrum1/Dimension')
        if dimension is not None:
            # Move the native scale beyond the projected Z axis. Applying only
            # PosX preserves the template's scale height and color levels.
            dimension.find('PosX').text='120'
            for child in list(dimension):
                if child.tag!='PosX':dimension.remove(child)
        for child in list(spectrum.find('Spectrum1')):
            if child.tag not in {'Dimension','DimAxes'}:spectrum.find('Spectrum1').remove(child)
        dimaxes=spectrum.find('Spectrum1/DimAxes')
        keep_path(dimaxes,['DimAxis2','NewAxes','*'])
        for axis in spectrum.findall('Spectrum1/DimAxes/DimAxis2/NewAxes/*'):
            for child in list(axis):
                if child.tag not in {'Title','Labels'}:axis.remove(child)
    tree.write(path,encoding='utf-8',xml_declaration=True)
    if not op.lt_int(f'CorrosionOriginApplyTheme("{path}")'):raise RuntimeError('Origin不能应用三维坐标轴标题')
    applied=out/'origin_applied_theme.xml'
    if not op.lt_int(f'CorrosionOriginExportTheme("{applied}")'):raise RuntimeError('Origin不能核对应用后的三维主题')
    actual=ET.parse(applied).getroot()
    return dict(colorbar_reverse=actual.findtext('Root/Spectrums/Spectrum1/DimAxes/DimAxis2/Reverse'),
                axis_title_text={axis:actual.findtext(f'Root/Axes/{axis}/Titles/*/Text') for axis in ('X','Y','Z')},
                colorbar_title_text=actual.findtext('Root/Spectrums/Spectrum1/DimAxes/DimAxis2/NewAxes/NewAxis1/Title/Text'))


def render(job_dir):
    import numpy as np
    import originpro as op
    from PIL import Image
    job_dir=Path(job_dir);spec=_read(job_dir/'spec.json');o=normalise_origin_options(spec['options'])
    data=load_origin_snapshot(job_dir,spec);out=job_dir/'outputs';out.mkdir(exist_ok=True)
    evidence=dict(version=None,project_reopened=False,settings={},warnings=[])
    try:
        # originpro APP creates OriginExt.Application, not ApplicationSI/attach.
        op.set_show(False)
        _record_owner(op,job_dir)
        evidence['version']=op.lt_float('@V')
        print('Origin dedicated instance version',evidence['version'],flush=True)
        op.new()
        multi=spec['plot_type']=='surface'
        observed=data['observed'];columns=['x','y','z'] if multi else ['x','y']
        w=_sheet(op,'Frozen observations',observed,columns)
        _csv(out/'observed.csv',columns,zip(*(observed[k] for k in columns)))
        if multi:
            surf=data['surface'];matrix=op.new_sheet('m',lname='Frozen predicted response surface')
            matrix.from_np(np.array(surf['z'],dtype=float));matrix.xymap=(surf['x'][0],surf['x'][-1],surf['y'][0],surf['y'][-1])
            xx,yy=np.meshgrid(surf['x'],surf['y']);zz=np.array(surf['z'])
            _csv(out/'surface_grid.csv',['X1','X2','Fitted_Y'],zip(xx.ravel(),yy.ravel(),zz.ravel()))
            graph=op.new_graph(template='glCMAP');layer=graph[0]
            fitted=layer.add_mplot(matrix,0,type=103)
            # The template enables colormap fill; this controls its numeric levels.
            low=float(zz.min()) if o['color_min'] is None else o['color_min']
            high=float(zz.max()) if o['color_max'] is None else o['color_max']
            if low>=high:
                if o['color_min'] is not None or o['color_max'] is not None:raise ValueError('色标单侧范围与曲面范围冲突')
                low-=.5;high+=.5
            if o['show_observed'] and o['symbol']!='none':
                scatter=layer.add_plot(w,colx=0,coly=1,colz=2,type=240);_plot_style(scatter,o)
        else:
            curve=data['curve'];c=_sheet(op,'Frozen fitted curve',curve,['x','y'])
            _csv(out/'fitted_curve.csv',['X','Fitted_Y'],zip(curve['x'],curve['y']))
            graph=op.new_graph(template='scatter');layer=graph[0]
            if o['show_observed'] and o['symbol']!='none':
                scatter=layer.add_plot(w,colx=0,coly=1,type='s');_plot_style(scatter,o)
            fitted=layer.add_plot(c,colx=0,coly=1,type='l');fitted.color=o['line_color']
            fitted.set_cmd(f'-w {o["line_width"]*500}',f'-d { {"solid":0,"dash":1,"dot":2}[o["line_style"]] }')
            fitted.transparency=100-o['opacity']
        layer.rescale()
        if multi:
            # Rescaling initializes the native color range; freeze requested levels afterwards.
            fitted.zlevels=dict(levels=np.linspace(low,high,7).tolist(),minors=0)
            fitted.colormap={'viridis':'Viridis.PAL','rainbow':'Rainbow.PAL','grayscale':'GrayScale.PAL'}[o['colormap']]
        settings=evidence['settings']
        font=op.lt_float(f'font("{o["font_family"]}")')
        if not math.isfinite(font) or font<=0:raise ValueError('Origin不能识别所选字体')
        graph.set_int('unit',3)
        graph.set_int('kar',0)
        _number(graph,'width',o['width_mm']/25.4*graph.get_float('resx'),settings)
        _number(graph,'height',o['height_mm']/25.4*graph.get_float('resy'),settings)
        if multi:
            layer.set_float('width',55);layer.set_float('height',55)
            layer.set_float('left',15);layer.set_float('top',22)
        for axis,object_name in [('x','XB'),('y','YL')]+([('z','ZB')] if multi else []):
            label=o[axis+'_label']+(f' ({o[axis+"_unit"]})' if o[axis+'_unit'] else '')
            if not multi:_text(layer,object_name,label,o['font_size'],font,{})
            if axis in ('x','y'):
                layer.axis(axis).scale=2 if o[axis+'_scale']=='log' else 1
                _number(layer,axis+'.reverse',int(o[axis+'_reverse']),settings)
                _number(layer,axis+'.majorTicks',o[axis+'_major_ticks'],settings)
                _number(layer,axis+'.minorTicks',o[axis+'_minor_ticks'],settings)
                _number(layer,axis+'.showGrids',int(o['grid']),settings)
            _number(layer,axis+'.label.pt',o['tick_size'],settings)
            _number(layer,axis+'.label.font',font,settings)
            layer.axis(axis).set_limits(o[axis+'_min'],o[axis+'_max'])
            # Fixed ranges remain frozen after export or interactive reopening.
            layer.set_int(axis+'.rescale',0)
        if multi:
            settings['applied_native_theme']=_surface_titles(op,layer,out,o,font)
            if not np.array_equal(matrix.to_np2d(),zz):raise RuntimeError('Origin矩阵读回与冻结响应面不一致')
            settings['matrix_xy_map']=list(matrix.xymap)
            settings['matrix_corner_z']=[float(zz[0,0]),float(zz[0,-1]),float(zz[-1,0]),float(zz[-1,-1])]
            evidence['warnings'].append('三维色标刻度的字体仍采用Origin模板字体；轴标题和色标标题使用显式字体。')
        title_layer=layer
        if multi:
            # Native graph labels preserve the OpenGL surface underneath.
            layer.lt_exec('label -p (35) (-35) -n OriginTitle Placeholder;')
        title=_text(title_layer,'OriginTitle',o['title'],o['title_size'],font,{})
        if not multi:_place(title_layer,title,.5,1.12)
        legend=layer.label('Legend')
        if multi and legend:legend.remove();legend=None
        if o['legend']=='none':
            if legend:legend.remove()
        else:
            has_observed=o['show_observed'] and o['symbol']!='none'
            if multi:legend_text=r'\l(1) Fitted surface'+('\n'+r'\l(2) Observed' if has_observed else '')
            else:legend_text=(r'\l(1) Observed'+'\n'+r'\l(2) Fitted') if has_observed else r'\l(1) Fitted'
            if multi:
                lx=110 if o['legend'].endswith('right') else 0
                ly=-27 if o['legend'].startswith('top') else 100
                layer.lt_exec(f'label -p ({lx}) ({ly}) -n Legend Placeholder;')
            legend=_text(title_layer,'Legend',legend_text,o['legend_size'],font,{})
            legend.set_int('background',1 if o['legend_border'] else 0)
            if multi:
                legend.text='Fitted surface'+('\nObserved' if has_observed else '')
            else:_place(layer,legend,.80 if o['legend'].endswith('right') else .18,.9 if o['legend'].startswith('top') else .12)
        if multi:
            layer.activate()
            fitted.transparency=100-o['opacity']
            _number(layer,'camera.azimuth',o['azimuth'],settings)
            _number(layer,'camera.inclination',90-o['elevation'],settings)
            actual_levels=fitted.zlevels['levels']
            if not np.allclose([actual_levels[0],actual_levels[-1]],[low,high],rtol=1e-9,atol=1e-9):raise RuntimeError('Origin色标范围与指定范围不一致')
            evidence['settings'].update(colormap=fitted.colormap,color_levels=fitted.zlevels)
        op.lt_exec('doc -uw;')
        print('style applied',json.dumps(evidence,ensure_ascii=False),flush=True)
        formats=list(dict.fromkeys(['png']+o['formats']))
        for ext in formats:
            actual='tif' if ext=='tiff' else ext
            target=out/f'origin_plot.{actual}'
            # Explicit page margins prevent inherited GUI export themes from cropping dimensions.
            size=f'tr1.Unit:=2 tr1.Width:={round(o["width_mm"]/25.4*o["dpi"])}' if ext in {'png','tiff'} else ''
            op.set_lt_str('__LASTEXP','')
            graph.lt_exec(f'expgraph -sw type:={actual} filename:="origin_plot" path:="{out}" overwrite:=replace tr.Margin:=2 {size};')
            result=op.get_lt_str('__LASTEXP')
            if not result or not target.is_file() or target.stat().st_size<100:raise RuntimeError(f'Origin导出{ext}失败，已生成的其他文件保留')
            if ext in {'png','tiff'}:
                with Image.open(target) as im:
                    pixels=im.copy()
                pixels.save(target,dpi=(o['dpi'],o['dpi']))
                evidence['settings'][ext+'_size']=list(pixels.size)
            print('exported',target.name,flush=True)
        if not op.save(str(out/'origin_project.opju')):raise RuntimeError('Origin工程保存失败')
        evidence['project_reopened']=bool(op.open(str(out/'origin_project.opju')))
        if not evidence['project_reopened']:raise RuntimeError('Origin工程重开失败')
        reopened=op.find_graph()
        if reopened is None or len(reopened[0].plot_list())<1:raise RuntimeError('重开工程中缺少可编辑的数据图层')
        evidence['editable_plot_count']=len(reopened[0].plot_list())
        evidence['dedicated_instance']=True
        _atomic_json(out/'origin_runtime.json',evidence)
        print('project saved and reopened',flush=True)
    finally:
        try:op.exit()
        except Exception as exc:print('Origin exit:',repr(exc),flush=True)


def open_project(project,job_dir):
    import originpro as op
    op.set_show(True)
    _record_owner(op,job_dir)
    if not op.open(str(project)):raise RuntimeError('Origin不能打开编辑工程')
    op.set_show(True)
    op.detach()
    print('editable project opened',flush=True)


if __name__=='__main__':
    if sys.argv[1]=='render':render(Path(sys.argv[2]))
    elif sys.argv[1]=='open':open_project(Path(sys.argv[3]),Path(sys.argv[2]))
    else:raise ValueError('未知Origin运行模式')
