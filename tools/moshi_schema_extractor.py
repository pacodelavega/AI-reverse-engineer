#!/usr/bin/env python3
"""Extracts Moshi JsonReader.Options field schemas directly from Dalvik bytecode."""
import glob
import json
import struct
import sys

def extract_moshi_schemas(dex_path: str) -> dict[str, list[str]]:
    with open(dex_path, "rb") as f:
        data = f.read()
    if data[:4] != b"dex\n":
        return {}

    string_ids_size, string_ids_off = struct.unpack("<II", data[56:64])
    strings = []
    for i in range(string_ids_size):
        off = struct.unpack("<I", data[string_ids_off + i*4 : string_ids_off + i*4 + 4])[0]
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
            strings.append("")

    type_ids_size, type_ids_off = struct.unpack("<II", data[64:72])
    types = [strings[struct.unpack("<I", data[type_ids_off + i*4 : type_ids_off + i*4 + 4])[0]] for i in range(type_ids_size)]

    def read_uleb128(idx):
        res, shift = 0, 0
        while True:
            b = data[idx]
            idx += 1
            res |= (b & 0x7F) << shift
            if (b & 0x80) == 0:
                break
            shift += 7
        return res, idx

    class_defs_size, class_defs_off = struct.unpack("<II", data[96:104])
    schemas = {}
    for i in range(class_defs_size):
        entry = data[class_defs_off + i*32 : class_defs_off + (i+1)*32]
        class_idx, _, _, _, _, _, class_data_off, _ = struct.unpack("<IIIIIIII", entry)
        cname = types[class_idx]
        if "JsonAdapter" in cname and class_data_off > 0:
            idx = class_data_off
            sf, idx = read_uleb128(idx)
            inf, idx = read_uleb128(idx)
            dm, idx = read_uleb128(idx)
            vm, idx = read_uleb128(idx)
            for _ in range(sf * 2 + inf * 2):
                _, idx = read_uleb128(idx)
            fields = []
            for m_count in (dm, vm):
                last_m = 0
                for _ in range(m_count):
                    diff, idx = read_uleb128(idx)
                    last_m += diff
                    flags, idx = read_uleb128(idx)
                    code_off, idx = read_uleb128(idx)
                    if code_off > 0 and code_off + 16 <= len(data):
                        _, _, _, _, _, insns_size = struct.unpack("<HHHHII", data[code_off:code_off+16])
                        insns = data[code_off+16 : code_off+16+insns_size*2]
                        pos = 0
                        while pos < len(insns) - 1:
                            op = insns[pos]
                            if op == 0x1A and pos + 4 <= len(insns):
                                s_idx = struct.unpack("<H", insns[pos+2:pos+4])[0]
                                if s_idx < len(strings):
                                    s = strings[s_idx]
                                    if len(s) > 1 and not s.startswith("(") and not s.startswith("L") and s not in ("moshi", "reader", "writer"):
                                        fields.append(s)
                                pos += 4
                            else:
                                pos += 2
            if fields:
                schemas[cname] = sorted(set(fields))
    return schemas

if __name__ == "__main__":
    dex = sys.argv[1] if len(sys.argv) > 1 else "classes.dex"
    print(json.dumps(extract_moshi_schemas(dex), indent=2, ensure_ascii=False))
