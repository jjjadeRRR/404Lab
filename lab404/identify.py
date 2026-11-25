"""Say what an APP1 is, or say that we do not know.

Only an exact full SHA256 match counts as known. Version strings and row counts are hints for the conversation with the user: a
string can survive inside a modified image, so a hint never makes an image known.
"""
import json
import re
from pathlib import Path

from .image import Image, ImageError, sha256

TABLE = json.loads((Path(__file__).parent/'known_images.json').read_text(encoding='utf-8'))['images']
STOCK_ROWS = 12  # [BYTES] stock 5.52, DOOM OS 0.7.2, 0.7.3 and 0.7.4 all have 12 scatter rows
HINTS = (rb'DOOM ?OS [0-9]+\.[0-9]+(?:\.[0-9]+)?[- ][0-9A-F]{4}', rb'SiPi v[0-9.]+', rb'[Tt]ampal[ -][0-9.]+')


def identify(raw):
    result = dict(status='unknown', sha256=sha256(raw), size=len(raw), family=None, version=None, source=None,
                  structure=None, scatter_rows=None, hints=[])
    try:
        image = Image(raw)
    except ImageError as e:
        result.update(status='invalid', structure=str(e))
        return result
    result.update(structure='ok', scatter_rows=len(image.rows))
    for entry in TABLE:
        if entry['sha256'] == result['sha256']:
            result.update(status='known', family=entry['family'], version=entry['version'], source=entry['source'])
    for pattern in HINTS:
        found = {m.group().decode('ascii') for _, data, _ in image.segments for m in re.finditer(pattern, data)}
        result['hints'] += sorted(found)
    if result['status'] != 'known' and len(image.rows) != STOCK_ROWS:
        result['hints'].append(f'{len(image.rows)} scatter rows, {STOCK_ROWS} in stock: extra rows suggest a mod')
    return result


def explain(result):
    if result['status'] == 'known':
        return f'{result["family"]} {result["version"]}, exact match. {result["source"]}'
    if result['status'] == 'invalid':
        return f'Not a usable APP1: {result["structure"]}. Do not build on it.'
    hints = '; '.join(result['hints']) or 'none'
    return (f'Unknown image, hash {result["sha256"]}. Hints, not proof: {hints}. '
            'Ask the user where it came from. Do not assume any address applies to it until it is checked.')
