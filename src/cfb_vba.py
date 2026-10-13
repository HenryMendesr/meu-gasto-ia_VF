#!/usr/bin/env python3
import math
import struct
from pathlib import Path

FREE = 0xFFFFFFFF
END = 0xFFFFFFFE


class CFB:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        if self.data[:8] != bytes.fromhex("D0CF11E0A1B11AE1"):
            raise ValueError("not a CFB file")
        self.sector_size = 1 << struct.unpack_from("<H", self.data, 30)[0]
        self.mini_sector_size = 1 << struct.unpack_from("<H", self.data, 32)[0]
        self.first_dir = struct.unpack_from("<I", self.data, 48)[0]
        self.mini_cutoff = struct.unpack_from("<I", self.data, 56)[0]
        self.first_minifat = struct.unpack_from("<I", self.data, 60)[0]
        self.num_minifat = struct.unpack_from("<I", self.data, 64)[0]
        first_difat = struct.unpack_from("<I", self.data, 68)[0]
        num_difat = struct.unpack_from("<I", self.data, 72)[0]
        num_fat = struct.unpack_from("<I", self.data, 44)[0]
        difat = list(struct.unpack_from("<109I", self.data, 76))
        sid = first_difat
        for _ in range(num_difat):
            sec = self._sector(sid)
            vals = struct.unpack_from(f"<{self.sector_size // 4}I", sec)
            difat.extend(vals[:-1])
            sid = vals[-1]
        fat_sids = [x for x in difat if x != FREE][:num_fat]
        self.fat = []
        for fsid in fat_sids:
            self.fat.extend(struct.unpack_from(f"<{self.sector_size // 4}I", self._sector(fsid)))

        self.dir_chain = self._chain(self.first_dir, self.fat)
        self.dir_bytes = bytearray(self._read_chain(self.dir_chain))
        self.entries = []
        for off in range(0, len(self.dir_bytes), 128):
            raw = self.dir_bytes[off:off + 128]
            if len(raw) < 128:
                break
            name_len = struct.unpack_from("<H", raw, 64)[0]
            name = raw[:max(0, name_len - 2)].decode("utf-16le", "replace") if name_len >= 2 else ""
            self.entries.append({
                "index": off // 128,
                "name": name,
                "type": raw[66],
                "left": struct.unpack_from("<I", raw, 68)[0],
                "right": struct.unpack_from("<I", raw, 72)[0],
                "child": struct.unpack_from("<I", raw, 76)[0],
                "start": struct.unpack_from("<I", raw, 116)[0],
                "size": struct.unpack_from("<Q", raw, 120)[0],
            })

        root = self.entries[0]
        self.root_chain = self._chain(root["start"], self.fat)
        self.mini_stream = bytearray(self._read_chain(self.root_chain))[:root["size"]]
        self.minifat = []
        if self.num_minifat and self.first_minifat not in (FREE, END):
            mf_chain = self._chain(self.first_minifat, self.fat)[:self.num_minifat]
            mf_data = self._read_chain(mf_chain)
            self.minifat = list(struct.unpack_from(f"<{len(mf_data) // 4}I", mf_data))

    def _sector(self, sid):
        off = 512 + sid * self.sector_size
        return self.data[off:off + self.sector_size]

    def _chain(self, start, table):
        if start in (FREE, END):
            return []
        out, seen, sid = [], set(), start
        while sid not in (FREE, END):
            if sid in seen or sid >= len(table):
                raise ValueError("invalid or cyclic sector chain")
            seen.add(sid)
            out.append(sid)
            sid = table[sid]
        return out

    def _read_chain(self, chain):
        return b"".join(bytes(self._sector(s)) for s in chain)

    def stream(self, entry):
        size = entry["size"]
        if size < self.mini_cutoff:
            chain = self._chain(entry["start"], self.minifat)
            raw = b"".join(self.mini_stream[s * self.mini_sector_size:(s + 1) * self.mini_sector_size] for s in chain)
        else:
            chain = self._chain(entry["start"], self.fat)
            raw = self._read_chain(chain)
        return raw[:size]

    def replace_stream(self, entry, payload: bytes):
        old_size = entry["size"]
        if (old_size < self.mini_cutoff) != (len(payload) < self.mini_cutoff):
            raise ValueError("replacement crosses mini-stream cutoff")
        if old_size < self.mini_cutoff:
            chain = self._chain(entry["start"], self.minifat)
            capacity = len(chain) * self.mini_sector_size
            if len(payload) > capacity:
                raise ValueError(f"mini stream too large: {len(payload)} > {capacity}")
            padded = payload + b"\x00" * (capacity - len(payload))
            for i, sid in enumerate(chain):
                a = sid * self.mini_sector_size
                self.mini_stream[a:a + self.mini_sector_size] = padded[i * self.mini_sector_size:(i + 1) * self.mini_sector_size]
            root_padded = self.mini_stream + b"\x00" * (len(self.root_chain) * self.sector_size - len(self.mini_stream))
            for i, sid in enumerate(self.root_chain):
                off = 512 + sid * self.sector_size
                self.data[off:off + self.sector_size] = root_padded[i * self.sector_size:(i + 1) * self.sector_size]
        else:
            chain = self._chain(entry["start"], self.fat)
            capacity = len(chain) * self.sector_size
            if len(payload) > capacity:
                raise ValueError(f"stream too large: {len(payload)} > {capacity}")
            padded = payload + b"\x00" * (capacity - len(payload))
            for i, sid in enumerate(chain):
                off = 512 + sid * self.sector_size
                self.data[off:off + self.sector_size] = padded[i * self.sector_size:(i + 1) * self.sector_size]
        entry["size"] = len(payload)
        struct.pack_into("<Q", self.dir_bytes, entry["index"] * 128 + 120, len(payload))
        for i, sid in enumerate(self.dir_chain):
            off = 512 + sid * self.sector_size
            self.data[off:off + self.sector_size] = self.dir_bytes[i * self.sector_size:(i + 1) * self.sector_size]


def decompress_container(buf: bytes) -> bytes:
    if not buf or buf[0] != 1:
        raise ValueError("bad compressed-container signature")
    pos, out = 1, bytearray()
    while pos < len(buf):
        if pos + 2 > len(buf):
            raise ValueError("truncated chunk header")
        header = struct.unpack_from("<H", buf, pos)[0]
        chunk_size = (header & 0x0FFF) + 3
        signature = (header >> 12) & 7
        compressed = (header >> 15) & 1
        if signature != 3 or chunk_size < 3 or chunk_size > 4098 or pos + chunk_size > len(buf):
            raise ValueError("invalid chunk")
        chunk_end = pos + chunk_size
        pos += 2
        chunk = bytearray()
        if not compressed:
            if chunk_end - pos != 4096:
                raise ValueError("invalid raw chunk")
            chunk.extend(buf[pos:chunk_end])
            pos = chunk_end
        else:
            while pos < chunk_end and len(chunk) < 4096:
                flags = buf[pos]
                pos += 1
                for bit in range(8):
                    if pos >= chunk_end or len(chunk) >= 4096:
                        break
                    if not (flags & (1 << bit)):
                        chunk.append(buf[pos])
                        pos += 1
                    else:
                        if pos + 2 > chunk_end:
                            raise ValueError("truncated copy token")
                        token = struct.unpack_from("<H", buf, pos)[0]
                        pos += 2
                        cur = len(chunk)
                        offset_bits = max(4, (cur - 1).bit_length())
                        length_bits = 16 - offset_bits
                        length_mask = (1 << length_bits) - 1
                        length = (token & length_mask) + 3
                        offset = (token >> length_bits) + 1
                        if offset > cur:
                            raise ValueError("invalid copy offset")
                        for _ in range(length):
                            chunk.append(chunk[-offset])
                            if len(chunk) >= 4096:
                                break
            pos = chunk_end
        out.extend(chunk)
    return bytes(out)


def _best_match(block: bytes, pos: int):
    if pos == 0:
        return 0, 0
    offset_bits = max(4, (pos - 1).bit_length())
    length_bits = 16 - offset_bits
    max_len = min((1 << length_bits) + 2, len(block) - pos)
    max_off = min(1 << offset_bits, pos)
    best_len, best_off = 0, 0
    first = block[pos]
    for off in range(1, max_off + 1):
        if block[pos - off] != first:
            continue
        length = 1
        while length < max_len and block[pos + length - off] == block[pos + length]:
            length += 1
        if length >= 3 and length > best_len:
            best_len, best_off = length, off
            if length == max_len:
                break
    return best_len, best_off


def compress_container(raw: bytes) -> bytes:
    result = bytearray([1])
    for base in range(0, len(raw), 4096):
        block = raw[base:base + 4096]
        body = bytearray()
        pos = 0
        while pos < len(block):
            flag_index = len(body)
            body.append(0)
            flags = 0
            for bit in range(8):
                if pos >= len(block):
                    break
                length, offset = _best_match(block, pos)
                if length >= 3:
                    offset_bits = max(4, (pos - 1).bit_length())
                    length_bits = 16 - offset_bits
                    token = ((offset - 1) << length_bits) | (length - 3)
                    body.extend(struct.pack("<H", token))
                    flags |= 1 << bit
                    pos += length
                else:
                    body.append(block[pos])
                    pos += 1
            body[flag_index] = flags
        if len(body) + 2 < 4098:
            header = 0x8000 | 0x3000 | ((len(body) + 2) - 3)
            result.extend(struct.pack("<H", header))
            result.extend(body)
        else:
            if len(block) != 4096:
                raise ValueError("final incompressible block too large")
            result.extend(struct.pack("<H", 0x3FFF))
            result.extend(block)
    return bytes(result)


def find_source(stream: bytes):
    candidates = []
    for off, b in enumerate(stream):
        if b != 1:
            continue
        try:
            raw = decompress_container(stream[off:])
        except Exception:
            continue
        score = sum(x in raw for x in (b"Attribute VB_Name", b"Sub ", b"Function ", b"Option Explicit"))
        printable = sum(c in b"\r\n\t" or 32 <= c < 127 for c in raw[:min(len(raw), 2000)])
        if score and printable > min(len(raw), 2000) * 0.8:
            candidates.append((score, len(raw), off, raw))
    if not candidates:
        return None
    return max(candidates, key=lambda x: (x[0], x[1]))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("cfb")
    ap.add_argument("--dump", type=Path)
    ns = ap.parse_args()
    cfb = CFB(Path(ns.cfb).read_bytes())
    if ns.dump:
        ns.dump.mkdir(parents=True, exist_ok=True)
    for e in cfb.entries:
        if e["type"] != 2 or not e["name"]:
            continue
        s = cfb.stream(e)
        src = find_source(s)
        print(f'{e["index"]:3d} {e["size"]:7d} {e["name"]!r}', end="")
        if src:
            score, rawlen, off, raw = src
            print(f" source@{off} raw={rawlen} score={score}")
            if ns.dump:
                (ns.dump / (e["name"].replace("/", "_") + ".bas")).write_bytes(raw)
        else:
            print()
