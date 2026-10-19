# 配方构建与便携打包

这些脚本是本 skill 新增的工程辅助工具，承接 MATTERIX 的可复用资产、操作帧与物理/语义分层思路；不属于论文报告的原始工具。无需启动 Isaac Sim 即可写入 OpenUSD 通用物理属性。使用支持 `from pxr import Usd, UsdPhysics, UsdUtils` 的 Python；当前测试环境为 Python 3.12、OpenUSD 0.26.8。脚本只用标准库和 OpenUSD，不自动安装依赖。

## 输入与输出

先通过目标环境实际支持的转换器得到几何 USD，再逐项核对零件身份与运动归属。不要把转换后的装配树直接当运动链。构建器不读取 SolidWorks 配合，不推测质量、密度、关节或控制器，也不移动源零件。

准备一个工作目录，例如：

```text
work/
├── geometry/
│   └── model.usda
├── recipe.json
└── controller.py          # 如有运行脚本
```

复制 [教学配方](../assets/build-recipe.json) 到 `work/recipe.json`，按真实 USD 路径与参数依据修改。示例要求源几何中存在 `/Asset/Base/Collider` 与 `/Asset/Slider/Collider`，并由相应 Link 持有；`Collider` 应为 Cube 等受支持的几何节点。模板没有配套实机模型，全部参数为演示估算，不可据此声称完成标定。

源资产须已正确规范为米、千克、Z-up。几何、刚体尺度和世界位姿仍需人工/项目检查；仅修改 stage 元数据不能完成单位换算。构建器要求顶层资产根，拒绝实例代理编辑和嵌套刚体。需要特殊 USD 组合或物理后端时，使用设备专用构建器。

## 构建

在 skill 根目录执行，替换实际路径：

```bash
python -B scripts/build_asset.py \
  --recipe /path/to/work/recipe.json \
  --output /path/to/work/built
```

`built` 必须尚不存在。成功后得到：

| 文件 | 内容 |
|---|---|
| `built/asset.usda` | 推荐入口；相对引用物理层与源几何 |
| `built/physics.usda` | 新增刚体、碰撞、材质、关节驱动与帧 |
| `built/build.json` | 完整配方、输入哈希、OpenUSD 版本和静态检查 warnings |

原几何不会复制到 `built`，不能只发送这三个文件。依赖不完整或配方无效时不发布输出目录；已有输出不覆盖。后续编辑需要管理版本并重新验证，`build.json` 只记录本次构建时的输入。

## 配方字段

JSON 顶层 `schema_version=1`、`geometry`、`default_prim` 必填；其余集合可省略。`geometry` 相对配方文件解析；`default_prim` 为已有顶层节点，如 `/Asset`。新增节点须在此根内且尚不存在；已有刚体/碰撞属性可被配方覆盖，务必保留基线。

| 字段 | 必需内容及约定 |
|---|---|
| `bodies` | 已有 `path`、正数 `mass_kg`；可选 `center_of_mass_m`、`diagonal_inertia_kg_m2`、`principal_axes_xyzw`、`kinematic`（默认 false） |
| `materials` | 新 `path`、非负 `static_friction` / `dynamic_friction`、`restitution`（0–1） |
| `colliders` | 已有几何 `path`；Mesh 必须指定 `approximation`；可选物理 `material` 路径 |
| `joints` | 新 `path`、`type`、`body0` / `body1`、两侧 `local_pos0_m` / `local_pos1_m`、`local_rot0_xyzw` / `local_rot1_xyzw` |
| `frames` | 新 `path`、`position_m`、`orientation_xyzw`；父节点必须已存在 |
| `articulation_root` | 可选已有节点路径；必须按目标后端的实际拓扑选取 |
| `sources` / 各项 `source` | 参数、装配关系的依据说明，写入构建记录；不会自动核验真伪 |

所有四元数均为归一化 **xyzw**；不是某些控制接口使用的 wxyz。位置/质心以所属父级或刚体局部坐标表示；关节 world 一侧的锚点是世界坐标。惯量是质心处的主惯量，主轴相对刚体局部系；CAD 完整张量须先正确变换和分解，不能直接丢弃非对角项。未提供惯量时保留源设置或后端推算行为，不代表惯量已确认。

关节类型支持 `fixed`、`prismatic`、`revolute`。至少一侧指向已存在的刚体；另一侧 `null` 表示 world。移动/旋转关节还必须提供局部 `axis`（X/Y/Z）与有限、有序的 `limits`。固定关节不可填写限位和驱动。`active: false` 可保留非激活的可拆连接定义，启闭逻辑需另行实现。

可选 `drive` 必填 `type`（`force` 或 `acceleration`）、`stiffness`、`damping`、`max_force`、`target_position`；`target_velocity` 默认为 0。参数按 OpenUSD Drive 原义写入，不自动调参或换算增益。

- Prismatic：位置/行程 m，速度 m/s；force 模式的最大力为 N。
- Revolute：位置/行程 **度**，速度 **度/s**；force 模式最大力矩为 N·m。控制器接口若使用弧度，须在边界转换。
- acceleration 模式、驱动增益及最大输出的具体解释须核对目标后端；不要混用不同模式的数值。

Mesh 近似仅支持 `none`、`convexHull`、`convexDecomposition`；普通动态刚体拒绝 `none`。Cube/Sphere/Capsule/Cylinder/Cone 使用已有 primitive，不接受 Mesh approximation。脚本不生成避让外形或代理几何，不保证凸分解保留孔洞；SDF 与 PhysX 专有设置交给目标环境专用流程。几何碰撞可写入不等于后端已经 cooking 成功。

## 检查和打包

```bash
python -B scripts/inspect_usd.py /path/to/work/built/asset.usda \
  --output /path/to/work/static-report.json

python -B scripts/package_asset.py \
  --root /path/to/work \
  --entry built/asset.usda \
  --include built/build.json \
  --include controller.py \
  --include static-report.json \
  --output /path/to/delivery.zip
```

没有某个附加文件时删除对应 `--include`。该参数可重复，仅接受包根内的普通文件；目录需逐文件列出。入口和所有 USD 依赖必须位于 `--root` 内，资产引用必须为可解析的本地相对路径。根目录可以包含原 CAD 或私人文档，脚本只收集 USD 依赖与显式附加文件；发布前仍需检查清单和来源许可。

打包器拒绝已有输出、缺失依赖、越界文件、符号链接、绝对资产引用、远程 URI 和模板路径（例如 UDIM）。先将系统 MDL/纹理等资源依法整理为包内相对资源；它不会下载资源、改写引用或自动解决这些情形。某些依赖系统不能由通用 USD 遍历完整识别，必须另行收集并测试。

输出为保留分层的 ZIP，包含 `bundle_manifest.json`：入口、逐文件 SHA-256、检查范围及 warnings。打包会在临时搬迁目录重新打开入口并检查 ZIP CRC；不会 Flatten，不会丢弃原层中的 inactive 定义。ZIP 解压后打开清单指定的入口。

Python 导入、配置读取、MDL 内部引用、ScriptNode 和控制器的动态资源不一定是 USD asset path；必须用 `--include` 显式提供，并在接收环境测试。脚本不执行这些资源，也不验证 Python 代码。分层依赖和源 USD 本身可能含私有信息，发布前需审查。

## 完成范围

两脚本退出码：`0` 成功，`2` 输入、写入或检查失败。构建记录标为 `authored_not_simulated`；打包记录标为 `dependency_copy_and_partial_static_inspection`。它们不提供 PhysX 静置/抓取/全行程证明，不创建 Matterix 配置、语义容器、液体系统、控制回调或环境注册。

继续按 [项目接入](matterix-integration.md) 和 [验证要求](validation-and-packaging.md) 完成所要求的操作与目标环境测试。静态报告无错误只能证明已检查的不变量，不代表“可直接使用”或实机参数已标定。
