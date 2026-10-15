import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

class NativeRuntimeTests(unittest.TestCase):
    def test_unconfigured_never_loads(self):
        from backend.native_runtime import load_configured_runtime
        with patch.dict(os.environ, {'CORROSION_NATIVE_DLL_DIR':''}), patch('backend.native_runtime.ctypes.WinDLL', create=True) as loader:
            self.assertEqual(load_configured_runtime()['state'], 'not_configured')
            loader.assert_not_called()

    def test_windows_explicit_existing_file_and_hash(self):
        from backend.native_runtime import load_configured_runtime
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'MSVCP140.dll').write_bytes(b'test runtime')
            with patch.dict(os.environ, {'CORROSION_NATIVE_DLL_DIR':directory}), patch('backend.native_runtime.platform.system', return_value='Windows'), patch('backend.native_runtime.os.add_dll_directory', create=True) as add, patch('backend.native_runtime.ctypes.WinDLL', create=True) as loader:
                result=load_configured_runtime()
            self.assertEqual(result['state'],'loaded')
            self.assertEqual(len(result['sha256']),64)
            loader.assert_called_once_with(str(Path(directory)/'MSVCP140.dll'))
            add.assert_called_once_with(str(Path(directory).resolve()))

    def test_relative_directory_is_reported_without_loading(self):
        from backend.native_runtime import load_configured_runtime
        with patch.dict(os.environ, {'CORROSION_NATIVE_DLL_DIR':'relative'}), patch('backend.native_runtime.platform.system', return_value='Windows'), patch('backend.native_runtime.ctypes.WinDLL', create=True) as loader:
            self.assertEqual(load_configured_runtime()['state'],'failed')
            loader.assert_not_called()

    def test_loader_failure_is_returned(self):
        from backend.native_runtime import load_configured_runtime
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'MSVCP140.dll').write_bytes(b'test runtime')
            with patch.dict(os.environ, {'CORROSION_NATIVE_DLL_DIR':directory}), patch('backend.native_runtime.platform.system', return_value='Windows'), patch('backend.native_runtime.os.add_dll_directory', create=True), patch('backend.native_runtime.ctypes.WinDLL', side_effect=OSError('bad DLL'), create=True):
                result=load_configured_runtime()
            self.assertEqual(result['state'],'failed')
            self.assertIn('bad DLL',result['error'])

    def test_missing_dll_is_reported_without_loader_or_directory_change(self):
        from backend.native_runtime import load_configured_runtime
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'CORROSION_NATIVE_DLL_DIR':directory}), patch('backend.native_runtime.platform.system', return_value='Windows'), patch('backend.native_runtime.os.add_dll_directory', create=True) as add, patch('backend.native_runtime.ctypes.WinDLL', create=True) as loader:
                result=load_configured_runtime()
            self.assertEqual(result['state'],'failed')
            self.assertIn('不存在 MSVCP140.dll', result['error'])
            loader.assert_not_called()
            add.assert_not_called()

    def test_non_windows_configuration_does_not_load(self):
        from backend.native_runtime import load_configured_runtime
        with patch.dict(os.environ, {'CORROSION_NATIVE_DLL_DIR':'/explicit'}), patch('backend.native_runtime.platform.system', return_value='Linux'), patch('backend.native_runtime.ctypes.WinDLL', create=True) as loader:
            self.assertEqual(load_configured_runtime()['state'],'unsupported')
            loader.assert_not_called()
