import json
from pathlib import Path
import tempfile
import unittest

from bulk_video.classifier import classify
from bulk_video.cli import previous_download, read_links, task_id


class CoreTests(unittest.TestCase):
    def test_week_boundaries(self):
        self.assertEqual(classify('Civil 3D Semana 10')['folder'], '10_Civil3D_Semana_10')
        self.assertEqual(classify('Sem_19')['folder'], '19_Civil3D_Semana_19')
        self.assertEqual(classify('Sem20')['folder'], '14_Otros')

    def test_topics_accents_and_transcript(self):
        self.assertEqual(classify('Sección_típica')['folder'], '07_Secciones_Tipicas')
        self.assertEqual(classify('Taller', transcript='curva vertical')['folder'], '12_Diseno_Vertical')
        self.assertEqual(classify('driveway')['folder'], '14_Otros')

    def test_supported_hosts_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / 'links.txt'
            file.write_text('# comment\nhttps://youtu.be/a\nhttps://youtu.be/a\nhttps://youtube.com.evil.test/a\nhttps://vimeo.com/1\n', encoding='utf-8')
            links, bad = read_links(file)
            self.assertEqual(links, ['https://youtu.be/a', 'https://vimeo.com/1'])
            self.assertEqual(bad, [4])

    def test_existing_download_requires_matching_url_and_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / '.state').mkdir()
            url = 'https://youtu.be/a'
            marker = output / '.state' / (task_id(url) + '.json')
            marker.write_text(json.dumps({'url':url,'file':'video.mp4'}))
            self.assertIsNone(previous_download(output, url))
            (output / 'video.mp4').write_bytes(b'video fixture')
            self.assertEqual(previous_download(output, url), output / 'video.mp4')
            marker.write_text(json.dumps({'url': 'https://youtu.be/b', 'file':'video.mp4'}))
            self.assertIsNone(previous_download(output, url))

    def test_escape_from_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'output'
            (output / '.state').mkdir(parents=True)
            (root / 'outside.mp4').write_bytes(b'fixture')
            url = 'https://youtu.be/a'
            (output / '.state' / (task_id(url) + '.json')).write_text(json.dumps({'url':url,'file':'../outside.mp4'}))
            self.assertIsNone(previous_download(output, url))


if __name__ == '__main__':
    unittest.main()
