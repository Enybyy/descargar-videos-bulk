from argparse import Namespace
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from bulk_video.cli import process, previous_download


class DownloadTests(unittest.TestCase):
    def test_completed_file_is_reported_and_reordering_skips_it(self):
        class Downloader:
            calls = 0
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download=False):
                Downloader.calls += 1
                if not download:
                    return {'title':'Semana 10', 'description':''}
                file = Path(self.options['outtmpl'].replace('%(title).120B','Semana 10').replace('%(ext)s','mp4'))
                file.write_bytes(b'completed video fixture')
                return {'filepath':str(file)}
            def prepare_filename(self, info):
                return info['filepath']
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(output=Path(tmp), plan=False, subtitles=False, ffmpeg=None, node=None)
            url = 'https://youtu.be/sample'
            with patch.dict('sys.modules', {'yt_dlp':types.SimpleNamespace(YoutubeDL=Downloader)}):
                result = process(url, 1, args)
                self.assertEqual(result['status'],'downloaded')
                self.assertIsNotNone(previous_download(args.output, url))
                reordered = process(url, 9, args)
                self.assertEqual(reordered['status'],'existing')
                self.assertEqual(Downloader.calls, 2)
                self.assertEqual(reordered['index'], 9)

    def test_missing_final_file_does_not_mark_success(self):
        class Downloader:
            def __init__(self, options):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download=False):
                return {'title':'Unknown', 'filepath':'missing.mp4'}
            def prepare_filename(self, info):
                return info['filepath']
        with tempfile.TemporaryDirectory() as tmp:
            args = Namespace(output=Path(tmp),plan=False,subtitles=False,ffmpeg=None,node=None)
            with patch.dict('sys.modules', {'yt_dlp':types.SimpleNamespace(YoutubeDL=Downloader)}):
                result = process('https://youtu.be/sample',1,args)
                self.assertEqual(result['status'],'failed')
                self.assertFalse((Path(tmp)/'.state').exists())
