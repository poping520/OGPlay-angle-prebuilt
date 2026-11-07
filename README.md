# OGPlay ANGLE Prebuilt SDK

此仓库只保存 OGPlay 使用的可重定位 ANGLE 二进制 SDK。普通开发者通过 OGPlay 的
`third_party/angle-prebuilt` 浅 submodule 获取，不需要同步或编译完整 ANGLE 源码树。

各平台共用仓库根目录的 `include/` 和 `licenses/`。Windows SDK 专用许可证也位于
`licenses/`。平台目录按 `<platform>-<cpu>/<configuration>` 划分，包含链接库、运行时
文件和平台清单。平台清单记录 ANGLE commit、GN 参数、运行时文件和逐文件 SHA-256。
`include/manifest.json` 和 `licenses/manifest.json` 分别校验公共头文件和许可证。
默认 Release ANGLE 同时服务 OGPlay 的 Debug/Release 构建。

包只能由本仓库的 `tools/build_angle.py` 和 `tools/package_angle_sdk.py` 生成与验证，不要
直接修改二进制或清单。维护者可把固定 ANGLE checkout 放在本地 `angle/`，原始归档放在
`angle.zip`；两者均由 `.gitignore` 排除，不会进入远端仓库。具体流程见
[`tools/README.md`](tools/README.md)。
