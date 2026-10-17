"""Isolated Taichi probe. Kernels live in a real source file for inspect support."""
import json
import sys
import traceback


def probe(name):
    try:
        from backend.native_runtime import load_configured_runtime
    except ModuleNotFoundError:
        from native_runtime import load_configured_runtime
    load_configured_runtime()
    import taichi as ti
    if name == 'import':
        return {'state': 'passed', 'message': 'Taichi Python 包和原生扩展导入成功。', 'version': '.'.join(map(str, ti.__version__))}
    ti.init(arch=ti.cpu if name == 'cpu' else ti.gpu, offline_cache=False)
    arch = str(ti.lang.impl.current_cfg().arch).split('.')[-1]
    if name == 'gpu' and arch.lower() in ('x64', 'arm64', 'cpu'):
        return {'state': 'unavailable', 'actual_arch': arch, 'message': 'GPU 初始化回退至 CPU，不能据此认定 GPU 可用。'}
    values = ti.field(dtype=ti.i32, shape=8)

    @ti.kernel
    def minimum_kernel():
        for i in range(8):
            values[i] = i * i + 1

    minimum_kernel()
    ti.sync()
    if values[7] != 50:
        raise RuntimeError('最小 kernel 结果不正确')
    return {'state': 'passed', 'actual_arch': arch, 'device': {'backend': arch, 'name': None, 'note': '设备型号如由驱动报告，见原始日志；不根据硬件清单推断实际计算设备。'}, 'message': '最小 kernel 计算正确（7×7+1=50）。'}


if __name__ == '__main__':
    try:
        result = probe(sys.argv[1])
    except BaseException as exc:
        traceback.print_exc()
        result = {'state': 'failed', 'message': f'{type(exc).__name__}: {exc}'}
    print('DIAGNOSTICS_RESULT=' + json.dumps(result, ensure_ascii=True), flush=True)
