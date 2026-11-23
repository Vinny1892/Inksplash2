"""Regression cases for the AArch64 jump-table matcher."""

import importlib.util
from pathlib import Path
import struct
import unittest


GENERATOR = Path(__file__).resolve().parents[1] / 'baseline/totk-recomp/tools/recomp/gen.py'
spec = importlib.util.spec_from_file_location('recomp_generator', GENERATOR)
gen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen)


class JumpTableTests(unittest.TestCase):
    def test_adjacent_switches_use_the_current_indexed_load(self):
        # The first switch loads into x8. At the second add, x8 now holds
        # the new table base and x9 holds the entry loaded from that table.
        ops = [
            ('cmp', 'w8, #1'),
            ('b.hi', '#0x11c'),
            ('adrp', 'x9, #0x1000'),
            ('add', 'x9, x9, #0x40'),
            ('ldrsw', 'x8, [x9, x8, lsl #2]'),
            ('add', 'x8, x8, x9'),
            ('br', 'x8'),
            ('mov', 'w9, w8'),
            ('cmp', 'w8, #1'),
            ('b.hi', '#0x14c'),
            ('adrp', 'x8, #0x1000'),
            ('add', 'x8, x8, #0x80'),
            ('ldrsw', 'x9, [x8, x9, lsl #2]'),
            ('add', 'x8, x9, x8'),
            ('br', 'x8'),
        ]
        instructions = [(0x100 + i * 4, 4, op, args) for i, (op, args) in enumerate(ops)]
        image = bytearray(0x1090)
        struct.pack_into('<iiI', image, 0x1040, 0x11c - 0x1040, 0x120 - 0x1040, 1)
        struct.pack_into('<iiI', image, 0x1080, 0x13c - 0x1080, 0x144 - 0x1080, 1)
        emitter = gen.Emitter(bytes(image), {}, {}, {}, [])

        self.assertEqual(emitter.jump_table(instructions, 6, 0x100, 0x150), [0x11c, 0x120])
        self.assertEqual(emitter.jump_table(instructions, 14, 0x100, 0x150), [0x13c, 0x144])


if __name__ == '__main__':
    unittest.main()
