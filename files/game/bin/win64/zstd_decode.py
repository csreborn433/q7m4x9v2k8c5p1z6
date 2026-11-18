"""Small decode-only Zstandard (RFC 8878) implementation for the bundled runtime.

The embeddable Python shipped with the mod has no zstd module. Some legacy KV3
blocks use zstd, so this decoder supports single and concatenated frames
without dictionaries. It follows the structure of the zstd educational decoder.
"""

import struct

MAGIC = 0xFD2FB528

LL_BASE = list(range(16)) + [16, 18, 20, 22, 24, 28, 32, 40, 48, 64, 128, 256, 512, 1024, 2048, 4096,
                             8192, 16384, 32768, 65536]
LL_BITS = [0] * 16 + [1, 1, 1, 1, 2, 2, 3, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
ML_BASE = [n + 3 for n in range(32)] + [35, 37, 39, 41, 43, 47, 51, 59, 67, 83, 99, 131, 259, 515, 1027,
                                        2051, 4099, 8195, 16387, 32771, 65539]
ML_BITS = [0] * 32 + [1, 1, 1, 1, 2, 2, 3, 3, 4, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
LL_DEFAULT = (6, [4, 3, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 3, 2, 1, 1, 1,
                  1, 1, -1, -1, -1, -1])
ML_DEFAULT = (6, [1, 4, 3, 2, 2, 2, 2, 2, 2] + [1] * 37 + [-1] * 7)
OF_DEFAULT = (5, [1, 1, 1, 1, 1, 1, 2, 2, 2] + [1] * 15 + [-1] * 5)


class ZstdError(ValueError):
    pass


class _Forward:
    def __init__(self, data, position=0):
        self.data, self.bit = data, position * 8

    def read(self, count):
        if not count: return 0
        start, end = self.bit >> 3, (self.bit + count + 7) >> 3
        if end > len(self.data): raise ZstdError('Truncated zstd table description')
        value = (int.from_bytes(self.data[start:end], 'little') >> (self.bit & 7)) & ((1 << count) - 1)
        self.bit += count
        return value


class _Backward:
    def __init__(self, data):
        if not data or not data[-1]: raise ZstdError('Invalid zstd bitstream padding')
        self.data = data
        self.bit = (len(data) - 1) * 8 + data[-1].bit_length() - 1

    def read(self, count):
        if not count: return 0
        self.bit -= count
        low = self.bit
        shift = 0
        if low < 0:
            shift, low = -low, 0
            if self.bit + count <= 0: return 0
        start, end = low >> 3, (self.bit + count + 7) >> 3
        value = int.from_bytes(self.data[start:end], 'little') >> (low & 7)
        return (value << shift) & ((1 << count) - 1)


class _Fse:
    def __init__(self, accuracy, counts):
        size = 1 << accuracy
        self.accuracy = accuracy
        self.symbols, self.bits, self.base = [0] * size, [0] * size, [0] * size
        high, state = size, {}
        for symbol, count in enumerate(counts):
            if count == -1:
                high -= 1; self.symbols[high] = symbol; state[symbol] = 1
        position, step, mask = 0, (size >> 1) + (size >> 3) + 3, size - 1
        for symbol, count in enumerate(counts):
            if count <= 0: continue
            state[symbol] = count
            for _ in range(count):
                self.symbols[position] = symbol
                position = (position + step) & mask
                while position >= high: position = (position + step) & mask
        if position: raise ZstdError('Invalid zstd FSE distribution')
        for index in range(size):
            symbol = self.symbols[index]
            following = state[symbol]; state[symbol] += 1
            self.bits[index] = accuracy - (following.bit_length() - 1)
            self.base[index] = (following << self.bits[index]) - size

    @classmethod
    def rle(cls, symbol):
        table = cls.__new__(cls)
        table.accuracy, table.symbols, table.bits, table.base = 0, [symbol], [0], [0]
        return table

    @classmethod
    def read(cls, data, position, maximum):
        stream = _Forward(data, position)
        accuracy = stream.read(4) + 5
        if accuracy > maximum: raise ZstdError('zstd FSE accuracy too large')
        remaining, counts = (1 << accuracy) + 1, []
        while remaining > 1:
            bits = remaining.bit_length()
            value = stream.read(bits)
            lower = (1 << (bits - 1)) - 1
            threshold = (1 << bits) - 1 - remaining
            if (value & lower) < threshold:
                stream.bit -= 1; value &= lower
            elif value > lower:
                value -= threshold
            count = value - 1
            remaining -= abs(count)
            counts.append(count)
            if count == 0:
                repeat = stream.read(2)
                while True:
                    counts.extend([0] * repeat)
                    if repeat != 3: break
                    repeat = stream.read(2)
            if len(counts) > 256: raise ZstdError('Too many zstd FSE symbols')
        if remaining != 1: raise ZstdError('Invalid zstd FSE probabilities')
        return cls(accuracy, counts), ((stream.bit + 7) >> 3) - position


class _Huffman:
    def __init__(self, weights):
        total = sum(1 << (w - 1) for w in weights if w)
        if not total: raise ZstdError('Empty zstd Huffman table')
        self.max_bits = total.bit_length()
        rest = (1 << self.max_bits) - total
        if rest & (rest - 1): raise ZstdError('Invalid zstd Huffman weights')
        weights = list(weights) + [rest.bit_length()]
        if self.max_bits > 11: raise ZstdError('zstd Huffman depth too large')
        bits = [self.max_bits + 1 - w if w else 0 for w in weights]
        ranks = [0] * (self.max_bits + 2)
        for length in bits:
            if length: ranks[length] += 1
        starts = [0] * (self.max_bits + 2)
        for length in range(self.max_bits, 0, -1):
            starts[length - 1] = starts[length] + ranks[length] * (1 << (self.max_bits - length))
        size = 1 << self.max_bits
        self.symbols, self.lengths = [0] * size, [0] * size
        for symbol, length in enumerate(bits):
            if not length: continue
            code, span = starts[length], 1 << (self.max_bits - length)
            self.symbols[code:code + span] = [symbol] * span
            self.lengths[code:code + span] = [length] * span
            starts[length] += span

    def decode(self, data, count):
        stream = _Backward(data)
        state = stream.read(self.max_bits)
        mask, out = (1 << self.max_bits) - 1, bytearray(count)
        symbols, lengths = self.symbols, self.lengths
        for index in range(count):
            out[index] = symbols[state]
            length = lengths[state]
            state = ((state << length) + stream.read(length)) & mask
        if stream.bit != -self.max_bits: raise ZstdError('zstd Huffman stream size mismatch')
        return out

    @classmethod
    def read(cls, data, position):
        header = data[position]
        if header >= 128:
            count = header - 127
            raw = data[position + 1:position + 1 + (count + 1) // 2]
            weights = [(raw[i // 2] >> 4) if i % 2 == 0 else raw[i // 2] & 15 for i in range(count)]
            return cls(weights), position + 1 + (count + 1) // 2
        table, used = _Fse.read(data, position + 1, 6)
        stream = _Backward(data[position + 1 + used:position + 1 + header])
        states = [stream.read(table.accuracy), stream.read(table.accuracy)]
        weights, turn = [], 0
        while True:
            state = states[turn]
            weights.append(table.symbols[state])
            states[turn] = table.base[state] + stream.read(table.bits[state])
            if stream.bit < 0:
                weights.append(table.symbols[states[1 - turn]])
                break
            turn = 1 - turn
            if len(weights) > 255: raise ZstdError('Too many zstd Huffman weights')
        return cls(weights), position + 1 + header


class _Frame:
    def __init__(self):
        self.out = bytearray()
        self.huffman = None
        self.tables = [None, None, None]
        self.repeats = [1, 4, 8]

    def literals(self, data, position):
        kind, form = data[position] & 3, (data[position] >> 2) & 3
        if kind < 2:
            if form in (0, 2): size, position = data[position] >> 3, position + 1
            elif form == 1: size, position = (data[position] >> 4) + (data[position + 1] << 4), position + 2
            else:
                size = (data[position] >> 4) + (data[position + 1] << 4) + (data[position + 2] << 12)
                position += 3
            if kind == 0: return bytes(data[position:position + size]), position + size
            return bytes([data[position]]) * size, position + 1
        width, streams = {0: (10, 1), 1: (10, 4), 2: (14, 4), 3: (18, 4)}[form]
        header_size = {10: 3, 14: 4, 18: 5}[width]
        value = int.from_bytes(data[position:position + header_size], 'little')
        mask = (1 << width) - 1
        regenerated, compressed = (value >> 4) & mask, (value >> (4 + width)) & mask
        position += header_size
        end = position + compressed
        if kind == 2:
            self.huffman, position = _Huffman.read(data, position)
        elif self.huffman is None:
            raise ZstdError('zstd treeless literals without a table')
        if streams == 1: return bytes(self.huffman.decode(data[position:end], regenerated)), end
        sizes = struct.unpack_from('<3H', data, position)
        position += 6
        sizes = list(sizes) + [end - position - sum(sizes)]
        part = (regenerated + 3) // 4
        counts = [part, part, part, regenerated - 3 * part]
        out = bytearray()
        for size, count in zip(sizes, counts):
            out += self.huffman.decode(data[position:position + size], count)
            position += size
        return bytes(out), end

    def table(self, slot, mode, data, position, default, maximum):
        if mode == 0: self.tables[slot] = _Fse(*default)
        elif mode == 1: self.tables[slot] = _Fse.rle(data[position]); position += 1
        elif mode == 2:
            self.tables[slot], used = _Fse.read(data, position, maximum)
            position += used
        elif self.tables[slot] is None:
            raise ZstdError('zstd repeat table without a previous table')
        return position

    def block(self, data):
        literals, position = self.literals(data, 0)
        first = data[position]
        if first == 0: count, position = 0, position + 1
        elif first < 128: count, position = first, position + 1
        elif first < 255: count, position = ((first - 128) << 8) + data[position + 1], position + 2
        else: count, position = data[position + 1] + (data[position + 2] << 8) + 0x7F00, position + 3
        out, cursor = self.out, 0
        if count:
            modes = data[position]; position += 1
            position = self.table(0, modes >> 6, data, position, LL_DEFAULT, 9)
            position = self.table(1, (modes >> 4) & 3, data, position, OF_DEFAULT, 8)
            position = self.table(2, (modes >> 2) & 3, data, position, ML_DEFAULT, 9)
            ll, of, ml = self.tables
            stream = _Backward(data[position:])
            ls, os_, ms = stream.read(ll.accuracy), stream.read(of.accuracy), stream.read(ml.accuracy)
            repeats = self.repeats
            for index in range(count):
                of_code, ml_code, ll_code = of.symbols[os_], ml.symbols[ms], ll.symbols[ls]
                if of_code > 31: raise ZstdError('Invalid zstd offset code')
                offset_value = (1 << of_code) + stream.read(of_code)
                match = ML_BASE[ml_code] + stream.read(ML_BITS[ml_code])
                literal = LL_BASE[ll_code] + stream.read(LL_BITS[ll_code])
                if index + 1 < count:
                    ls = ll.base[ls] + stream.read(ll.bits[ls])
                    ms = ml.base[ms] + stream.read(ml.bits[ms])
                    os_ = of.base[os_] + stream.read(of.bits[os_])
                if offset_value > 3:
                    offset = offset_value - 3
                    repeats[:] = [offset, repeats[0], repeats[1]]
                else:
                    slot = offset_value - 1 + (literal == 0)
                    if slot == 0: offset = repeats[0]
                    else:
                        offset = repeats[slot] if slot < 3 else repeats[0] - 1
                        if slot > 1: repeats[2] = repeats[1]
                        repeats[1] = repeats[0]; repeats[0] = offset
                if cursor + literal > len(literals): raise ZstdError('zstd literal overrun')
                out += literals[cursor:cursor + literal]; cursor += literal
                if offset <= 0 or offset > len(out): raise ZstdError('Invalid zstd match offset')
                start = len(out) - offset
                if offset >= match: out += out[start:start + match]
                else:
                    pattern = bytes(out[start:])
                    out += (pattern * (match // offset + 1))[:match]
            if stream.bit != 0: raise ZstdError('zstd sequence stream size mismatch')
        out += literals[cursor:]


def decompress(data):
    data = bytes(data)
    position, result = 0, bytearray()
    while position < len(data):
        magic, = struct.unpack_from('<I', data, position)
        if magic & 0xFFFFFFF0 == 0x184D2A50:
            position += 8 + struct.unpack_from('<I', data, position + 4)[0]
            continue
        if magic != MAGIC: raise ZstdError('Not a zstd frame')
        descriptor = data[position + 4]
        position += 5
        content_flag, single = descriptor >> 6, (descriptor >> 5) & 1
        if descriptor & 8: raise ZstdError('Reserved zstd frame bit set')
        if not single: position += 1
        dictionary = (0, 1, 2, 4)[descriptor & 3]
        if dictionary and int.from_bytes(data[position:position + dictionary], 'little'):
            raise ZstdError('zstd dictionaries are not supported')
        position += dictionary
        content_bytes = (single, 2, 4, 8)[content_flag]
        expected = int.from_bytes(data[position:position + content_bytes], 'little') if content_bytes else None
        if content_bytes == 2: expected += 256
        position += content_bytes
        frame = _Frame()
        while True:
            header = int.from_bytes(data[position:position + 3], 'little')
            position += 3
            last, kind, size = header & 1, (header >> 1) & 3, header >> 3
            if kind == 0: frame.out += data[position:position + size]; position += size
            elif kind == 1: frame.out += bytes([data[position]]) * size; position += 1
            elif kind == 2: frame.block(bytes(data[position:position + size])); position += size
            else: raise ZstdError('Reserved zstd block type')
            if last: break
        if descriptor & 4: position += 4
        if expected is not None and expected != len(frame.out): raise ZstdError('zstd content size mismatch')
        result += frame.out
    return bytes(result)
