"""Security and mutation regressions; external commands are always faked."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import FakeRunner, make_config

from zjm_rag import ZjmError, files, locker_create
from zjm_rag.cli import main


class RegressionTest(unittest.TestCase):
    def test_excluded_source_roots_and_ancestors(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'
            secret = source / '.ssh'
            secret.mkdir(parents=True)
            (secret / 'config').write_text('private')
            cfg = make_config(self, allow=[str(source)])
            runner = FakeRunner()
            locker_create('lib', plain=True, config=cfg)
            alias = source / 'alias'
            alias.symlink_to(secret, target_is_directory=True)
            for path in (secret, secret / 'config', alias, alias / 'config'):
                with self.subTest(path=path), self.assertRaisesRegex(ZjmError, 'excluded'):
                    files.file_add('lib', [str(path)], config=cfg, runner=runner)
            self.assertEqual(runner.calls, [])
            self.assertEqual(files.file_list('lib', config=cfg)['files'], [])

    def test_overlapping_removals(self):
        cfg = make_config(self)
        runner = FakeRunner()
        locker_create('lib', plain=True, config=cfg)
        for name in ('docs/a.txt', 'docs/b.txt', 'keep.txt'):
            files.file_put('lib', name, 'text', config=cfg, runner=runner)
        result = files.file_remove('lib', ['docs', 'docs/a.txt', 'docs'], config=cfg, runner=runner)
        self.assertEqual(result['removed'], ['docs', 'docs/a.txt'])
        self.assertEqual([f['name'] for f in files.file_list('lib', config=cfg)['files']], ['keep.txt'])
        corpus = Path(cfg['home']) / 'lockers/lib/corpus'
        self.assertFalse((corpus / 'docs/a.txt').exists())
        self.assertFalse((corpus / 'docs/b.txt').exists())
        self.assertTrue((corpus / 'keep.txt').exists())

    def test_cli_preparation_errors_are_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / 'invalid.json'
            invalid.write_text('{broken')
            cases = [
                ['doctor', '--config', str(invalid)],
                ['doctor', '--config', str(Path(tmp) / 'missing')],
                ['find', 'q', '-l', 'lib', '--key-file', str(invalid)],
                ['file-list', 'lib', '--key-file', str(Path(tmp) / 'missing')],
            ]
            for args in cases:
                out, err = io.StringIO(), io.StringIO()
                with self.subTest(args=args), mock.patch.dict(os.environ, {'ZJM_IN_CONTAINER': '1'}), \
                        contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = main(args + ['--json'])
                self.assertEqual(code, 1)
                self.assertEqual(set(json.loads(out.getvalue())), {'error'})
                self.assertEqual(err.getvalue(), '')
