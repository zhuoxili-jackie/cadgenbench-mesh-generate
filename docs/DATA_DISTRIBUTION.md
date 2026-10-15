# 数据与 Git 的边界

Git 保存源码、配置、依赖锁、文档、SHA256/大小/版本清单，以及一个已验收的公开演示 Mesh。生成数据目录由 `.gitignore` 排除。

| 内容 | 位置 | 分发方式 |
|---|---|---|
| 代码、配置、文档、数据清单 | 本仓库 | Git |
| 小型演示 Mesh 与预览 | `examples/observed_case/` | Git，保留真实原件与哈希 |
| 单例完整带噪观测/独立重建包 | GitHub Release | ZIP + SHA256 |
| 后续全量 raw/观测数据 | 冻结后按源件或依赖闭包打包 | Release 独立资产，建议每包不超过 1 GiB |
| GT、源件映射与评测答案 | 可信评测端 | 独立私有评测包 |
| 环境、临时文件、重建缓存、运行日志 | 本地 | 不进入 Git；可再生缓存不作为必要输入分发 |

当前本地 `data/` 约 21.98 GiB：观测 8.80 GiB，PLY/STL 6.07 GiB，其他案例输入 2.35 GiB，可再生重建缓存 4.76 GiB。它包含仍在处理的案例，不能直接压成“最终数据集”发布；正式数据包应从已验收案例清单选择，再计算实际观测依赖闭包并去重。

`.gitignore` 不会自动解除已跟踪的文件；本仓库在首次提交前就排除了大数据。Repair 原仓库已有的历史基线文件保持原样，新试验写入其忽略的 `runs/`。

下载后先按 `data_index/releases.json` 校验包大小与 SHA256，再解压。Windows 可用 `Get-FileHash -Algorithm SHA256 文件.zip`。公开案例包只允许 raw Mesh、扫描观测及其派生数据；私有评测材料不复制到模型的输入目录。

不默认启用 Git LFS：全量观测是版本化数据包，独立下载更适合此协作方式；LFS 的存储和下载会计入账号额度。GitHub Release 每个资产须小于 2 GiB，这里计划使用不超过 1 GiB 的包。数据清单需记录版本、案例 ID、文件大小、SHA256、下载位置与实际观测依赖。

官方说明：[Git ignore](https://git-scm.com/docs/gitignore)、[GitHub 大文件](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)、[Release 配额](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)、[LFS 计费](https://docs.github.com/en/billing/concepts/product-billing/git-lfs)。
