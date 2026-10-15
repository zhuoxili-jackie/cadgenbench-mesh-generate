"""Write final delivery documentation only after the complete audit passes."""
from pathlib import Path
import sys,os,datetime,argparse
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'));os.chdir(ROOT)
from scanbench.common import *
from scanbench.reporting import report
from build_stage_resources import build as build_stage_resources
p=argparse.ArgumentParser();p.add_argument('--goal-seconds',type=float,required=True);p.add_argument('--goal-active-seconds',type=float);args=p.parse_args();summary=report();audit=load_json(ROOT/'reports/final_audit.json');assert summary['status']=='complete' and audit['status']=='pass'
stage_resources=build_stage_resources()
perf=load_json(ROOT/'reports/performance.json');sources=[json.loads(s) for s in (ROOT/'manifests/sources.jsonl').read_text(encoding='utf-8').splitlines()];cases=[json.loads(s) for s in (ROOT/'manifests/cases.jsonl').read_text(encoding='utf-8').splitlines()];cfg=config();tiers=summary['tiers'];totalbytes=sum(p.stat().st_size for p in ROOT.rglob('*') if p.is_file());publicbytes=sum(p.stat().st_size for p in (ROOT/'data').rglob('*') if p.is_file());peak=max((x['max_peak_rss_bytes'] for x in perf['stages'].values()),default=0);events=[json.loads(s) for s in (ROOT/'state/events.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()];successful_attempt_seconds=sum(e.get('metrics',{}).get('seconds',0) for e in events if e.get('event')=='stage_complete');runtime={'goal_elapsed_seconds_at_delivery':args.goal_seconds,'historical_completed_stage_attempt_seconds':successful_attempt_seconds,'note':'goal wall time includes implementation, calibration, waits, tests and audits; completed-stage sum includes superseded calibration stages but not unfinished attempts or uninstrumented work','whole_project_bytes':totalbytes,'public_data_including_reconstruction_caches_bytes':publicbytes,'peak_measured_worker_rss_bytes':peak,'disk_free_bytes':__import__('shutil').disk_usage(ROOT).free};atomic_json(ROOT/'reports/execution_resources.json',runtime)
peak=max([peak]+[e.get('metrics',{}).get('peak_rss_bytes',0) for e in events if e.get('event')=='stage_complete'])
successful_attempt_seconds=sum(e.get('metrics',{}).get('seconds',0) for e in events if e.get('event')=='stage_complete' and not e.get('metrics',{}).get('equivalent_camera_builder_migration'))
runtime.update(historical_completed_stage_attempt_seconds=successful_attempt_seconds,peak_measured_worker_rss_bytes=peak)
runtime.update(goal_tool_active_seconds_at_delivery=args.goal_active_seconds,wall_time_includes_user_requested_pause_and_discussion=True)
runtime.update(initial_project_target_gib=cfg['resources']['project_target_gib'],actual_project_above_initial_target=totalbytes>cfg['resources']['project_target_gib']*2**30,system_free_above_reserved_minimum=runtime['disk_free_bytes']>=cfg['resources']['reserve_gib']*2**30,storage_scope_note='Logical file sizes include required original observations, all Mesh outputs, immutable historical revisions and isolated real verification artifacts; derived reconstruction caches are excluded from distribution assets.')
active_time_text=f'goal 工具累计活动时间 {args.goal_active_seconds/3600:.2f} 小时；' if args.goal_active_seconds is not None else ''
atomic_json(ROOT/'reports/execution_resources.json',runtime)
limited='；'.join(f'{x["source_id"]}：{x["actual_placements"]} 次' for x in audit['limited_placements']) or '无'
discrete='；'.join(f'{x["source_id"]}/姿态 {x["placement_id"]}：{x["certified_contact_points"]} 个认证接触点，COM 余量 {x["COM_margin_mm"]:.3f} mm' for x in audit.get('certified_discrete_supports',[])) or '无'
frozen=load_json(ROOT/'reports/protocol_freeze.json')
implementation=frozen.get('implementation_revision','initial')
sampling=audit['physical_sampling_revision'];assert sampling['status']=='pass' and sampling['phase']=='full_current_batch'
sampling_policy=load_json(ROOT/'configs/sampling_density_v2.json')
sampling_version=sampling_policy['protocol']
sampling_overrides='; '.join(f'{sid}: {intervals} intervals ({intervals//4+1}/{intervals//2+1}/{intervals+1} frames per placement for hard/medium/easy)' for sid,intervals in sorted(sampling_policy['source_intervals'].items()))
sampling_table='| 源件 | 母轨迹间隔数 | hard 每放置帧数 | medium 每放置帧数 | easy 每放置帧数 |\n|---|---:|---:|---:|---:|\n'
for sid in sorted(summary['six_case_complete_sources']):
    example=next(c for c in cases if c['source_id']==sid)
    contract=load_json(ROOT/example['input_path']/'sampling_contract.json');intervals=contract['mother_intervals']
    sampling_table+=f'| {sid} | {intervals} | {intervals//4+1} | {intervals//2+1} | {intervals+1} |\n'
continuous=audit['continuous_free_space_correction'];preservation=continuous['baseline_preservation']
validity=audit['source_validity_diagnostics'];parameter_warning_sources=', '.join(validity['extra_exact_parameter_warnings']) or '无'
parameter_table='| 源件 | 同参数最大距离 mm | 曲线几何最近距离的采样最大值 mm | 检查的边/面组合 | 证据 |\n|---|---:|---:|---:|---|\n'
for item in validity['additional_quantification']:
    parameter_table+=f'| {item["source_id"]} | {item["max_same_parameter_disagreement_mm"]:.6g} | {item["max_sampled_locus_distance_mm"]:.6g} | {item["flagged_edge_face_pairs"]} | [实际诊断](../{item["evidence"]}) |\n'
amendments='；'.join(f'[{Path(x["path"]).parent.name}]({Path(x["path"]).relative_to("reports").as_posix()})' for x in frozen.get('implementation_amendments',[])) or '无'
source_table='| 源件 | 分层 | 实际稳定姿态 | 正式案例 | 离散弦高参数 mm | 采样最大偏差 mm | 证据 |\n|---|---|---:|---:|---:|---:|---|\n'
exclusion_details=[]
for source in sorted(sources,key=lambda x:x['source_id']):
    sid=source['source_id'];tier=source['status'];label={'eligible_native':'native','eligible_official_mesh_approx':'官方 Mesh 近似','source_excluded':'排除'}[tier]
    nposes=len(load_json(ROOT/f'private/gt/{sid}/placements.json')['placements']) if tier!='source_excluded' else '—'
    count=sum(c['source_id']==sid for c in cases);precision=source.get('chord_mm',source.get('original_linear_deflection_mm','—'))
    evidence=source.get('evidence_summary',f'private/gt/{sid}/metadata.json');target='../'+evidence
    measured_error=source.get('boundary_accuracy',{}).get('sampled_max_mm',source.get('accuracy_check',{}).get('max_sampled_mm'))
    error_text=f'{measured_error:.6g}' if measured_error is not None else '—'
    boundary_link=f' / [边界复核](../{source["boundary_accuracy"]["qualification"]})' if source.get('boundary_accuracy') else ''
    source_table+=f'| {sid} | {label} | {nposes} | {count} | {precision} | {error_text} | [实际记录]({target}){boundary_link} |\n'
    if tier=='source_excluded':exclusion_details.append(f'- {sid}：{source["reason"]} [证据]({target})')
exclusion_text='\n'.join(exclusion_details) or '无排除源件。'
reference_adjustment_text='；'.join(f'{x["source_id"]}：声明弦高 {x["chord_mm"]:g} mm，独立边界采样最大偏差 {x["sampled_boundary_max_mm"]:.6g} mm，[精度依据与先前尝试](../{x["evidence"]})' for x in audit.get('reference_scale_adjustments',[])) or '无额外源件精度调整'
bounds_correction_text='；'.join(f'{x["source_id"]}：原包围盒多计 {x["legacy_overestimate_mm"]:.6g} mm，参考与真实 CAD 极值的最大差 {x["actual_reference_bounds_error_mm"]:.6g} mm，[六方向独立复核](../{x["evidence"]})' for x in audit.get('axis_plane_bounds_corrections',[])) or '无'
mesher_adjustment_text='；'.join(f'{x["source_id"]}：边界弦高 {x["chord_mm"]:g} mm、角差 {x["angle_rad"]:g} rad，面内弦高 {x["parameters"]["DeflectionInterior"]:g} mm，边界采样最大偏差 {x["sampled_boundary_max_mm"]:.6g} mm，[完整参数和替代尝试](../{x["evidence"]})' for x in audit.get('native_reference_mesher_adjustments',[])) or '无'
quality='| 档位 | 案例数 | Mesh→观测支持 最小/平均 | 观测→Mesh 保留 最小/平均 | GT 总表面覆盖 平均 |\n|---|---:|---:|---:|---:|\n'
for level,q in audit['quality_by_difficulty'].items():quality+=f'| {level} | {sum(c["level"]==level for c in cases)} | {q["mesh_support"]["min"]:.4%} / {q["mesh_support"]["mean"]:.4%} | {q["observed_retention"]["min"]:.4%} / {q["observed_retention"]["mean"]:.4%} | {q["GT_coverage"]["mean"]:.4%} |\n'
commands='''```powershell
# 在工程根目录执行；环境为 Windows / Python 3.12
$env:OMP_NUM_THREADS='2'
$env:OPENBLAS_NUM_THREADS='2'
$env:MKL_NUM_THREADS='2'
$env:NUMBA_NUM_THREADS='2'
py -3.12 -m venv .venv
.\\.venv\\Scripts\\python.exe -m pip install -r requirements.lock
.\\.venv\\Scripts\\python.exe scripts/bootstrap.py doctor
# 完整批次入口；本次先执行全源件驱动，诊断后按源件恢复，已有合格阶段按 hash 复用。
# 该命令默认覆盖全部 32 个官方源件，不会把尚未处理的异常自动变成排除。
.\\.venv\\Scripts\\python.exe scripts/run_full.py --resume
# 本次后段已执行的精确恢复命令（前者对应 logs/remaining_unaffected_246_250.log）：
.\\.venv\\Scripts\\python.exe scripts/run_full.py --resume --ids 246 247 248 249 250
.\\.venv\\Scripts\\python.exe scripts/run_full.py --resume --ids 245
# 独立验收：不生成或修改 Mesh
.\\.venv\\Scripts\\python.exe scripts/scanbench.py validate --all
.\\.venv\\Scripts\\python.exe scripts/supplemental_audit.py --all
.\\.venv\\Scripts\\python.exe scripts/final_audit.py
# 以下两条已实际执行，exported_case_sampling_v2 保留了当前实现的输出和访问审计。
# 再执行时使用完整工程副本，或将两条命令的 exported_case_sampling_v2 换成新的空目录名。
.\\.venv\\Scripts\\python.exe scripts/scanbench.py export-case --case-ids case_2438b1a3fd780c63 --output exported_case_sampling_v2 --observations-only
.\\.venv\\Scripts\\python.exe exported_case_sampling_v2/rebuild.py
# 当前采样 v2：从原始 STEP 开始的完整单例复现，实际比较观测数组和 Mesh 顶点/连接。
.\\.venv\\Scripts\\python.exe scripts/test_current_step_reproduction.py
# 本次已实际执行的证据实验：完整 STEP 复现、真实中断恢复、无变更恢复
# 前两条在有效签名存在时复用证据；第三条会更新冻结的测试报告。
# 如需重做这组实验，在完整工程副本中运行；上方 export-case 可直接生成新的独立 Mesh。
.\\.venv\\Scripts\\python.exe scripts/run_reproduction_r4.py
.\\.venv\\Scripts\\python.exe scripts/run_mesh_resume_r4.py
.\\.venv\\Scripts\\python.exe scripts/test_production_resume_r4.py
```

入口与作用域：`bootstrap.py doctor` 记录环境；`run_full.py --resume` 默认按固定清单逐件处理全部 32 件，包含来源、GT/放置、观测、六例生成与验收；`--ids` 明确限制源件。历史 pilot 在 218 首件之后运行 `.\\.venv\\Scripts\\python.exe scripts/run_pilot_remaining.py`，仅补 229/231 并核对 218，完成日志为 `logs/pilot_remaining_v6.log`。`validate --all` 与 `supplemental_audit.py --all` 只验收完整当前批次，不生成 Mesh；缺关键源件/案例会返回非零。独立单例重建入口为导出目录的 `rebuild.py`，上方两条实测命令已涵盖公开输入导出与重建。当前状态报表入口是 `.\\.venv\\Scripts\\python.exe scripts/report_progress.py`；本次实际已多次执行，最终文档由 `write_delivery.py` 在全量独立验收后生成，再用 `.\\.venv\\Scripts\\python.exe scripts/verify_delivery_documents.py` 核查。环境报告、报表与历史测试重做应在完整工程副本中进行，以保留本次冻结证据及交付文件。
\n'''
body=f'''# CADGenBench 物理扫描与破损 Mesh 最终报告

完成固定版本 `{REV}` 的全部 32 个公开 STEP 判定。native {len(tiers['eligible_native'])} 件，官方 Mesh 近似层 {len(tiers['eligible_official_mesh_approx'])} 件，排除 {len(tiers['source_excluded'])} 件；六例完整源件 {len(summary['six_case_complete_sources'])} 件，正式案例 {summary['verified_case_count']} 例。当前全量独立验收通过，无未处理 failed/pending。

## 数据与索引

- 正式数据：[data/cases](../data/cases/)，共享带噪观测：[data/observations](../data/observations/)。
- 完整表面预览：[preview_index.html](preview_index.html)。每例使用全部三角形生成六视图，包含斜视与初始接触面；橙色表示从开口看到的三角形背面。
- [quality_table.csv](quality_table.csv)、[final_audit.json](final_audit.json)、[acceptance.json](acceptance.json)、[tests_report.json](tests_report.json)、[final_file_inventory.json](final_file_inventory.json)。
- 私有源件对应、GT、逐例验收与补充特征检查位于 `private/`；公开重建输入不含 GT。
- 来源清单：[sources.jsonl](../manifests/sources.jsonl)，案例清单：[cases.jsonl](../manifests/cases.jsonl)，限制和排除依据均由实际记录生成。

## 实际质量

{quality}
这些指标使用各例报告的毫米容差 `max(3σ, 1.5h)`，不能解释成无孔、完整或全局 Hausdorff 保证。独立固定面积采样每例 30,000 点；Mesh→GT 距离是样本统计。各例 `supplemental.json` 将缺失按持续桌面接触、有限视角不可达、自遮挡/入射角、有限像素观测和 meshing 丢失分开记录。

## 物理和重建协议

当前物理采样版本为 `{sampling_version}`，实现修订为 `{implementation}`。源件 245 的原 hard 相邻重叠不足后，按任务书沿完整螺旋均匀加密并单独冻结新版本；噪声、重建和质量门限保持不变。实现修订及兼容性证据：{amendments}。采样版本、原始冻结和当前代码快照见 [protocol_freeze.json](protocol_freeze.json) 与 [采样修订](protocol_amendments/r5_sampling_density/amendment.json)。

毫米制，不归一化尺寸。OCP 拓扑离散优先使用 0.02 mm 弦差和 0.15 rad 角差；实际参数、替代尝试、STEP 单位与原离散精度按源件记录。每次放置均通过精确 BREP 桌面高度、接触面积与重心支撑检查。相机从 75° 向 5° 绕完整三圈，持续看向中心；桌面与物体比较首次命中，接触面不作为扫描返回。默认母轨迹 193 帧，hard/medium/easy 每放置 49/97/193 帧，默认 1/2/3 次放置；有依据的均匀加密见下表。同帧、同种子观测跨档完全共享。每例公开 `sampling_contract.json` 给出实际间隔数、帧数、放置次数和冻结策略 hash。

{sampling_table}

未加密的 {sampling['unchanged_source_count']} 件 / {sampling['unchanged_case_count']} 例保留原始相机、观测、工作点、Mesh 与缓存。原数值检查函数 AST 相同，实际旧输入完整 hash 一致，物理检查重新执行且结果完全一致后，才更新阶段和验收元数据；旧验收原件完整归档。加密源件的旧相机位置使用原整数噪声键，新位置使用原母网格的精确有理参数键，已有噪声载荷不变。独立全量复核见 [采样迁移核查](protocol_amendments/r5_sampling_density/full_independent_audit.json)。

噪声是沿单位射线的 Euclidean range 高斯噪声，σ=`clip(0.0002D, 0.01, 0.10)` mm，截断于 ±3σ。固定 SplitMix64/Box–Muller 键包含源件、种子、姿态、母帧和像素，两个种子为 20261014 与 20261015。

重建仅从带噪观测估计法向，按 voxel 与六个主轴方向法向锥选取真实观测代表点，不平均或投影回 GT。BPA 半径为 1/1.5/2/2.5h，受边长、三角形内部观测支持和前景自由空间约束；不补洞、不 Poisson 补全、不删除方位扇区或随机 GT 面。`normal_cluster_degrees` 是保留的无效草稿字段，实际聚类规则以冻结代码中的六法向锥为准。

源件 243 easy 第一种子在独立面积采样中暴露了原 22 点三角形采样漏检的局部自由空间冲突。r4 统一增加连续检查：把三角形裁剪到实测稳定 3×3 前景像素对应的透视单元，求该交集的最小 Euclidean range，仅删除违反原自由空间门槛的三角形，不增加或移动表面。此次候选实现的退化像素单元误判也经独立测试发现并在正式更新前修正；失败候选、原 Mesh 和全部诊断均保留。修订重新通过三源件 18 例 pilot、当前代码的无 GT/STEP 复现/真实进程树中断/无变更恢复测试后冻结。

当前全部案例中，连续检查对 {continuous['affected_cases']} 例移除了共 {continuous['removed_faces']} 个有观测依据的三角形；单例最大移除面积占比 {continuous['max_case_removed_area_fraction']:.6%}。独立验收使用另一套二维重心半平面与凸二次最小值算法逐一复核删除依据，并逐面比较保留三角形的实际坐标。修改前 129 例的 {preservation['baseline_files']} 个文件中，{preservation['hash_and_mtime_preserved']} 个保持 hash 与时间戳不变，{preservation['explicitly_archived_downstream_mesh_files']} 个明确更新的下游 Mesh/重建记录保留完整原件；扫描、GT、工作点和有效上游缓存均未重跑或改写。证据见 [r4 修订](protocol_amendments/r4_continuous_free_space/amendment.json)、[全量保留核查](protocol_amendments/r4_continuous_free_space/full_inventory_audit.json) 和逐例 `continuous_veto.json` / `reports/continuous_independent/`。

## 限制与证据

- 实际不足三种稳定姿态：{limited}。未重复姿态或悬空凑数。额外候选使用有限凸包支撑方向提案，再按精确 CAD 接触与重心条件认证；候选生成的回归测试见 [hull_pose_proposals.json](tests/hull_pose_proposals.json)，停滞问题的诊断与修正见 [correction.json](pose_audit_revision/correction.json)。
- 单列的点/线接触姿态：{discrete}。真实接触面积记为零，支撑多边形面积另记；至少三个非共线的真实 CAD 接触点贴桌，精确 BREP 不穿桌，独立质心余量超过数值/曲率带才可采用。单点、共线、滚动近似或悬空候选不会据此通过。证据见 [实际 CAD 控制与兼容性检查](tests/discrete_contact_support.json)。
- 有独立证据的自然分离案例共 {len(audit['natural_separation_cases'])} 例，见全量审计列表及逐例 `fragmentation_review.json`。逐区域对应、相同带噪距离图的局部三角化对照、观测保留与完整方位检查均保留。
- 其中 {len(audit.get('subpixel_region_join_limits',[]))} 例存在不足一像素的参考可见面间隙被局部连接的分辨率限制，不能宣称这些小槽保真。原始连通分量与最初未通过的严格对应结果均保留；另按声明像素尺度核对主要分区，并从原始像素/range 回读连接面支持证据。逐例面积比例、支持率和证据路径见 `final_audit.json` 的 `subpixel_region_join_limits`。Mesh、扫描参数和质量门槛均未为此修改。
- 亚分辨率特征不作保真承诺。各源件 `feature_contract.json` 给出实际采样尺度；每例对所有可识别、可解析的轴向圆柱通道进行独立射线检查。非圆柱槽仍受全表面观测支持和自由空间约束，未声称完成语义槽枚举。
- 小尺度 BPA 孔隙和局部 meshing 损失仍可见，并单列为算法损失，不能当作物理遮挡。没有以补洞掩盖缺失。
- 三档几何可见集合保持嵌套；最终 Mesh 总覆盖率有 {len(audit['nonmonotonic_mesh_coverage'])} 组非单调比较，逐点分开核查了容差收紧与局部成网变化，未修改正式分数或删除观测。当前证据见 [覆盖率比较](monotonicity/summary.json)；[初期 pilot 补充分析](pilot_monotonicity_addendum.md) 作为历史分析保留，不替代当前逐例结果。
- 扫描是已知准确姿态、理想前景分割、无限平面桌面和受控 range 噪声的几何模拟，不是特定扫描仪的精度复刻；封闭或深腔不保证可达，多实体按刚性装配处理并在源清单标记。
- 原始 STEP 和 GT 仅用于采集/私有验收。无 GT 新目录独立进程重建、整例 STEP 同种子复现、实际进程杀停恢复、已完成 hash/mtime 不变、缺失/破损文件拒绝均有真实运行证据。

## 来源分层

native：{', '.join(tiers['eligible_native']) or '无'}。

官方 Mesh 近似层：{', '.join(tiers['eligible_official_mesh_approx']) or '无'}。

近似层使用固定官方版本的原始多边形参考，不以细分宣称提高曲面精度。扫描和覆盖指标针对该参考；逐件保留有效 STEP、原生替代尝试、官方哈希、尺寸/体积及 Mesh→BREP 距离核查。下表区分离散参数与实测采样最大偏差，后者也不是精确全局 Hausdorff 距离。

所有正式参考另经 128 个固定面积样本到 CAD 边界面的独立距离复核，涵盖曲面向内、向外的离散偏差；点/线支撑的接触点也另做边界面距离检查。原始元数据中的点到实体快速检查保留为历史诊断，因实体内部点可能返回零，不作为完整表面距离。下表与来源清单的 `boundary_accuracy` 使用独立边界复核结果；实际控制证据见 [box_control.json](source_boundary_audits/box_control.json)。

源件的 `brep_valid` 明确指冻结实现采用的 OpenCascade `BRepCheck_Analyzer` 默认几何检查，不是严格参数自洽或全局几何误差的证明。全部 32 件另做了默认检查、拓扑检查和连续同参数检查；以下源件默认检查通过，但额外连续同参数检查未通过：{parameter_warning_sources}。原始 3D 边曲线与面上参数曲线可能存在表示偏差，不能把同参数距离直接等同于物理几何间隙。全部检查结果、具体子形体和错误码均保留在 [源件有效性检查明细](source_validity_scope.json)。未修改源文件、边容差、几何或冻结的资格门槛，也没有声称这些额外检查通过。扫描层的可靠性仍由实际参考网格拓扑、声明精度、独立 CAD 边界采样和逐例扫描验收约束；这些数据不提供 CAD 参数修复或后续布尔运算正确性保证。

对 244–250 的所有报错边/面组合进一步比较了同参数距离及双向曲线最近距离。后者使用固定参数采样和局部数值最小化，只是样本的最近距离上界，不是全曲线 Hausdorff 上界；两列数值不可互换，也不替代参考网格实测精度。

{parameter_table}

源件参考精度的额外调整：{reference_adjustment_text}。源件 241 的 0.05 mm 原生候选低于其 0.10 mm range 噪声尺度，且比官方 0.5 mm 近似参考细一个数量级；先前四组原生精度结果和新的实际几何对照完整保留。这是该源件在采集前声明的参考精度，扫描、重建和逐例质量门槛未改变。包围盒数值异常另由 CAD 边界到六个外侧平面的距离核查，含已知尺寸与旋转方块控制，最终验收再次实际计算：{bounds_correction_text}。

原生面内精度控制的额外实现：{mesher_adjustment_text}。该独立副本只显式设置五个 OpenCascade 离散参数，避免默认实体容差把面内误差提高；原官方拓扑拼接代码经 AST 比较保持完全一致，未改变 STEP、补洞或坐标焊接。方块与圆柱的解析几何控制，以及最终从实际控制网格重算的结果见 [native_surface_control.json](tests/native_surface_control.json)。这些源件仍使用同一冻结扫描、重建和逐例验收流程。

排除源件：{', '.join(tiers['source_excluded']) or '无'}。具体原因及尝试不在此省略，见对应源件记录与日志；没有把脚本异常或一次超时当作排除理由。

{source_table}

{exclusion_text}

## 资源与复现

初始工程磁盘目标为 {cfg['resources']['project_target_gib']} GiB。实际工程保留全部观测、Mesh、不可变修订原件和隔离验收实验，当前逻辑文件总量为 {totalbytes/2**30:.3f} GiB；系统盘实测空闲 {runtime['disk_free_bytes']/2**30:.3f} GiB，保留门限为 {cfg['resources']['reserve_gib']} GiB。分发资产排除可再生重建缓存，完整工程中的有效阶段与证据保持可回读。

逐例资源记录位于 `private/annotations/<case_id>/resources.json`，关联 [实际阶段资源索引](stage_resources.json) 中的阶段输入 hash、原始计时/RSS、当前产物字节及共享观测引用。各例重建、数值验收和渲染均有实测时间/RSS；共享源件处理、历史测量与未单独计量的元数据组装明确区分，未把缺测填成零，也未把当前文件大小称为历史磁盘峰值。

当前采样 v2 另从 STEP 独立重做一例，重新确定分辨率、姿态和相机，比较约 {load_json(ROOT/'reports/tests/full_case_reproduction_sampling_v2.json')['observed_pixels_compared']:,} 个真实观测返回及实际 Mesh 顶点/连接，均严格一致。新证据见 [当前版本 STEP 复现](tests/full_case_reproduction_sampling_v2.json)；原 r4 复现与恢复实验仍完整保留。

截至交付记录，从 goal 创建起实际经过 {args.goal_seconds/3600:.2f} 小时（含用户要求的暂停与协作讨论）；{active_time_text}已完成阶段历史计时总和 {successful_attempt_seconds/3600:.2f} 小时（包含校准），单工作进程实测峰值 RSS {peak/2**30:.3f} GiB。整个工程含虚拟环境、复现实验与缓存 {totalbytes/2**30:.3f} GiB；`data` 含重建缓存 {publicbytes/2**30:.3f} GiB。生产按单源件、单案例串行，数值库 2 线程，保留至少 {cfg['resources']['reserve_gib']} GiB 系统空闲；只读辅助诊断与验收在内存余量足够时并行运行。提前进行的连续自由空间独立核查先实测单例成本，并在每例启动前要求至少 3 GiB 可用内存，逐次资源记录保留在 `reports/operations/ready_continuous_*.json` 和 `reports/operations/completed_case_snapshot_*.json`。205 处理期间观察到跨案例内存滞留后，后续源件改为每例独立子进程，案例结束即释放进程内存；冻结的数值算法不变，执行逻辑一致性与真实缓存复用证据见 [case_process_isolation/proof.json](operations/case_process_isolation/proof.json)。详见 [execution_resources.json](execution_resources.json)、[performance.json](performance.json)、[environment.json](environment.json)。

{commands}
正式状态由 SQLite 原子阶段和实际文件 hash 决定，不从旧日志累加案例数。导出命令只携带公开观测、相机、参数与重建代码；导出的 `rebuild.py` 拒绝已有非空重建输出目录。上述导出与重建命令已在空目录实际执行，几何顶点和面连接完全一致，原工程 private/sources/data 路径读取为零，见 [交付命令实测](operations/delivery_export_command_sampling_v2.json)。当前完整导出与重建结果保留在 `exported_case_sampling_v2/`；`exported_case/` 保留先前实现的历史证据。已有测试证据按当前代码/输入签名复用，删除产物或篡改数据不会被当作有效缓存。

工作止于破损 Mesh 数据生成与验收，未启动 e2e script generation、repair、SCA/CQ、Harbor 或 RSI。
'''
atomic_bytes(ROOT/'reports/final_report.md',body.encode('utf-8'))
readme=f'''# CADGenBench physical scan / damaged Mesh dataset

Status: complete. All 32 official STEP sources were attempted at revision `{REV}`. Native: {len(tiers['eligible_native'])}; official-mesh approximation: {len(tiers['eligible_official_mesh_approx'])}; excluded: {len(tiers['source_excluded'])}. Actual accepted cases: **{summary['verified_case_count']}**.

[Final report](reports/final_report.md) · [Full-surface previews](reports/preview_index.html) · [Quality table](reports/quality_table.csv) · [Independent audit](reports/final_audit.json) · [Tests](reports/tests_report.json) · [Data card](DATASET_CARD.md) · [Licenses](LICENSES.md)

Public cases are under `data/cases/<opaque_case_id>/input/`; observations are shared by content hash under `data/observations/`. `private/` and source mappings are evaluation-only. Hidden `.reconstruction_cache/` directories contain derived public-observation intermediates and are not required input assets; export-case omits them.

Each input includes shared-vertex PLY, STL, observed working points, per-point camera/pixel provenance, camera matrices, range-observation references, complete reconstruction settings, protocol hash and an explicit `sampling_contract.json`. Physical sampling version: `{sampling_version}`. Default mother-grid intervals: 192. Evidenced uniform refinements: {sampling_overrides}. No GT geometry or GT normals are read by reconstruction.

{commands}
Windows shell execution used PTY without login. Background test workers were hidden. Existing GLM projects and old data were left unchanged.
'''
atomic_bytes(ROOT/'README.md',readme.encode('utf-8'))
card=f'''# Dataset card

This local dataset simulates partial physical tabletop scans of fixed public CADGenBench input STEP geometry. It contains {summary['verified_case_count']} actual cases from {len(eligible) if (eligible:=summary['six_case_complete_sources']) else 0} six-case sources, with two fixed noise seeds and three placement/density levels. The private source/case mapping is in `manifests/`.

Upstream: HuggingAI4Engineering / CADGenBench / Mecado, [fixed source revision](https://huggingface.co/datasets/HuggingAI4Engineering/cadgenbench-data/tree/{REV}), ODC-BY. The upstream editing instructions were not executed; input.step is used as original geometry. SHA256 is verified against the official LFS inventory. See LICENSES.md for attribution and third-party notices.

Physical sampling version: `{sampling_version}`. Base path geometry, noise, reconstruction and quality gates retain their pilot values; evidenced uniform path-density refinements are frozen separately: {sampling_overrides}. Current implementation revision: `{implementation}`. Each case records its actual sampling in `sampling_contract.json`. The [freeze manifest](reports/protocol_freeze.json) binds original and current code, the sampling policy, controls, exact compatibility and qualified cache-reuse evidence.

Use: controlled tests of algorithms consuming genuinely incomplete, noisy, observed geometry. Data represents exact poses and ideal segmentation. It does not model reflectance, photometric failure, motion blur, drift or a calibrated commercial scanner. No repair/modeling task was performed.

Difficulty changes only physical placements and nested path sampling. Every path covers three full downward turns. The table participates in first-hit occlusion. Stable poses may be fewer than three: {limited}. No artificial directional sector deletion or random ground-truth triangle deletion was used.

Separately certified point/line supports: {discrete}. Their physical contact area remains zero; the support polygon is recorded separately. Exact CAD contact, table clearance and strict COM stability are rechecked independently. A single rolling contact or collinear contacts do not qualify.

Reconstruction uses measured normals and observed points only, with bounded BPA and range support/free-space rejection. The PLY preserves shared topology, while STL round-trips the same facets. Small local meshing holes remain; these are reported separately from physical missing surfaces. Subresolution features and inaccessible cavities are explicit limitations, not excluded difficult cases.

Native / approximate / excluded source counts: {len(tiers['eligible_native'])} / {len(tiers['eligible_official_mesh_approx'])} / {len(tiers['source_excluded'])}. Per-source precision, units, actual settings, stable poses, all feature checks and nonfatal natural limitations are in the [final report](reports/final_report.md), [source manifest](manifests/sources.jsonl) and private annotations. All delivered cases passed independent acceptance at the stated tolerances. Quality metrics are sampled engineering checks, not mathematical guarantees.

The official-mesh approximation tier targets the unchanged upstream polygonal reference. Its original chord parameter and sampled deviation from the valid STEP are recorded separately; no subdivision is presented as improved CAD surface accuracy. Extra reference qualification does not change the frozen scan, noise, reconstruction or acceptance settings.

Reference precision is independently checked against a compound of all CAD boundary faces, avoiding the zero distance that OCCT can return for a point inside a solid. `boundary_accuracy` in the source manifest is the complete sampled boundary-distance result; the older point-to-solid diagnostic is retained as historical evidence. Discrete contact points also pass a separate boundary-only check.

`brep_valid` refers to the frozen default OCCT BRepCheck_Analyzer geometry checks. All 32 sources also have separate continuous same-parameter diagnostics. Sources passing the default check but failing the extra exact-parameter check: {parameter_warning_sources}. These known source representation inconsistencies are disclosed in [source_validity_scope.json](reports/source_validity_scope.json) and quantified further for 244–250 in the final report. No source geometry or edge tolerance was modified, and the extra checks are not represented as passes. A same-parameter discrepancy is not necessarily a physical curve-locus gap. Reference topology and sampled boundary accuracy remain separate qualifications; this dataset does not certify CAD parameter consistency or downstream Boolean operations.

The exported case is independently rebuildable from public observations only. Full reproduction and real interruption/resume are evidenced in [tests_report.json](reports/tests_report.json). Public observation storage is shared across levels; export-case resolves references into an isolated directory. Use requirements.lock and the commands in README.md.
'''
atomic_bytes(ROOT/'DATASET_CARD.md',card.encode('utf-8'))
atomic_bytes(ROOT/'reports/progress_report.md',(f'# CADGenBench scan delivery\n\nStatus: **complete**. All 32 source conclusions are recorded; {summary["verified_case_count"]} actual cases from {len(summary["six_case_complete_sources"])} sources passed current independent acceptance.\n\nSee the [final report](final_report.md), [quality table](quality_table.csv) and [full-surface preview index](preview_index.html) for the authoritative delivered results.\n').encode('utf-8'))
atomic_json(ROOT/'state/next_actions.json',{'status':'dataset_complete','next_action':'verify delivery document/index consistency, then stop; no downstream repair or modeling work authorized','final_audit_sha256':file_hash(ROOT/'reports/final_audit.json')});print('Wrote verified final report, README and data card')
