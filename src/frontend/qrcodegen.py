"""
Generador de códigos QR en Python puro (sin dependencias externas).
Basado en la implementación de dominio público/MIT de Project Nayuki.
Permite generar código SVG puro para renderizar en Streamlit de forma 100% offline.
"""

from __future__ import annotations
import collections.abc
from enum import Enum
from typing import List, Optional, Sequence, Tuple


class QrCode:
    """Representa un código QR 2D con corrección de errores Reed-Solomon."""

    MIN_VERSION = 1
    MAX_VERSION = 40

    class Ecc(Enum):
        LOW = (0, 1)  # ~7% recuperación
        MEDIUM = (1, 0)  # ~15% recuperación
        QUARTILE = (2, 3)  # ~25% recuperación
        HIGH = (3, 2)  # ~30% recuperación

        ordinal: int
        format_bits: int

        def __init__(self, ordinal: int, format_bits: int):
            self.ordinal = ordinal
            self.format_bits = format_bits

    def __init__(self, version: int, ecc: QrCode.Ecc, data_codewords: Sequence[int], msk: int):
        if not (QrCode.MIN_VERSION <= version <= QrCode.MAX_VERSION):
            raise ValueError("Versión de código QR fuera de rango")
        if not (-1 <= msk <= 7):
            raise ValueError("Valor de máscara fuera de rango")

        self.version = version
        self.size = version * 4 + 17
        self.ecc = ecc

        self._modules = [[False] * self.size for _ in range(self.size)]
        self._is_function = [[False] * self.size for _ in range(self.size)]

        self._draw_function_patterns()
        all_codewords = self._add_ecc_and_interleave(data_codewords)
        self._draw_codewords(all_codewords)

        if msk == -1:
            min_penalty = 1 << 30
            best_mask = 0
            for mask_candidate in range(8):
                self._apply_mask(mask_candidate)
                self._draw_format_bits(mask_candidate)
                penalty = self._get_penalty_score()
                if penalty < min_penalty:
                    min_penalty = penalty
                    best_mask = mask_candidate
                self._apply_mask(mask_candidate)  # revert
            msk = best_mask

        self.mask = msk
        self._apply_mask(msk)
        self._draw_format_bits(msk)
        self._is_function = []

    def get_module(self, x: int, y: int) -> bool:
        return 0 <= x < self.size and 0 <= y < self.size and self._modules[y][x]

    @staticmethod
    def encode_text(text: str, ecc: QrCode.Ecc) -> QrCode:
        data_bytes = text.encode("utf-8")
        seg = QrSegment.make_bytes(data_bytes)
        return QrCode.encode_segments([seg], ecc)

    @staticmethod
    def encode_segments(segs: Sequence[QrSegment], ecc: QrCode.Ecc,
                        min_version: int = 1, max_version: int = 40,
                        mask: int = -1, boost_ecc: bool = True) -> QrCode:
        for version in range(min_version, max_version + 1):
            data_capacity_bits = QrCode._get_num_data_codewords(version, ecc) * 8
            data_used_bits = QrSegment.get_total_bits(segs, version)
            if data_used_bits != -1 and data_used_bits <= data_capacity_bits:
                break
        else:
            raise ValueError("Los datos no caben en el rango de versiones QR especificado")

        for new_ecc in (QrCode.Ecc.HIGH, QrCode.Ecc.QUARTILE, QrCode.Ecc.MEDIUM):
            if boost_ecc and data_used_bits <= QrCode._get_num_data_codewords(version, new_ecc) * 8:
                ecc = new_ecc

        bb = []
        for seg in segs:
            QrCode._append_bits(seg.mode.mode_bits, 4, bb)
            QrCode._append_bits(seg.num_chars, seg.mode.num_char_count_bits(version), bb)
            bb.extend(seg._bit_data)

        data_capacity_bits = QrCode._get_num_data_codewords(version, ecc) * 8
        QrCode._append_bits(0, min(4, data_capacity_bits - len(bb)), bb)
        QrCode._append_bits(0, (8 - len(bb) % 8) % 8, bb)
        pad_byte = 0xEC
        while len(bb) < data_capacity_bits:
            QrCode._append_bits(pad_byte, 8, bb)
            pad_byte ^= 0xEC ^ 0x11

        data_codewords = [0] * (len(bb) // 8)
        for i, bit in enumerate(bb):
            data_codewords[i >> 3] |= bit << (7 - (i & 7))

        return QrCode(version, ecc, data_codewords, mask)

    def to_svg_str(self, border: int = 4, fg_color: str = "#0f172a", bg_color: str = "#ffffff") -> str:
        """Genera una cadena XML con el SVG del código QR."""
        if border < 0:
            raise ValueError("El borde no puede ser negativo")
        total_size = self.size + border * 2
        rects = []
        for y in range(self.size):
            for x in range(self.size):
                if self.get_module(x, y):
                    rects.append(f'<rect x="{x + border}" y="{y + border}" width="1" height="1" fill="{fg_color}" />')
        rects_str = "".join(rects)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_size} {total_size}" '
            f'width="100%" height="100%" shape-rendering="crispEdges">\n'
            f'<rect width="{total_size}" height="{total_size}" fill="{bg_color}" />\n'
            f'{rects_str}\n</svg>'
        )

    def _draw_function_patterns(self) -> None:
        for i in range(self.size):
            self._set_function_module(6, i, i % 2 == 0)
            self._set_function_module(i, 6, i % 2 == 0)

        self._draw_finder_pattern(3, 3)
        self._draw_finder_pattern(self.size - 4, 3)
        self._draw_finder_pattern(3, self.size - 4)

        align_pat_pos = self._get_alignment_pattern_positions()
        num_align = len(align_pat_pos)
        for i in range(num_align):
            for j in range(num_align):
                if not ((i == 0 and j == 0) or (i == 0 and j == num_align - 1) or (i == num_align - 1 and j == 0)):
                    self._draw_alignment_pattern(align_pat_pos[i], align_pat_pos[j])

        self._draw_format_bits(0)
        self._draw_version()

    def _draw_format_bits(self, mask: int) -> None:
        data = self.ecc.format_bits << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412

        for i in range(0, 6):
            self._set_function_module(8, i, self._get_bit(bits, i))
        self._set_function_module(8, 7, self._get_bit(bits, 6))
        self._set_function_module(8, 8, self._get_bit(bits, 7))
        self._set_function_module(7, 8, self._get_bit(bits, 8))
        for i in range(9, 15):
            self._set_function_module(14 - i, 8, self._get_bit(bits, i))

        for i in range(0, 8):
            self._set_function_module(self.size - 1 - i, 8, self._get_bit(bits, i))
        for i in range(8, 15):
            self._set_function_module(8, self.size - 15 + i, self._get_bit(bits, i))
        self._set_function_module(8, self.size - 8, True)

    def _draw_version(self) -> None:
        if self.version < 7:
            return
        rem = self.version
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = self.version << 12 | rem
        for i in range(18):
            bit = self._get_bit(bits, i)
            a = self.size - 11 + i % 3
            b = i // 3
            self._set_function_module(a, b, bit)
            self._set_function_module(b, a, bit)

    def _draw_finder_pattern(self, x: int, y: int) -> None:
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                dist = max(abs(dx), abs(dy))
                xx = x + dx
                yy = y + dy
                if 0 <= xx < self.size and 0 <= yy < self.size:
                    self._set_function_module(xx, yy, dist != 2 and dist != 4)

    def _draw_alignment_pattern(self, x: int, y: int) -> None:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                self._set_function_module(x + dx, y + dy, max(abs(dx), abs(dy)) != 1)

    def _set_function_module(self, x: int, y: int, is_dark: bool) -> None:
        self._modules[y][x] = is_dark
        self._is_function[y][x] = True

    def _add_ecc_and_interleave(self, data: Sequence[int]) -> List[int]:
        ver = self.version
        ecc = self.ecc
        num_blocks = QrCode._NUM_ERROR_CORRECTION_BLOCKS[ecc.ordinal][ver]
        block_ecc_len = QrCode._ECC_CODEWORDS_PER_BLOCK[ecc.ordinal][ver]
        raw_codewords = QrCode._get_num_raw_data_modules(ver) // 8
        num_short_blocks = num_blocks - raw_codewords % num_blocks
        short_block_len = raw_codewords // num_blocks

        blocks: List[List[int]] = []
        rs_div = QrCode._reed_solomon_compute_divisor(block_ecc_len)
        k = 0
        for i in range(num_blocks):
            dat = list(data[k : k + short_block_len - block_ecc_len + (0 if i < num_short_blocks else 1)])
            k += len(dat)
            ecc_bytes = QrCode._reed_solomon_compute_remainder(dat, rs_div)
            if i < num_short_blocks:
                dat.append(0)
            dat.extend(ecc_bytes)
            blocks.append(dat)

        result: List[int] = []
        for i in range(len(blocks[0])):
            for j, blk in enumerate(blocks):
                if i != short_block_len - block_ecc_len or j >= num_short_blocks:
                    result.append(blk[i])
        return result

    def _draw_codewords(self, data: Sequence[int]) -> None:
        i = 0
        right = self.size - 1
        while right > 0:
            if right == 6:
                right = 5
            for vert in range(self.size):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = (self.size - 1 - vert) if upward else vert
                    if not self._is_function[y][x] and i < len(data) * 8:
                        self._modules[y][x] = self._get_bit(data[i >> 3], 7 - (i & 7))
                        i += 1
            right -= 2

    def _apply_mask(self, mask: int) -> None:
        for y in range(self.size):
            for x in range(self.size):
                if not self._is_function[y][x]:
                    invert = False
                    if mask == 0:
                        invert = (x + y) % 2 == 0
                    elif mask == 1:
                        invert = y % 2 == 0
                    elif mask == 2:
                        invert = x % 3 == 0
                    elif mask == 3:
                        invert = (x + y) % 3 == 0
                    elif mask == 4:
                        invert = (x // 3 + y // 2) % 2 == 0
                    elif mask == 5:
                        invert = (x * y) % 2 + (x * y) % 3 == 0
                    elif mask == 6:
                        invert = ((x * y) % 2 + (x * y) % 3) % 2 == 0
                    elif mask == 7:
                        invert = ((x + y) % 2 + (x * y) % 3) % 2 == 0
                    self._modules[y][x] ^= invert

    def _get_penalty_score(self) -> int:
        result = 0
        size = self.size
        modules = self._modules
        for y in range(size):
            run_color = False
            run_val = 0
            for x in range(size):
                if modules[y][x] == run_color:
                    run_val += 1
                    if run_val == 5:
                        result += 3
                    elif run_val > 5:
                        result += 1
                else:
                    run_color = modules[y][x]
                    run_val = 1
        for x in range(size):
            run_color = False
            run_val = 0
            for y in range(size):
                if modules[y][x] == run_color:
                    run_val += 1
                    if run_val == 5:
                        result += 3
                    elif run_val > 5:
                        result += 1
                else:
                    run_color = modules[y][x]
                    run_val = 1
        for y in range(size - 1):
            for x in range(size - 1):
                color = modules[y][x]
                if color == modules[y][x + 1] == modules[y + 1][x] == modules[y + 1][x + 1]:
                    result += 3
        black = sum(sum(1 for val in row if val) for row in modules)
        total = size * size
        k = (abs(black * 20 - total * 10) + total - 1) // total - 1
        result += k * 10
        return result

    def _get_alignment_pattern_positions(self) -> List[int]:
        if self.version == 1:
            return []
        num = self.version // 7 + 2
        step = (self.version * 8 + num * 3 + 5) // (num * 4 - 4) * 2
        result = [6] + [self.size - 7 - (num - 1 - i) * step for i in range(1, num)]
        return result

    @staticmethod
    def _get_num_raw_data_modules(ver: int) -> int:
        size = ver * 4 + 17
        result = size * size
        result -= 8 * 8 * 3
        result -= (size - 16) * 2
        if ver >= 2:
            num_align = ver // 7 + 2
            result -= (num_align * num_align - 3) * 25
            result += (num_align - 2) * 2 * 5 * 2
        if ver >= 7:
            result -= 6 * 3 * 2
        return result

    @staticmethod
    def _get_num_data_codewords(ver: int, ecc: QrCode.Ecc) -> int:
        return QrCode._get_num_raw_data_modules(ver) // 8 - (
            QrCode._ECC_CODEWORDS_PER_BLOCK[ecc.ordinal][ver]
            * QrCode._NUM_ERROR_CORRECTION_BLOCKS[ecc.ordinal][ver]
        )

    @staticmethod
    def _reed_solomon_compute_divisor(degree: int) -> List[int]:
        result = [0] * (degree - 1) + [1]
        root = 1
        for _ in range(degree):
            for j in range(degree):
                result[j] = QrCode._reed_solomon_multiply(result[j], root)
                if j + 1 < degree:
                    result[j] ^= result[j + 1]
            root = QrCode._reed_solomon_multiply(root, 0x02)
        return result

    @staticmethod
    def _reed_solomon_compute_remainder(data: Sequence[int], divisor: Sequence[int]) -> List[int]:
        result = [0] * len(divisor)
        for b in data:
            factor = b ^ result.pop(0)
            result.append(0)
            for i, coef in enumerate(divisor):
                result[i] ^= QrCode._reed_solomon_multiply(coef, factor)
        return result

    @staticmethod
    def _reed_solomon_multiply(x: int, y: int) -> int:
        z = 0
        for i in reversed(range(8)):
            z = (z << 1) ^ ((z >> 7) * 0x11D)
            z ^= ((y >> i) & 1) * x
        return z

    @staticmethod
    def _get_bit(val: int, i: int) -> bool:
        return ((val >> i) & 1) != 0

    @staticmethod
    def _append_bits(val: int, num_bits: int, bb: List[int]) -> None:
        for i in reversed(range(num_bits)):
            bb.append((val >> i) & 1)

    _ECC_CODEWORDS_PER_BLOCK = [
        [-1, 7, 10, 15, 20, 26, 18, 20, 24, 30, 18, 20, 24, 26, 30, 22, 24, 28, 30, 28, 28, 28, 28, 30, 30, 26, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
        [-1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26, 26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28],
        [-1, 13, 22, 18, 26, 18, 24, 18, 22, 20, 24, 28, 26, 24, 20, 30, 24, 28, 28, 26, 30, 28, 30, 30, 30, 30, 28, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
        [-1, 17, 28, 22, 16, 22, 28, 26, 26, 24, 28, 24, 28, 22, 24, 24, 30, 28, 28, 26, 28, 30, 24, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
    ]

    _NUM_ERROR_CORRECTION_BLOCKS = [
        [-1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 4, 4, 4, 4, 4, 6, 6, 6, 6, 7, 8, 8, 9, 9, 10, 12, 12, 12, 13, 14, 15, 16, 17, 18, 19, 19, 20, 21, 22, 24, 25],
        [-1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18, 20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49],
        [-1, 1, 1, 2, 2, 4, 4, 6, 6, 8, 8, 8, 10, 12, 16, 12, 17, 16, 18, 21, 20, 23, 23, 25, 27, 29, 34, 34, 35, 38, 40, 43, 45, 48, 51, 53, 56, 59, 62, 65, 68],
        [-1, 1, 1, 2, 4, 4, 4, 5, 6, 8, 8, 11, 11, 16, 16, 18, 16, 19, 21, 25, 25, 25, 34, 30, 32, 35, 37, 40, 42, 45, 48, 51, 54, 57, 60, 63, 66, 70, 72, 74, 77],
    ]


class QrSegment:
    """Segmento de datos para codificación en QR."""

    class Mode(Enum):
        BYTE = (0x4, (8, 16, 16))

        mode_bits: int
        _cc_bits: Tuple[int, int, int]

        def __init__(self, mode_bits: int, cc_bits: Tuple[int, int, int]):
            self.mode_bits = mode_bits
            self._cc_bits = cc_bits

        def num_char_count_bits(self, ver: int) -> int:
            return self._cc_bits[(ver + 7) // 17]

    def __init__(self, mode: QrSegment.Mode, num_chars: int, bit_data: Sequence[int]):
        self.mode = mode
        self.num_chars = num_chars
        self._bit_data = list(bit_data)

    @staticmethod
    def make_bytes(data: bytes) -> QrSegment:
        bb = []
        for b in data:
            QrCode._append_bits(b, 8, bb)
        return QrSegment(QrSegment.Mode.BYTE, len(data), bb)

    @staticmethod
    def get_total_bits(segs: Sequence[QrSegment], version: int) -> int:
        result = 0
        for seg in segs:
            ccbits = seg.mode.num_char_count_bits(version)
            if seg.num_chars >= (1 << ccbits):
                return -1
            result += 4 + ccbits + len(seg._bit_data)
        return result
