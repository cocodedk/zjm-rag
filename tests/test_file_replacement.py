"""Plain file-add preserves existing data when preparation or replacement fails."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fakes import FakeRunner, make_config

from zjm_rag import files, locker_create
from zjm_rag.lockers import locker_dir


class ReplacementTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.source = Path(tmp.name) / 'source'
        self.source.mkdir()
        self.cfg = make_config(self, allow=[str(self.source)])
        self.runner = FakeRunner(ignored=['unused'])
        locker_create('lib', plain=True, config=self.cfg)
        files.file_put('lib', 'docs/original.txt', 'original', config=self.cfg, runner=self.runner)
        self.ldir = locker_dir(self.cfg, 'lib')

    def test_copy_failure_preserves_entire_batch(self):
        before = (self.ldir / 'locker.json').read_bytes()
        first = self.source / 'first.txt'
        first.write_text('first')
        docs = self.source / 'docs'
        docs.mkdir()
        (docs / 'new.txt').write_text('new')
        with mock.patch.object(files, 'copy_tree', side_effect=OSError('copy failed')), self.assertRaises(OSError):
            files.file_add('lib', [str(first), str(docs)], config=self.cfg, runner=self.runner)
        self.assertEqual((self.ldir / 'locker.json').read_bytes(), before)
        self.assertEqual((self.ldir / 'corpus/docs/original.txt').read_text(), 'original')
        self.assertFalse((self.ldir / 'corpus/first.txt').exists())
        self.assertEqual(list(self.ldir.glob('.add-*')), [])

    def test_type_changes_and_ignored_replacement(self):
        source = self.source / 'docs'
        source.write_text('now a file')
        files.file_add('lib', [str(source)], config=self.cfg, runner=self.runner)
        self.assertEqual((self.ldir / 'corpus/docs').read_text(), 'now a file')
        result = files.file_add('lib', [str(source)], config=self.cfg, runner=FakeRunner(ignored=['docs']))
        self.assertEqual(result['replaced'], [])
        self.assertEqual([f['name'] for f in files.file_list('lib', config=self.cfg)['files']], ['docs'])
        source.unlink()
        source.mkdir()
        (source / 'new.txt').write_text('now a directory')
        files.file_add('lib', [str(source)], config=self.cfg, runner=self.runner)
        self.assertEqual([f['name'] for f in files.file_list('lib', config=self.cfg)['files']], ['docs/new.txt'])
        result = files.file_add('lib', [str(source)], config=self.cfg, runner=FakeRunner(ignored=['docs']))
        self.assertEqual(result['replaced'], [])
        self.assertEqual([f['name'] for f in files.file_list('lib', config=self.cfg)['files']], ['docs/new.txt'])
        self.assertEqual((self.ldir / 'corpus/docs/new.txt').read_text(), 'now a directory')

    def test_install_failure_restores_previous_paths(self):
        before = (self.ldir / 'locker.json').read_bytes()
        source = self.source / 'docs'
        source.write_text('replacement')
        real_replace = files.os.replace

        def replace(src, dst):
            if Path(src).name.startswith('new-'):
                raise OSError('rename failed')
            return real_replace(src, dst)

        with mock.patch.object(files.os, 'replace', side_effect=replace), self.assertRaises(OSError):
            files.file_add('lib', [str(source)], config=self.cfg, runner=self.runner)
        self.assertEqual((self.ldir / 'locker.json').read_bytes(), before)
        self.assertEqual((self.ldir / 'corpus/docs/original.txt').read_text(), 'original')
        self.assertEqual(list(self.ldir.glob('.add-*')), [])
