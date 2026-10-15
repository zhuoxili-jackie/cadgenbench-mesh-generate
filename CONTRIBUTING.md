# 协作入口

本仓库提供已完成的 Generate 实现和 174 例数据清单，完整数据通过正式 Release v1.0.0 附件获取。普通 git clone 只下载代码、索引与展示。先按 README 的 meshes 预设获取全部 STL/PLY；需要重建机制时补 full 或单例 rebuild 预设。

`au12321ua` 已有 write 权限。请在分支提交改动，保留案例原始字节、mm 单位和 SHA256。生成目录、环境、缓存、下载包和私有评测材料均 gitignore，不要强制加入 Git。按匿名 part_group 划分开发/评测，六个案例保持同组。

Generate 与 Repair 分开；Repair 是 https://github.com/zhuoxili-jackie/scanmesh-toolkit 。本次只更新生成实现、数据分发与案例展示，没有运行修复实验。
