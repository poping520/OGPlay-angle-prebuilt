"""Inspect Android ELF exports without depending on a host readelf installation."""

from pathlib import Path
import re
import struct


def dynamic_exports(path: Path) -> set[str]:
    data = path.read_bytes()
    try:
        if data[:6] != b"\x7fELF\x02\x01":
            raise ValueError("expected a little-endian ELF64 library")
        section_offset = struct.unpack_from("<Q", data, 40)[0]
        section_size, section_count = struct.unpack_from("<HH", data, 58)
        if section_size != 64 or not section_count:
            raise ValueError("missing ELF section table")
        sections = [struct.unpack_from("<IIQQQQIIQQ", data, section_offset + i * 64)
                    for i in range(section_count)]
        symbols: set[str] = set()
        found = False
        for section in sections:
            if section[1] != 11:  # SHT_DYNSYM
                continue
            found = True
            strings = sections[section[6]]
            strings_start, strings_size = strings[4:6]
            table = data[strings_start:strings_start + strings_size]
            offset, size, entry_size = section[4], section[5], section[9]
            if (entry_size != 24 or size % entry_size
                    or offset + size > len(data) or len(table) != strings_size):
                raise ValueError("invalid ELF dynamic symbol table")
            for pos in range(offset, offset + size, entry_size):
                name, info, other, index, _, _ = struct.unpack_from("<IBBHQQ", data, pos)
                if index == 0 or info >> 4 not in (1, 2, 10) or other & 3 not in (0, 3):
                    continue  # undefined, local or hidden
                end = table.find(b"\0", name)
                if end < 0:
                    raise ValueError("invalid ELF symbol name")
                symbols.add(table[name:end].decode("ascii"))
        if not found:
            raise ValueError("missing ELF dynamic symbol table")
        return symbols
    except (ValueError, IndexError, struct.error, UnicodeError) as error:
        raise RuntimeError(f"cannot inspect Android ELF exports at {path}: {error}") from error


def verify_android_exports(path: Path) -> None:
    exports = dynamic_exports(path)
    if path.name == "libEGL_angle.so":
        pattern = r"egl[A-Z].*"
        required = {"eglGetProcAddress", "eglInitialize", "eglCreateContext"}
    elif path.name == "libGLESv2_angle.so":
        pattern = r"gl[A-Z].*|EGL_.*|ANGLEGetDisplayPlatform|ANGLEResetDisplayPlatform"
        required = {"glGetString", "glDrawArrays", "EGL_GetProcAddress",
                    "ANGLEGetDisplayPlatform", "ANGLEResetDisplayPlatform"}
    else:
        raise RuntimeError(f"unexpected Android library: {path.name}")
    unexpected = sorted(name for name in exports if not re.fullmatch(pattern, name))
    if unexpected:
        raise RuntimeError(f"Android library exports private symbols: {path}: {', '.join(unexpected)}")
    if required - exports:
        raise RuntimeError(f"Android library is missing required exports: {path}: {sorted(required - exports)}")
