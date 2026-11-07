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

公共头文件和许可证与平台二进制分开打包，各平台共用 `include/` 和 `licenses/`。

`package-headers` 从 ANGLE 源码生成仓库级（或暂存）头文件目录，默认目标为仓库根
`include/`。

`package-licenses` 从 ANGLE 源码生成公共许可证目录，默认目标为仓库根 `licenses/`。
发布 Windows SDK 时用 `--windows-sdk-license` 加入微软 SDK 许可证。

`package` 把已验证产物转换为
`.local/angle-sdk/<platform>-<cpu>/<release|debug>`。平台包只保留链接库、运行时文件、
逐文件 SHA-256 清单，默认不携带 PDB，可用 `--include-symbols` 生成调试包。打包和复验时
会校验平台目录旁的公共 `licenses/` 及其 ANGLE commit。

```text
python tools/package_angle_sdk.py package-headers
python tools/package_angle_sdk.py package-licenses \
  --licenses .local/angle-sdk/licenses \
  --windows-sdk-license <absolute-sdk-license.rtf>
python tools/package_angle_sdk.py package
python tools/package_angle_sdk.py verify-headers
python tools/package_angle_sdk.py verify \
  --sdk .local/angle-sdk/windows-x64/release
```

每条打包命令生成的目标目录必须不存在。复验后，将对应平台目录和暂存的公共许可证发布到仓库
根目录。公共头直接维护在根目录 `include/`。源码、原始归档、depot_tools、GN 输出和临时包
均禁止提交。

## 自测

```text
python tools/build_angle.py --self-test
python tools/package_angle_sdk.py --self-test
python tools/package_angle_sdk.py verify-headers
python tools/package_angle_sdk.py verify-licenses
python tools/package_angle_sdk.py verify --sdk linux-x64/release
python tools/package_angle_sdk.py verify --sdk windows-x64/release
python tools/package_angle_sdk.py verify --sdk macos-arm64/release
python tools/package_angle_sdk.py verify --sdk macos-x64/release
```
