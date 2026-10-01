"""Local download runner. Download state is identified by URL, never list position."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlsplit

from .classifier import classify

HOSTS = {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be', 'vimeo.com', 'www.vimeo.com', 'player.vimeo.com'}


def read_links(file):
    links, rejected = [], []
    for number, line in enumerate(file.read_text(encoding='utf-8-sig').splitlines(), 1):
        value = line.strip()
        if not value or value.startswith('#'):
            continue
        try:
            parsed = urlsplit(value)
        except ValueError:
            rejected.append(number)
            continue
        if parsed.scheme not in {'http', 'https'} or parsed.hostname not in HOSTS or parsed.username or parsed.password or any(c.isspace() for c in value):
            rejected.append(number)
        elif value not in links:
            links.append(value)
    return links, rejected


def task_id(url):
    return hashlib.sha256(url.encode()).hexdigest()[:20]


def previous_download(output, url):
    marker = output / '.state' / (task_id(url) + '.json')
    try:
        state = json.loads(marker.read_text(encoding='utf-8'))
        file = (output / state['file']).resolve()
        if state['url'] == url and file.is_relative_to(output.resolve()) and file.is_file() and file.stat().st_size > 0:
            return file
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def options(args):
    value = {'noplaylist': True, 'quiet': True, 'socket_timeout': 30, 'retries': 3, 'windowsfilenames': True}
    if args.ffmpeg:
        value['ffmpeg_location'] = args.ffmpeg
    if args.node:
        value['js_runtimes'] = {'node': {'path': args.node}}
    return value


def fetch_transcript(url, args):
    import yt_dlp
    import re
    with tempfile.TemporaryDirectory(prefix='bulk-subtitles-') as directory:
        config = options(args) | {'skip_download': True, 'writesubtitles': True, 'writeautomaticsub': True, 'subtitleslangs': ['es'], 'subtitlesformat': 'vtt', 'outtmpl': str(Path(directory) / '%(id)s.%(ext)s')}
        try:
            with yt_dlp.YoutubeDL(config) as ydl:
                ydl.download([url])
            lines = []
            for file in Path(directory).glob('*.vtt'):
                for line in file.read_text(encoding='utf-8').splitlines():
                    if not line.strip() or '-->' in line or line.startswith(('WEBVTT', 'Kind:', 'Language:')) or line.isdigit():
                        continue
                    text = re.sub('<[^>]+>', '', line).strip()
                    if text and (not lines or lines[-1] != text):
                        lines.append(text)
            return ' '.join(lines)
        except yt_dlp.utils.DownloadError:
            return ''


def process(url, index, args):
    import yt_dlp
    existing = previous_download(args.output, url)
    if existing and not args.plan:
        return {'index': index, 'url': url, 'status': 'existing', 'file': str(existing.relative_to(args.output.resolve()))}
    try:
        with yt_dlp.YoutubeDL(options(args)) as ydl:
            info = ydl.extract_info(url, download=False)
        if not info or info.get('_type') in {'playlist', 'multi_video'}:
            raise ValueError('Provide a single video URL, not a playlist')
        title = info.get('title') or 'Untitled'
        transcript = fetch_transcript(url, args) if args.subtitles else ''
        result = classify(title, info.get('description') or '', transcript)
        folder = args.output / result['folder']
        record = {'index': index, 'url': url, 'title': title, **result, 'status': 'planned' if args.plan else 'downloaded'}
        if args.plan:
            return record
        folder.mkdir(parents=True, exist_ok=True)
        config = options(args) | {'format': 'bestvideo+bestaudio/best', 'merge_output_format': 'mp4', 'outtmpl': str(folder / (task_id(url) + '_%(title).120B.%(ext)s'))}
        completed = []
        def capture(event):
            if event.get('status') == 'finished' and event.get('info_dict', {}).get('filepath'):
                completed.append(Path(event['info_dict']['filepath']))
        config['postprocessor_hooks'] = [capture]
        with yt_dlp.YoutubeDL(config) as ydl:
            downloaded = ydl.extract_info(url, download=True)
            candidates = completed + [Path(downloaded.get('filepath') or ydl.prepare_filename(downloaded))]
        actual = next((p for p in reversed(candidates) if p.is_file() and p.stat().st_size and p.suffix not in {'.part', '.ytdl'}), None)
        if actual is None:
            raise ValueError('Downloader returned without a completed output file')
        record['file'] = str(actual.resolve().relative_to(args.output.resolve()))
        state = args.output / '.state'
        state.mkdir(exist_ok=True)
        marker = state / (task_id(url) + '.json')
        temporary = marker.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(marker)
        return record
    except Exception as error:
        return {'index': index, 'url': url, 'status': 'failed', 'error': str(error)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Download and organize a video list by Civil 3D topic.')
    parser.add_argument('--links', type=Path, default=Path('links.txt'))
    parser.add_argument('--output', type=Path, default=Path('downloads'))
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=3)
    parser.add_argument('--ffmpeg', help='FFmpeg binary or directory; otherwise use PATH')
    parser.add_argument('--node', help='Optional Node.js binary path for YouTube extraction')
    parser.add_argument('--subtitles', action='store_true', help='Use available Spanish subtitles for topic scoring')
    parser.add_argument('--plan', action='store_true', help='Fetch metadata and classify without downloading video')
    args = parser.parse_args(argv)
    if not args.links.is_file():
        parser.error(f'Links file not found: {args.links}')
    links, rejected = read_links(args.links)
    if not links:
        parser.error('No supported video URLs found')
    if not args.plan and not args.ffmpeg and not shutil.which('ffmpeg'):
        parser.error('Install FFmpeg or provide --ffmpeg before downloading')
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda task: process(task[1], task[0], args), enumerate(links, 1)))
    report = {'results': results, 'rejected_lines': rejected}
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in results:
        print(f"{item['index']:02d} {item['status']}: {item.get('file') or item.get('folder') or item.get('error')}")
    if rejected:
        print(f'Ignored unsupported lines: {rejected}')
    return 1 if any(r['status'] == 'failed' for r in results) or rejected else 0
