# 项目接入与依据

## 论文与实现边界

阅读 [Darvish 等 MATTERIX 论文](https://doi.org/10.1038/s43588-025-00924-4) 与任务相关的正文、Methods 和图示：资产/环境构建与 Fig. 3 涉及可复用 USD 及嵌套多对象工作站；Manipulation and perception skills 与 Fig. 4 涉及 primitive、组合技能和工作流；Integrated physics and semantics engine 涉及物理与语义共同驱动事件和过程。若实现依赖补充细节，读取实际补充材料；未取得时说明边界。

论文提供框架依据，不能作为当前 checkout 已实现某动作的证据。CAD 配合重建、质量分配、螺纹/卡扣代理、控制器和具体液体门控是资产工程选择，应分别说明依据。优先复用现有实现而非另造资产或状态机框架。

## 先读当前消费方

以下是上游风格的搜索线索，路径和 API 可能随版本变化，使用前在目标仓库定位：

| 目的 | 查找线索 |
|---|---|
| 资产基类与 spawn 覆盖 | `MatterixStaticObjectCfg`、`MatterixRigidObjectCfg`、`MatterixArticulationCfg` |
| 分类与导出 | `matterix_assets/{infrastructure,labware,equipment,robots}` 及 `__init__.py` |
| 帧与抓放接口 | `PickObjectCfg`、`PlaceObjectCfg`、`MoveToFrameCfg` 及实际 primitive 实现 |
| 动作/语义/生命周期 | `action_terms`、`event_terms`、semantics manager 和 scene reset/update |
| 场景与任务入口 | scene config、任务注册、workflow loader、诊断脚本及 `--help` |
| 大文件与路径 | 资产包常量、Git LFS、子模块边界与资源许可 |

例如可用 `rg -n 'class Matterix.*Cfg|class PickObjectCfg|class MoveToFrameCfg' source` 查入口，再读定义、直接调用者和同类配置。不要把本机私有目录或某一版 Isaac Lab 的四元数顺序写成永久 API。

## 完成接入

1. 选择匹配物理用途的 cfg。资产路径由项目常量或包资源解析；用户指定派生目录优先，移动后仍可使用。
2. 提供分类导出和 scene 对象键，按需注册动作/语义/回调。组合工作站可以使用现有风格组装函数，同时加入机构、独立耗材和固定操作目标。
3. 查清 frame 消费语义：`post_grasp` 字段存在不等于动作会读取它，某些组合动作使用自己的相对抬升参数。关节设备帧跟踪实际 link，测量运动前后世界帧。配置质量字段可能只用于语义，核对真实 spawn 和 PhysX。
4. 维护唯一 authoritative 的运动体/耗材/目标注册表，避免同一源几何既作为机构子体又生成独立对象；固定语义目标映射父体但不重复物理质量。
5. 使用正常环境生命周期更新/重置；测试停止/启动、重复初始化、销毁和选择性 reset，防止重复回调和跨环境污染。
6. 给出实际运行过的加载/操作命令与依赖版本，确认默认入口指向交付文件。任务要求工作流时注册相关任务/动作并运行，不要求用户补核心回调。

目标环境有界运行至少量测最终尺寸/方向、物体/关节、操作帧及所声明语义；有独立状态时测试至少两个环境。纯静态对象的状态隔离测试可说明不适用。独立 Isaac Sim 夹具、配置 import 和目标 Matterix 环境分别验收。

## 用户窗口

使用可用 MCP 时先只读确认实际 stage、入口和层状态。端口监听或窗口存在不足以证明连接。保留未保存编辑，再决定更新窗口；磁盘保存不代表窗口已重载。

无法连接时在私有进程/复制场景继续有界验证，报告窗口尚未更新。USD 脚本节点的扩展和信任设置保持目标工具的正常机制，不通过 skill 绕过。
