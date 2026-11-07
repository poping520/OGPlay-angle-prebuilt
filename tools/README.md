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

## Android arm64

在 Linux 主机上构建 Android `arm64-v8a` 动态库，沿用脚本固定的 ANGLE commit。
按 [ANGLE 官方 Android 构建说明](https://chromium.googlesource.com/angle/angle/+/c24d9971269a878a221238a5923abdcc933fa2e9/doc/DevSetupAndroid.md)
使用 Chromium 配套 Clang、Android NDK 和 SDK，不依赖系统安装的 Android Studio。
`sync` 自动传入 `--deps=android`，下载该 commit 的 Android 依赖。
新增的本地工具请放在仓库 `.local/`（例如 `.local/depot_tools`），gclient 管理的
工具链依赖仍使用 ANGLE checkout 内的官方路径；这些目录都不会提交。
现有 `depot_tools/` 和已同步的 Android 依赖也可直接复用。

```sh
# 新环境需要 depot_tools；已有时跳过 clone，并使用实际路径。
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git .local/depot_tools
python3 tools/build_angle.py all --platform android --depot-tools .local/depot_tools --jobs 3

# 已同步依赖时，可分别执行 configure / build / verify。
python3 tools/build_angle.py verify --platform android
python3 tools/package_angle_sdk.py package-licenses --licenses .local/angle-sdk/licenses
python3 tools/package_angle_sdk.py package --build angle/out/ogplay-android-arm64
python3 tools/package_angle_sdk.py verify --sdk .local/angle-sdk/android-arm64/release
```

若暂存的公共许可证已存在，跳过 `package-licenses`，直接复验即可。
Android 默认 CPU 为 `arm64`，输出为 `angle/out/ogplay-android-arm64`，不会覆盖桌面
`out/ogplay`。当前只支持 Android arm64；默认 Release、Vulkan 后端、关闭 SwiftShader，
显式设置 `android_ndk_api_level=23` 和 `default_min_sdk_version=23`（Android 6）。
Vulkan 后端仍要求设备提供兼容的 Vulkan 驱动，API 23 编译不代表所有 Android 6 设备都能运行。
不设置 `--output` 时 Debug/Release 共用该 Android 构建目录，需要保留两者时分别指定输出。

平台包位于 `android-arm64/release/lib/`，包含 `libEGL_angle.so` 和 `libGLESv2_angle.so`（保留上游 Android 后缀以区别系统库）；
应用应把它们一起放入 APK 的 `lib/arm64-v8a/`（例如项目的 `jniLibs/arm64-v8a/`）。
Vulkan loader 由 Android 系统提供，不打包桌面 `libvulkan.so.1`。
公共头文件和许可证仍使用根目录 `include/`、`licenses/`；打包时会校验库为 arm64 ELF。
这是供应用链接/加载的原生库 SDK，构建目标为 `libEGL`、`libGLESv2`。

Android 构建脚本会自动、幂等地应用
[`patches/android-private-runtime.patch`](patches/android-private-runtime.patch)，并开启
`ogplay_android_hide_runtime_exports=true`。链接器使用 version script 仅导出 EGL/GLES
接口、`libEGL` 动态加载所需的 `EGL_*` 分发入口及两个 ANGLE 平台接口；同时使用
`--exclude-libs=libunwind.a`。其余符号（包括 `_Unwind_*`、`unw_*`、C++ 运行库）
保持库内可见，防止与宿主 NDK libc++ 的异常展开实现发生 ABI 冲突。参见
[NDK 官方 Unwinding 说明](https://android.googlesource.com/platform/ndk/+/master/docs/BuildSystemMaintainers.md#Unwinding)。
固定的上游 commit 不变，构建及 SDK 清单另记补丁路径和 SHA-256。

更新已有 Android 输出时，先执行 `configure`，再执行 `build` 和 `verify`。
构建验证、打包及 SDK 复验均检查 ELF 动态导出表，拒绝导出私有运行库符号或缺失
关键接口的库。主机校验不替代实机回归：集成后应使用宿主 NDK 的 `libc++_shared.so`
运行“抛异常＋析构清理”用例，并覆盖链接 ANGLE 及动态加载 ANGLE 的路径。

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
python tools/test_android_exports.py
python tools/package_angle_sdk.py verify-headers
python tools/package_angle_sdk.py verify-licenses
python tools/package_angle_sdk.py verify --sdk linux-x64/release
python tools/package_angle_sdk.py verify --sdk windows-x64/release
python tools/package_angle_sdk.py verify --sdk macos-arm64/release
python tools/package_angle_sdk.py verify --sdk macos-x64/release
python tools/package_angle_sdk.py verify --sdk android-arm64/release
```
