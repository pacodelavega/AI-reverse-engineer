#!/usr/bin/env python3
"""Zero-token DEX string pool extractor. Reads string table directly in <100ms."""
import glob
import struct
import sys

def extract_dex_strings(dex_path: str) -> list[str]:
    with open(dex_path, "rb") as f:
        data = f.read()
    if data[:4] != b"dex\n":
        return []

    string_ids_size, string_ids_off = struct.unpack("<II", data[56:64])
    strings = []
    for i in range(string_ids_size):
        off = struct.unpack("<I", data[string_ids_off + i*4 : string_ids_off + (i+1)*4])[0]
        # ULEB128 string length
        length, shift, idx = 0, 0, off
        while True:
            b = data[idx]
            idx += 1
            length |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                break
            shift += 7
        try:
            strings.append(data[idx:idx+length].decode("utf-8", errors="ignore"))
        except Exception:
            pass
    return strings

if __name__ == "__main__":
    targets = sys.argv[1:] or glob.glob("classes*.dex")
    for target in targets:
        strs = extract_dex_strings(target)
        print(f"[{target}] Extracted {len(strs)} strings")
