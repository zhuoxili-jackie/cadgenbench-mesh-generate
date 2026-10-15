# 可信评测参考交接

与本仓库 **v1.0.0 / 174 例** 对应的 GT、私有映射和几何依据，单独放在私有仓库：

[cadgenbench-evaluation-private](https://github.com/zhuoxili-jackie/cadgenbench-evaluation-private) · [评测包 v1.0.0](https://github.com/zhuoxili-jackie/cadgenbench-evaluation-private/releases/tag/v1.0.0)

评测包约 **632 MiB**，共三个普通 ZIP：元数据、参考几何、验收依据。包含 29 件参考 GT、全部 32 件原始 STEP 及结论、174 条私有案例映射、双向坐标变换、特征/精度说明和 GT 六视图。它通过公开案例清单、raw STL/PLY 哈希和公开 Release manifest SHA256 绑定本数据版本。

模型只读取 Generate 任务允许的扫描输入。GT 仓库及其下载包只放在可信评测机器/容器中；模型执行或源码重放环境不挂载该目录，不继承能访问它的 GitHub 凭据。私有参考不自动成为模型可见文件。

黄星尧 `au12321ua` 在接受独立仓库邀请后，按评测仓库 README 下载并运行 `verify_package.py`。交付方已核对全部 174 条映射、348 个 raw Mesh 文件哈希和 29 件参考几何；接收方还需在自己的环境确认读取、单位/坐标和输入隔离，并记录接收结果。

此处只提供评测包入口，不改变原 raw Mesh、公开下载包、数据版本、修复结果或下游评分口径。
