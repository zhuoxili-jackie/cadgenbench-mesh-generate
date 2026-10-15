# v1.0.0 状态

原扫描生成 goal 已完成，174/174 正式案例通过全量独立验收与交付一致性检查；不是旧的 140 例预览快照。32 源件结论：24 native、5 官方 Mesh 近似、3 排除；排除源件 202/217/240 有多入口、跨内核与替代网格调查证据。

当前物理采样版本 physical_scan_v2_overlap_density；重建实现 r4_continuous_free_space。默认每次放置 hard/medium/easy 为 49/97/193 帧；一个经过重叠调查的源件统一加密至 193/385/769 帧，质量门槛、噪声及重建未改变。全部案例带 sampling_contract.json。

21 项必需报告全部通过，当前版本从 STEP 独立重做一例，3,973,942 个真实返回数组、Mesh 顶点及连接严格一致；公开单例无 GT 重建和真实中断恢复均通过。发布完整性核查另见 collaboration_verification.json。验收为声明容差下的工程抽样，不是全局 Hausdorff 或 CAD 参数/布尔运算保证。

没有执行新数据 repair、SCA、Harbor、RSI 或端到端建模。当前 Repair 仓库独立保留。GitHub 的历史 preview 标签继续保留，正式 174 例使用本版本。
