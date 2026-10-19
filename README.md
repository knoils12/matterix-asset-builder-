# Matterix Asset Builder

供 AI 编程助手使用的通用资产制作 skill：将 CAD、网格、URDF/MJCF 或已有 USD 制作、修复并接入 Matterix。覆盖静态设施、自由器皿、关节设备与组合工作站，按用途选择步骤。

这是资产工程流程与验证方法，不是能够从任意外形自动恢复真实机构和动力学参数的转换器。它要求读取目标项目的当前源码，不绑定某台移液站、个人路径或固定版本的控制参数；这是社区整理的独立项目。

## 使用

将本仓库作为名为 `matterix-asset-builder` 的 skill 文件夹，放入 AI 工具支持的技能目录。仓库根目录的 [SKILL.md](SKILL.md) 是入口。对使用 `~/.codex/skills` 的安装，且目标目录尚不存在时：

```bash
git clone https://github.com/knoils12/matterix-asset-builder-.git \
  ~/.codex/skills/matterix-asset-builder
```

已有同名 skill 时先保留原版本，再替换；不要覆盖其他工具的配置。仓库名末尾的 `-` 是当前 GitHub 地址的一部分，skill 名称本身没有尾部 `-`。

在支持技能调用的助手中提供输入路径、Matterix 仓库和目标能力，例如：

```text
使用 $matterix-asset-builder，将这套 STEP 装配制作成可在当前 Matterix 中
控制的设备。保留源文件，输出到独立目录；要求滑台运动和夹爪取放。
请完成质量/惯量依据、关节/驱动、碰撞、操作帧、配置接入和有界运行验证。
```

也可用于已有资产修复或打包，无需每次重建全部内容：

```text
使用 $matterix-asset-builder，检查这个 USD 中自由耗材的支撑和抓取。
保留非目标关节，按实测结果修复，并报告默认静置与目标动作的验证范围。
```

助手还需能够读取目标源码/文件，并具备所需转换器、OpenUSD 或 Isaac Sim/Matterix 环境。文档本身不安装厂商 CAD 插件，不授予远程发布权限，也不替代实机测量。

## 包含内容

| 文件 | 用途 |
|---|---|
| [SKILL.md](SKILL.md) | 任务范围、流程路由与完成条件 |
| [转换路线](references/conversion-routes.md) | CAD/网格/机器人描述导入、GUI 与版本适配 |
| [几何与来源](references/geometry-and-source.md) | 实例身份、单位、显隐、外壳、拆分/合并 |
| [物理与机构](references/physics-and-mechanisms.md) | 运动归属、质量惯量、关节驱动、碰撞与支撑 |
| [操作与语义](references/operations-and-semantics.md) | 自由取放、旋盖、安装、注射器与体积守恒 |
| [Matterix 接入](references/matterix-integration.md) | 配置、帧消费方、回调、语义和多环境 |
| [验证与打包](references/validation-and-packaging.md) | 分级证据、inactive 定义、USD 合并和依赖闭包 |
| [验收记录模板](assets/acceptance-template.md) | 中文零件/关节功能、参数依据及测量记录 |
| [只读 USD 检查](scripts/inspect_usd.py) | 组合依赖、物理节点清单和部分静态不变量 |

## 只读检查脚本

使用能够 `from pxr import Usd` 的 Python；目标 Isaac Sim Python 或独立 OpenUSD Python 均可。脚本不依赖 Matterix，默认加载当前选择的 payload；不会修改 USD，也不执行 ScriptNode。

```bash
python scripts/inspect_usd.py /path/to/asset.usda --output /path/to/new-report.json
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

报告文件必须是新路径，避免覆盖已有证据。退出码 `0` 表示本脚本未发现所检查的错误，`1` 表示发现错误，`2` 表示检查/输出失败；warnings 需人工按用途判断。输出包含单位、defaultPrim、layers/assets/unresolved、刚体、碰撞、关节与非激活 prim。

检查范围有限：不会验证几何正确性、质量充分性、支撑、碰撞 cooking、完整运动学、未选 variant、inactive 父级下未组合的后代或实例代理内部。返回 `no_detected_errors` 不代表资产已通过物理或 Matterix 验收。

## 验证状态

2026-10-19，OpenUSD Python `0.26.8`：

- skill frontmatter/命名结构校验通过。
- 7 个自动化测试通过，包含静态支架、自由器皿、滑台/非激活连接三类合成资产，以及缺失依赖、错误关节目标、无效惯量、报告防覆盖。
- 本地相对文档链接、Python 语法、发布内容与个人路径检查通过。
- [行为评估案例](tests/skill-cases.md) 提供后续独立 AI 评估输入；当前未执行独立模型行为评测。

这些测试验证 skill 结构和辅助脚本，不构成跨真实资产的端到端转换或 PhysX/Matterix 工作流认证。运行时工具兼容性以使用者实际版本为准。

## 依据与来源

- [MATTERIX 论文，DOI: 10.1038/s43588-025-00924-4](https://doi.org/10.1038/s43588-025-00924-4)：资产/环境构建、Fig. 3–4、Methods、物理与语义引擎；本 skill 是工程方法整理，不将新增修复归为论文原始实现。
- [Matterix 上游](https://github.com/AccelerationConsortium/Matterix)：本次同时核对实际工作区的配置基类、器皿示例与 PickObject 消费方。使用其他 checkout 时重新定位和核对。
- [Isaac Sim 模型转 USD 流程分享](https://chatgpt.com/share/6ad5e615-265c-83ee-bc84-893b55df34ec?no_universal_links=1)：依据用户提供的完整正文整理转换、Link/Joint/Drive、检查工具及分层方法，未复制整篇教程或其中图片。
- 本项目资产制作会话中的实际问题：支撑/穿透、运动归属、自由耗材、连接完整性、语义容器、液体守恒、合并时丢失非激活连接。仅提炼通用决策和验证要求，不发布源 CAD、私人会话日志或设备专用参数。
- 核对的 NVIDIA 参考：[物理基础](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/physics/simulation_fundamentals.html)、[关节教程](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/robot_setup_tutorials/tutorial_gui_simple_robot.html)、[资产检查](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/openusd_tuning_tutorials/tutorial_02_inspect_asset.html)、[Robot Schema](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/omniverse_usd/robot_schema.html)。它们是版本参考，不是 skill 的固定运行依赖。

## 许可

本仓库新编写的 skill、脚本和模板采用 [MIT License](LICENSE)。外部论文、文档、软件与用户资产保留各自许可；本仓库不重新授权它们。
