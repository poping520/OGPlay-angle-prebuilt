"""Regression checks for private Android runtime symbol rejection."""

from pathlib import Path
import struct
import tempfile
import unittest

from android_exports import dynamic_exports, verify_android_exports


def make_android_elf(exports: list[str], imports: tuple[str, ...] = ()) -> bytes:
    strings = bytearray(b"\0")
    symbols = bytearray(24)  # ELF null symbol
    for name in [*exports, *imports]:
        symbols.extend(struct.pack("<IBBHQQ", len(strings), 0x12, 0,
                                   0 if name in imports else 1, 0, 0))
        strings.extend(name.encode("ascii") + b"\0")
    header = bytearray(64)
    header[:6] = b"\x7fELF\x02\x01"
    struct.pack_into("<HHI", header, 16, 3, 183, 1)
    struct.pack_into("<Q", header, 40, 64)
    struct.pack_into("<HH", header, 58, 64, 3)
    table_offset = 64 + 3 * 64
    sections = bytearray(64)
    sections.extend(struct.pack("<IIQQQQIIQQ", 0, 3, 0, 0,
                                table_offset, len(strings), 0, 0, 1, 0))
    sections.extend(struct.pack("<IIQQQQIIQQ", 0, 11, 0, 0,
                                table_offset + len(strings), len(symbols), 1, 1, 8, 24))
    return bytes(header + sections + strings + symbols)


class AndroidExportsTest(unittest.TestCase):
    def test_runtime_exports_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libEGL_angle.so"
            api = ["eglGetProcAddress", "eglInitialize", "eglCreateContext"]
            for symbol in ("_Unwind_RaiseException", "unw_get_proc_info",
                           "__register_frame", "_Znwm", "__emutls_get_address"):
                with self.subTest(symbol=symbol):
                    path.write_bytes(make_android_elf([*api, symbol]))
                    with self.assertRaisesRegex(RuntimeError, "exports private symbols"):
                        verify_android_exports(path)

    def test_undefined_runtime_imports_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libEGL_angle.so"
            api = ["eglGetProcAddress", "eglInitialize", "eglCreateContext"]
            path.write_bytes(make_android_elf(api, ("_Unwind_Resume",)))
            verify_android_exports(path)
            self.assertEqual(dynamic_exports(path), set(api))

    def test_missing_api_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libGLESv2_angle.so"
            path.write_bytes(make_android_elf(["glDrawArrays"]))
            with self.assertRaisesRegex(RuntimeError, "missing required exports"):
                verify_android_exports(path)

    def test_truncated_elf_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "libEGL_angle.so"
            path.write_bytes(make_android_elf(["eglGetProcAddress"])[:-1])
            with self.assertRaisesRegex(RuntimeError, "cannot inspect Android ELF"):
                verify_android_exports(path)


if __name__ == "__main__":
    unittest.main()
