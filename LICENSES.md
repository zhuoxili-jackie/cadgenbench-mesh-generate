# Source and dependency attribution

The public CADGenBench editing inputs are from HuggingAI4Engineering / CADGenBench, with Mecado attribution in the upstream data card. The frozen data revision is `f76f965585817c621d6ea0d150d745adf670e66e`. Its data card declares **ODC-BY**. The unmodified data card is retained at `sources/DATA_CARD_UPSTREAM.md`; per-file download URL and SHA256 are retained beside every acquired STEP file. The simulated observations and derived mesh data retain this source attribution and database-license notice.

The topology-aware STEP tessellation implementation at `vendor/cadgenbench/common/mesh.py` and its profiling helper are copied unchanged from Hugging Face CADGenBench commit `33304cf771fc5639144b1df9611e347251052cf8`, copyright 2026 Hugging Face, **Apache License 2.0**. The original copyright headers and full license are retained in the vendor directory.

`tools/native_surface_control/native_surface_control_mesh.py` is a separately marked derivative of that Apache-2.0 implementation. It adds only five explicit OpenCascade meshing parameter assignments; source geometry and topology-stitching logic are unchanged. The original copyright header is retained, and the full license is at `vendor/cadgenbench/LICENSE`. Its modification notice and source hashes are documented by `reports/tests/native_surface_control.json` and each source's qualification evidence.

Third-party libraries are installed in the isolated `.venv`; their package versions are in `requirements.lock` and package/license metadata remains in each installed distribution. Open3D, NumPy, SciPy, Trimesh, cadquery-ocp / OpenCascade, Numba, llvmlite, Matplotlib, Pillow, Shapely, PyYAML and psutil are used under their respective licenses. No claim of ownership over the underlying source CAD models is made.

NetworkX 3.4.2 (BSD-3-Clause) was used by the initial Trimesh candidate-pose audit and is retained to reproduce that investigation. Current finite candidate proposals use SciPy; exact CAD contact and COM tests independently certify or reject them.

py-spy 0.4.1 (MIT) is a diagnostic tool used to inspect a stalled candidate-pose subprocess. It is not read by scanning or reconstruction; its license remains in the installed distribution.

An isolated diagnostic kernel, cadquery-ocp 7.9.3.1.1 with its proxy and VTK 9.6.2 dependencies, is retained under `tools/ocp79/` to cross-check source validity and tessellation behavior. It does not replace the frozen production runtime. Distribution metadata and licenses remain in that directory.
