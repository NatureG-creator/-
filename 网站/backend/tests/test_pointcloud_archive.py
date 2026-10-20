import json
import shutil
import unittest
from pathlib import Path

from backend.pointcloud_archive import archive_pointcloud_job


class PointCloudArchiveTests(unittest.TestCase):
    def test_archives_inputs_and_outputs_by_category(self):
        root = Path(r"D:\CODEX文件\python腐蚀代码\.archive-test-fixed")
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        try:
            job = root / "jobs" / "abc123"
            (job / "inputs").mkdir(parents=True)
            (job / "outputs" / "pointcloud").mkdir(parents=True)
            (job / "inputs" / "reference.xyz").write_text("0 0 0\n", encoding="utf-8")
            (job / "inputs" / "detail.xyz").write_text("0 0 1\n", encoding="utf-8")
            (job / "outputs" / "pointcloud" / "matlab_target.mat").write_bytes(b"mat")
            (job / "outputs" / "pointcloud" / "six_metrics.csv").write_text("mean\n1\n", encoding="utf-8")
            (job / "outputs" / "过程图.png").write_bytes(b"png")
            (job / "outputs" / "summary.json").write_text("{}", encoding="utf-8")
            archive = archive_pointcloud_job(job, root / "archive", job_id="abc123")
            self.assertEqual(archive["state"], "completed")
            archive_dir = Path(archive["archive_root"])
            self.assertTrue((archive_dir / "01_参考点云" / "reference.xyz").is_file())
            self.assertTrue((archive_dir / "02_腐蚀细节点云" / "detail.xyz").is_file())
            self.assertTrue((archive_dir / "03_MATLAB六指标" / "pointcloud" / "matlab_target.mat").is_file())
            self.assertTrue((archive_dir / "03_MATLAB六指标" / "pointcloud" / "six_metrics.csv").is_file())
            self.assertTrue((archive_dir / "04_过程图" / "过程图.png").is_file())
            self.assertTrue((archive_dir / "05_诊断报告" / "summary.json").is_file())
            manifest = json.loads((archive_dir / "归档清单.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["job_id"], "abc123")
            self.assertGreaterEqual(manifest["file_count"], 5)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
