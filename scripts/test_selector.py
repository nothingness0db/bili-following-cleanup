"""Regression: a missing review is not a 'keep' rating, even in partial builds."""
import contextlib
import io
import json
import runpy
import shutil
import tempfile
import unittest
from pathlib import Path


class SelectorClassificationTest(unittest.TestCase):
    def test_partial_reviews_do_not_inflate_type_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            stage = Path(folder)
            shutil.copy2(Path(__file__).with_name('build_selector.py'), stage / 'build_selector.py')
            rows = [{'mid': '1', 'uname': '已审核'}, {'mid': '2', 'uname': '尚未审核'}]
            (stage / 'combined.json').write_text(json.dumps(rows), encoding='utf-8')
            (stage / 'analyze_out_01.json').write_text(json.dumps([
                {'mid': '1', 'type': 0, 'type_name': '保留/无问题', 'priority': '低', 'unfollow': False}
            ]), encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                runpy.run_path(str(stage / 'build_selector.py'))
            result = json.loads((stage / 'combined.json').read_text(encoding='utf-8'))
            self.assertEqual([(r['type'], r['type_name']) for r in result], [(0, '保留'), (-1, '未分类')])
            self.assertFalse(result[1]['unfollow'])


if __name__ == '__main__':
    unittest.main()
