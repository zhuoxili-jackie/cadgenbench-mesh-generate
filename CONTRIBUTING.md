# 协作入口

仓库为李卓曦与黄星尧的 Generate 协作预览。先消费 `examples/observed_case/` 的 raw Mesh，再通过 Release 下载完整观测重建包。模型可见文件按案例允许清单配置，GT 与私有评测映射在可信侧另包交接。

普通 `git clone` 获取代码和演示 Mesh；全量扫描数据不随克隆下载。版本、已验收案例和下载包哈希在 `data_index/`，分发约定见 `docs/DATA_DISTRIBUTION.md`。

改动在分支上提交。生成目录、环境、缓存和运行日志已忽略。不要把本地整个 `data/` 强制加入 Git；原始字节、坐标、单位与哈希应保持可追溯。

环境、输入格式或观察工具有变化时，先提交最小案例和影响说明。当前 full-batch 脚本需要原工程证据与状态，本快照主要服务代码审阅、首件读取、独立观测重建及接口联调。

[协作计划](https://mcn12m1x8pa4.feishu.cn/wiki/QUzLwk9UDiLf6Hk36qXcSlZJn2c) · [For Huang](https://mcn12m1x8pa4.feishu.cn/wiki/WJsswtWQ9iTC4kkIvrTcnhUIneg) · [For Li](https://mcn12m1x8pa4.feishu.cn/wiki/DhPJwydQZifT8VkYkFHceMDCn9w)
