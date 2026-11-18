"""The knowledge base: checked records about the unit and its firmwares, queried instead of read end to end.

knowledge/
  controls.json          every physical control, by canonical name
  facts/<topic>.json     claims with evidence and, where possible, byte checks a script can run on the user's image
                         (size and SHA-256 of the bytes, so the repository holds no firmware)
  bindings/<fw>.json     key bindings of one firmware, with a coverage statement per screen
  screens/<fw>.json      screens of one firmware
  notes/*.md             short explanations that name fact ids

An unknown is a valid record. A binding database that does not cover a screen answers `unknown` for that screen, never `free`.
"""
import json
from pathlib import Path

from .identify import TABLE
from .image import Image, ImageError, matches

ROOT = Path(__file__).resolve().parents[1]/'knowledge'
LABELS = ('HARDWARE', 'EMULATOR', 'BYTES', 'DOC', 'HYPOTHESIS')
STATUSES = ('verified', 'unknown', 'hypothesis', 'disputed')
COVERAGE = ('complete', 'partial', 'unknown')
GESTURES = ('press', 'hold', 'release', 'turn', 'press_turn', 'power_on')
ANY = 'any'


CONTACT = ('press', 'hold', 'release', 'press_turn')  # gestures that act on putting a key down or letting it up


def _gestures_collide(one, other):
    """A press, a hold and a release of the same keys start with the same contact, so they cannot mean different things without changing timing. A turn is a separate motion."""
    if one == other or 'press_turn' in (one, other):
        return True
    return one in CONTACT and other in CONTACT


def gaps(root=ROOT):
    """The questions a mod author must have answered that are not fully answered yet (knowledge/required.json)."""
    return [q for q in json.loads((Path(root)/'required.json').read_text(encoding='utf-8'))['questions'] if q['state'] != 'known']


class KnowledgeError(ValueError):
    pass


def firmware_ids():
    ids = {ANY}
    for entry in TABLE:
        family = entry['family']
        if family in ('stock', 'doom-os'):
            ids.add(f'{family}-{entry["version"].split()[0]}')
        else:
            ids.add(family)
    return ids | {'side-piece', 'etc', 'tallfree', 'irakliymod'}


def firmware_id_of(entry):
    if entry['family'] in ('stock', 'doom-os'):
        return f'{entry["family"]}-{entry["version"].split()[0]}'
    return entry['family']


def _need(record, fields, where):
    for field in fields:
        if field not in record:
            raise KnowledgeError(f'{where}: missing {field}')


def _check_evidence(evidence, where):
    if not isinstance(evidence, list) or not evidence:
        raise KnowledgeError(f'{where}: needs evidence')
    for item in evidence:
        _need(item, ('label', 'source'), where)
        if item['label'] not in LABELS:
            raise KnowledgeError(f'{where}: unknown evidence label {item["label"]}')
        if not str(item['source']).strip():
            raise KnowledgeError(f'{where}: empty evidence source')


def _check_firmware(value, where, known):
    for fw in value if isinstance(value, list) else [value]:
        if fw not in known:
            raise KnowledgeError(f'{where}: unknown firmware {fw}')


def validate_fact(fact, known, where='fact'):
    _need(fact, ('id', 'claim', 'topic', 'firmware', 'status', 'evidence'), where)
    where = f'fact {fact["id"]}'
    if fact['status'] not in STATUSES:
        raise KnowledgeError(f'{where}: unknown status {fact["status"]}')
    _check_firmware(fact['firmware'], where, known)
    _check_evidence(fact['evidence'], where)
    labels = {item['label'] for item in fact['evidence']}
    if fact['status'] == 'verified' and labels <= {'HYPOTHESIS'}:
        raise KnowledgeError(f'{where}: a hypothesis cannot be verified')
    for check in fact.get('checks', []):
        _need(check, ('firmware', 'address'), where)
        _check_firmware(check['firmware'], where, known)
        int(check['address'], 16)
        if 'sha256' in check:
            _need(check, ('size',), where)
            if not 0 < int(check['size']) <= 4096 or len(check['sha256']) != 64:
                raise KnowledgeError(f'{where}: a check needs a size of 1-4096 bytes and a 64-digit sha256')
            int(check['sha256'], 16)
        elif 'hex' in check:
            bytes.fromhex(check['hex'])
        else:
            raise KnowledgeError(f'{where}: a check needs size and sha256 (or hex, for local use only)')


def validate_binding(binding, controls, where='binding'):
    _need(binding, ('id', 'screen', 'keys', 'gesture', 'action', 'status', 'evidence'), where)
    where = f'binding {binding["id"]}'
    if binding['gesture'] not in GESTURES:
        raise KnowledgeError(f'{where}: unknown gesture {binding["gesture"]}')
    if binding['status'] not in STATUSES:
        raise KnowledgeError(f'{where}: unknown status {binding["status"]}')
    for key in binding['keys']:
        if key not in controls:
            raise KnowledgeError(f'{where}: unknown control {key}')
    _check_evidence(binding['evidence'], where)


def validate_screen(screen, where='screen'):
    _need(screen, ('id', 'name', 'status', 'evidence'), where)
    if screen['status'] not in STATUSES:
        raise KnowledgeError(f'screen {screen["id"]}: unknown status')
    _check_evidence(screen['evidence'], f'screen {screen["id"]}')


class Knowledge:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.known = firmware_ids()
        self.facts = []
        self.bindings = {}  # firmware id -> {'coverage': {...}, 'inherits': id|None, 'bindings': [...]}
        self.screens = {}
        self.controls = set()
        path = self.root/'controls.json'
        if path.exists():
            self.controls = {c['name'] for c in json.loads(path.read_text(encoding='utf-8'))['controls']}
        seen = set()
        for path in sorted((self.root/'facts').glob('*.json')) if (self.root/'facts').exists() else []:
            for fact in json.loads(path.read_text(encoding='utf-8'))['facts']:
                validate_fact(fact, self.known, path.name)
                self._unique(fact['id'], seen)
                self.facts.append(fact)
        for path in sorted((self.root/'bindings').glob('*.json')) if (self.root/'bindings').exists() else []:
            data = json.loads(path.read_text(encoding='utf-8'))
            _check_firmware(data['firmware'], path.name, self.known)
            for state in data['coverage'].values():
                if state not in COVERAGE:
                    raise KnowledgeError(f'{path.name}: unknown coverage {state}')
            for binding in data['bindings']:
                validate_binding(binding, self.controls, path.name)
                self._unique(binding['id'], seen)
            self.bindings[data['firmware']] = data
        for path in sorted((self.root/'screens').glob('*.json')) if (self.root/'screens').exists() else []:
            data = json.loads(path.read_text(encoding='utf-8'))
            _check_firmware(data['firmware'], path.name, self.known)
            for screen in data['screens']:
                validate_screen(screen, path.name)
            self.screens[data['firmware']] = data['screens']

    @staticmethod
    def _unique(record_id, seen):
        if record_id in seen:
            raise KnowledgeError(f'duplicate id {record_id}')
        seen.add(record_id)

    def query(self, term, firmware=None):
        term = term.lower()
        words = term.split()
        exact, out = [], []
        for fact in self.facts:
            fw = fact['firmware'] if isinstance(fact['firmware'], list) else [fact['firmware']]
            if firmware and firmware not in fw and ANY not in fw:
                continue
            text = json.dumps(fact, ensure_ascii=False).lower()
            if term in text:
                exact.append(fact)
            elif len(words) > 1 and all(word in text for word in words):
                out.append(fact)
        return exact+out

    def topics(self):
        """{topic: number of facts}, so an agent can see what there is to ask about."""
        count = {}
        for fact in self.facts:
            count[fact['topic']] = count.get(fact['topic'], 0)+1
        return dict(sorted(count.items()))

    def chain(self, firmware):
        """This firmware's binding file and the ones it inherits from, nearest first."""
        out = []
        while firmware and firmware in self.bindings and firmware not in [d['firmware'] for d in out]:
            out.append(self.bindings[firmware])
            firmware = self.bindings[firmware].get('inherits')
        return out

    def check_keys(self, firmware, screen, keys, gesture='press'):
        """Is this input free on this screen? Returns ('occupied', binding), ('free', None) or ('unknown', reason)."""
        chain = self.chain(firmware)
        if not chain:
            return 'unknown', f'no key binding data for {firmware}'
        for name in keys:
            if name not in self.controls:
                raise KnowledgeError(f'unknown control {name}')
        wanted = set(keys)
        prefixes = {frozenset(keys[:i]): '+'.join(keys[:i]) for i in range(1, len(keys))}
        for data in chain:
            for binding in data['bindings']:
                if binding['screen'] not in (screen, ANY):
                    continue
                held = frozenset(binding['keys'])
                if held == wanted and _gestures_collide(binding['gesture'], gesture):
                    return 'occupied', binding
                if held in prefixes and binding['gesture'] in CONTACT:  # that binding fires on the way to this chord
                    return 'occupied', {**binding, 'conflict': f'starts with {prefixes[held]}'}
        for data in chain:
            state = data['coverage'].get(screen)
            if state != 'complete':
                return 'unknown', f'{data["firmware"]}: coverage of screen {screen} is {state or "not recorded"}'
        return 'free', None

    def verify(self, image, firmware):
        """Run byte checks for this firmware on the user's image. Returns [(fact id, 'pass'|'fail', detail)]."""
        image = image if isinstance(image, Image) else Image(image)
        results = []
        for fact in self.facts:
            for check in fact.get('checks', []):
                if check['firmware'] != firmware:
                    continue
                try:
                    same, got = matches(image, int(check['address'], 16), check)
                    state = 'pass' if same else 'fail'
                    detail = f'{check["address"]}: sha256 {got}'
                except ImageError as e:
                    state, detail = 'fail', str(e)
                results.append((fact['id'], state, detail))
        return results
