"""Compatibility scenarios: the same inputs on base and candidate must give the same result."""
import struct

HELPER = 0x15FEE
FIXTURE = 0x30000000
STATE, SOURCE, DEST = FIXTURE, FIXTURE+0x2000, FIXTURE+0x4000
WORDS = 896


def _mix(machine, mode, frame, route):
    machine.write(STATE+0xEC, struct.pack('<I', mode))
    pcm = [v & 0xFFFFFFFF for f in range(64) for v in (1000+f*31, -2000-f*19)]
    machine.write(SOURCE, struct.pack('<128I', *pcm))
    machine.write(DEST, bytes(WORDS*4))
    machine.call(HELPER, (STATE, DEST, frame, SOURCE, 100, route, 10000, 10000, 1))
    return machine.read(DEST, WORDS*4)


def mixer_output_unchanged(base, candidate):
    compared = 0
    for mode in (0, 0xD, 0x73):
        for frame in (0, 1, 31, 63):
            for route in (0, 1, 4, 6):
                a, b = _mix(base, mode, frame, route), _mix(candidate, mode, frame, route)
                if not any(a):
                    raise AssertionError(f'silent fixture at {mode}, {frame}, {route}: the comparison would be empty')
                if a != b:
                    raise AssertionError(f'output differs at mode {mode}, frame {frame}, route {route}')
                compared += 1
    return compared
