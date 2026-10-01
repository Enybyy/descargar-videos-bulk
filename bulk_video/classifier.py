"""Deterministic classification shared with the browser through a JSON rule file."""
import json
from pathlib import Path
import re
import unicodedata

RULES_PATH = Path(__file__).resolve().parent.parent / 'demo' / 'rules.json'


def normalize(value):
    value = unicodedata.normalize('NFD', value.casefold())
    return re.sub(r'[_\s]+', ' ', ''.join(c for c in value if not unicodedata.combining(c)))


def classify(title, description='', transcript=''):
    """Prioritize explicit week labels; otherwise score complete keyword phrases."""
    title_text = normalize(title)
    week = re.search(r'\bsem(?:ana)?\s*[-:]?\s*(\d{1,2})\b', title_text)
    if week and 1 <= int(week[1]) <= 19:
        number = int(week[1])
        return {'folder': f'{number:02d}_Civil3D_Semana_{number}', 'reason': f'Week {number} in title'}
    rules = json.loads(RULES_PATH.read_text(encoding='utf-8'))
    metadata = normalize(title + ' ' + description)
    transcript = normalize(transcript)
    best, score = None, 0
    for rule in rules:
        current = 0
        for keyword in rule['keywords']:
            pattern = r'\b' + re.escape(normalize(keyword)) + r'\b'
            current += 3 * len(re.findall(pattern, metadata)) + len(re.findall(pattern, transcript))
        if current > score:
            best, score = rule, current
    if best:
        return {'folder': best['folder'], 'reason': f'Keyword score: {score}'}
    return {'folder': '13_Diseno_Geometrico_Otros' if title.upper().startswith('DGV') else '14_Otros', 'reason': 'No matching week or topic'}
