# 转换与工具路线

## 按输入选择，按目标版本核实

| 输入 | 优先考虑 | 需要验证 |
|---|---|---|
| STEP/STP、IGES、SolidWorks 装配 | 当前环境提供的 CAD Converter/厂商导出 | 格式/许可、单位、occurrence、配置与抑制件；层级不等于配合 |
| STL/OBJ/FBX/glTF/GLB | 可用 Asset Converter，必要时 Blender 预处理 | STL 单位、OBJ/MTL 与纹理、多对象层级、法线和尺度 |
| URDF/MJCF | 目标版本对应 importer | link/joint/inertia、mesh 引用、固定基座、mimic/闭链与导入默认值 |
| Blender | Blender USD exporter | 对象选择、可见性、轴向、材质/纹理和变换 |
| 已有 USD | 保留 composition，增量修复派生层 | defaultPrim、variant/payload、物理层、资源和 runtime 依赖 |
| 仅照片/视频 | 用户需要时重建外观与尺度 | 遮挡、内部结构和物理参数不可由外观唯一确定，标明推断 |

CAD 转换器不可用时可考虑 FreeCAD 读 STEP、按共同装配系导出网格、Blender 整理后导出 USD。记录降级损失：材质、零件身份、曲面精度、配合及质量信息。不能假设转经 STL 后仍保留单位、装配树和材料。

转换质量按关键曲面、配合间隙和使用精度选择。跨运动体合并会丢失运动边界；过密 tessellation 会增加成本而不自动提高物理精度。保持可单独替换的几何阶段副本，后续物理覆盖尽量独立维护。

按 loose parts 拆分只识别拓扑连通性：可能拆散同一机械零件的多个实体，也可能无法分开粘连零件。依据源身份与运动用途核对拆分，信息已丢失时取得更好来源或按授权重建。

## GUI 与自动化的最短路径

AI 有可用 MCP/API/CLI 时优先使用并保留可复现构建；用户需要 GUI 教程时，按实际版本给可见步骤。先确认当前窗口及未保存编辑，测试场景使用私有副本。

1. 转换：核实当前 Extension Manager 中 CAD/asset/importer 扩展和支持格式，使用该版本真实的导入/转换入口，输出到派生目录。
2. 整理：检查 Stage 的 Xform、link、visual 与 collision；重新挂接前后比较世界变换。原点便于组织，物理轴心仍由 joint 局部锚点定义。
3. 物理：运动 link 设刚体，子级接触几何设 collider，配置质量、惯量和物理材质。避免对同一 link 的每个视觉网格都套“Rigid Body with Colliders”而创建额外刚体。
4. 关节：创建适当 Fixed/Revolute/Prismatic，读回 Body0/Body1、局部位置/旋转、轴与限位。位置/速度驱动还需 Drive 或实际控制器；力控制可以不使用位置 Drive。
5. 检查：使用目标版本支持的 collider/joint 可视化、Robot/Joint Inspector 与 Asset Validation。验证器辅助发现配置问题，仍需运行时动作测量。

可运行脚本路径和菜单可能迁移；先查当前安装和官方文档，不能把教程示例命令直接当成用户环境的已验证入口。

## Articulation 与 Robot Schema

固定机器人与自由基座选择真实基座约束；静态家具不用添加 articulation。符合后端要求的位置配置 ArticulationRoot，避免多个冲突 root、未处理闭链或多余世界固定约束。固定到世界时，一侧 Body 关系未绑定可表示世界；另一侧及世界/局部锚点仍须正确。

在目标版本和消费工具需要时检查 `IsaacRobotAPI`、`IsaacLinkAPI`、`IsaacJointAPI`、`IsaacSiteAPI`。Robot Schema 提供结构/工具识别，不能代替物理刚体、关节、articulation 或 Matterix 操作帧。当前版本不提供该 schema 时，不将它列为无条件完成门槛。

6.2 参考入口（使用其他版本时切换对应文档）：[机器人关节](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/robot_setup_tutorials/tutorial_gui_simple_robot.html)、[检查资产](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/openusd_tuning_tutorials/tutorial_02_inspect_asset.html)、[物理基础](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/physics/simulation_fundamentals.html)、[Robot Schema](https://docs.isaacsim.omniverse.nvidia.com/6.2.0/omniverse_usd/robot_schema.html)。[CAD Converter](https://docs.omniverse.nvidia.com/extensions/latest/ext_cad-converter.html) 的格式、插件和许可支持按实际版本另查；这些文档不绑定 skill 到单一发行版本。
