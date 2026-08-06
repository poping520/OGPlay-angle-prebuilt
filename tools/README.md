# ANGLE SDK 维护工具

## 构建

`build_angle.py` 校验本地 `angle/` checkout 与脚本固定 commit 一致，使用官方
depot_tools/gclient/GN/Ninja 生成 `libEGL` 与 `libGLESv2`。Windows 固定 MSVC 及其原生
标准库，Linux/macOS 使用 Clang；`--source` 可指定其他本地源码目录，但不会放宽 commit
校验。

```text
python tools/build_angle.py all --depot-tools <absolute-depot-tools-path>
python tools/build_angle.py verify
```

`sync`、`configure`、`build`、`verify` 可分别用于增量维护；`print-config` 输出固定 GN 参数。
默认产物位于 `angle/out/ogplay`，验证后写入包含源码 commit、平台、CPU、配置、GN 参数和
核心产物的 `ogplay-angle-manifest.json`。

## 打包

公共头文件与平台二进制分开打包，避免各平台重复存放相同 `include/`。

`package-headers` 从 ANGLE 源码生成仓库级（或暂存）头文件目录，默认目标为仓库根
`include/`。

`package` 把已验证产物转换为
`.local/angle-sdk/<platform>-<cpu>/<release|debug>`。平台包只保留链接库、运行时文件、
许可证和逐文件 SHA-256 清单，**不含** `include/`；默认不携带 PDB，可用
`--include-symbols` 生成调试包。

```text
python tools/package_angle_sdk.py package-headers
python tools/package_angle_sdk.py package \
  --windows-sdk-license <absolute-sdk-license.rtf>
python tools/package_angle_sdk.py verify-headers
python tools/package_angle_sdk.py verify \
  --sdk .local/angle-sdk/windows-x64/release
```

目标目录必须不存在，避免旧文件混入新包。复验后再把对应平台目录更新到仓库根目录；公共头
直接维护在根目录 `include/`。源码、原始归档、depot_tools、GN 输出和临时包均禁止提交。

## 自测

```text
python tools/build_angle.py --self-test
python tools/package_angle_sdk.py --self-test
python tools/package_angle_sdk.py verify-headers
python tools/package_angle_sdk.py verify --sdk windows-x64/release
python tools/package_angle_sdk.py verify --sdk macos-arm64/release
python tools/package_angle_sdk.py verify --sdk macos-x64/release
```
