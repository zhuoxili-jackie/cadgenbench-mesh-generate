# 数据分发

版本 `v1.0.0`：174 例，29 组，每组 easy/medium/hard × 两种子。原始 STL/PLY 字节与本地终验一致。

Git 保存代码、配置、174 行清单、验收摘要和小型展示。大数据使用同一仓库 Release 的独立 ZIP 附件，每包小于 1 GiB；无需 Git LFS，也无需合并分卷。GitHub 官方说明单个 Release 附件需小于 2 GiB，见 [官方文档](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas)。

只做 Mesh 读取/修复时下载 meshes、previews、metadata。重做观测重建另需 reconstruction 和 observations；共享观测只保存一次。full 包集不含任何 GT/STEP、私有对应表、私有图、旧 Mesh、环境、日志或可再生重建缓存。它提供全部已验收公开输入，不等同于完整的本地历史审计工程。

`SHA256SUMS.txt` 校验每个附件；`release-manifest.json` 校验解压后的每个真实文件。不要更改单位或归一化后冒充原始数据。所有参考单位为 mm，STL 本身没有单位字段，必须保留同目录 README.json。

包按案例及共享观测组组织。每个 Mesh 案例的 STL 与 PLY 位于同一个包；各包解压到同一目标目录。单例下载以 accepted_cases.jsonl 的 release_assets 为准，不保证一个 ZIP 只有一个案例。preset meshes 包含全部 174 例，两种子不重复命名替代。

GT 与源件映射只留在可信评测侧。模型可见输入按实验允许清单配置，不把观测或评测资料默认暴露给只允许 Mesh 的实验。

对应 v1.0.0 的 GT、私有映射及几何依据通过[独立评测仓库](https://github.com/zhuoxili-jackie/cadgenbench-evaluation-private)单独交付，约 632 MiB。访问与接收步骤见[可信评测交接说明](TRUSTED_EVALUATION_HANDOFF.md)。
