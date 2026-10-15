"""Read-only physical density investigation; never changes production inputs."""
from pathlib import Path
import argparse, os, sys
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT / 'src'))
for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMBA_NUM_THREADS']:
    os.environ[key] = '2'
from scanbench.common import *
from scanbench.camera import trajectory
from scanbench.validate import distance_scene
import trimesh
import open3d as o3d


def summarize(cameras, masks, difficulty):
    rows = {}
    for level, settings in difficulty.items():
        values, pairs = [], []
        for pid in sorted({c['placement_id'] for c in cameras})[:settings['placements']]:
            ids = [i for i, c in enumerate(cameras) if c['placement_id'] == pid and c['mother_frame_id'] % settings['stride'] == 0]
            for a, b in zip(ids[:-1], ids[1:]):
                na, nb = int(masks[a].sum()), int(masks[b].sum())
                if na and nb:
                    value = float((masks[a] & masks[b]).sum() / max(na, nb))
                    values.append(value)
                    pairs.append({'placement': pid, 'a': cameras[a]['mother_frame_id'], 'b': cameras[b]['mother_frame_id'], 'theta_a': cameras[a]['theta_unwrapped_deg'], 'visible_a': na, 'visible_b': nb, 'overlap': value})
        rows[level] = {'p10': float(np.quantile(values, .1)), 'minimum': min(values), 'median': float(np.median(values)), 'nonempty_adjacent_pairs': len(values), 'pairs': pairs}
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('--intervals', nargs='+', type=int, default=[192, 384, 768])
    args = parser.parse_args()
    sid = args.source
    assert sid in IDS
    cfg = config()
    gt = ROOT / f'private/gt/{sid}'
    folder = ROOT / f'reports/density_investigations/{sid}'
    folder.mkdir(parents=True, exist_ok=True)
    raw = np.load(gt / 'mesh.npz')
    original = load_json(gt / 'cameras.json')
    original_cameras = original['cameras']
    poses = load_json(gt / 'placements.json')['placements']
    metadata = load_json(gt / 'metadata.json')
    ref_path = ROOT / f'private/reference/{sid}/evaluation.npz'
    ref = np.load(ref_path)
    points, normals = ref['points'], ref['normals']
    scene = distance_scene(trimesh.Trimesh(raw['vertices'], raw['faces'], process=False))
    base_intervals = max(c['mother_frame_id'] for c in original_cameras)
    known = {}
    for camera, mask in zip(original_cameras, ref['camera_visibility']):
        known[(camera['placement_id'], camera['mother_frame_id'] / base_intervals)] = (camera, mask)
    before = {str(p.relative_to(ROOT)).replace('\\', '/'): {'sha256': file_hash(p), 'mtime_ns': p.stat().st_mtime_ns} for p in [gt / 'cameras.json', gt / 'mesh.npz', gt / 'placements.json', ref_path]}
    trials = []
    for intervals in args.intervals:
        assert intervals >= base_intervals and intervals % base_intervals == 0 and intervals % 4 == 0
        started = time.time()
        scan = {**cfg['scan'], 'intervals': intervals}
        cameras = sum([trajectory(raw['vertices'], p['T_table_from_object'], scan, original['resolution'], p['placement_id']) for p in poses], [])
        masks, reused = [], 0
        for index, cam in enumerate(cameras):
            position = (cam['placement_id'], cam['mother_frame_id'] / intervals)
            if position in known:
                prior, mask = known[position]
                for field in ['K', 'T_object_from_camera', 'T_table_from_camera', 'near_mm', 'far_mm', 'resolution']:
                    np.testing.assert_array_equal(cam[field], prior[field])
                reused += 1
            else:
                C = np.asarray(cam['T_object_from_camera'])
                eye = C[:3, 3]
                delta = points - eye
                ranges = np.linalg.norm(delta, axis=1)
                direction = delta / ranges[:, None]
                rays = np.column_stack([np.broadcast_to(eye, points.shape), direction]).astype(np.float32)
                hits = scene.cast_rays(o3d.core.Tensor(rays), nthreads=2)['t_hit'].numpy()
                first = abs(hits - ranges) < max(metadata['diagonal_mm'] * 2e-6, 1e-4)
                pc = delta @ C[:3, :3]
                K = np.asarray(cam['K'])
                uv = pc[:, :2] / pc[:, 2, None] * [K[0, 0], K[1, 1]] + [K[0, 2], K[1, 2]]
                inframe = (pc[:, 2] > 0) & (uv.min(1) >= 0) & (uv.max(1) < cam['resolution']) & (ranges >= cam['near_mm']) & (ranges <= cam['far_mm'])
                place = poses[cam['placement_id']]
                T = np.asarray(place['T_table_from_object'])
                height = (T[:3, :3] @ eye + T[:3, 3])[2]
                dz = direction @ T[2, :3]
                table = np.full(len(points), np.inf)
                down = dz < -1e-12
                table[down] = -height / dz[down]
                clear = table > ranges + place['epsilon_contact_mm']
                incidence = -np.einsum('ij,ij->i', direction, normals) >= np.cos(np.deg2rad(scan['incidence_deg']))
                mask = first & inframe & clear & incidence
                known[position] = (cam, mask)
            masks.append(mask)
            if index % 200 == 0:
                print(canonical_json({'source': sid, 'intervals': intervals, 'camera': index, 'total': len(cameras)}), flush=True)
        masks = np.asarray(masks)
        checks = summarize(cameras, masks, cfg['difficulty'])
        camera_path = folder / f'cameras_{intervals}.json'
        mask_path = folder / f'visibility_{intervals}.npz'
        atomic_json(camera_path, {**original, 'cameras': cameras, 'investigation_only': True, 'mother_intervals': intervals})
        atomic_npz(mask_path, camera_visibility=masks, points=points, normals=normals)
        trial = {'intervals': intervals, 'frames_per_placement': {level: intervals // settings['stride'] + 1 for level, settings in cfg['difficulty'].items()}, 'levels': checks, 'all_p10_pass': all(x['p10'] >= .5 for x in checks.values()), 'reused_exact_camera_visibility': reused, 'new_camera_visibility': len(cameras) - reused, 'seconds': time.time() - started, 'camera_file': str(camera_path.relative_to(ROOT)).replace('\\', '/'), 'camera_sha256': file_hash(camera_path), 'visibility_file': str(mask_path.relative_to(ROOT)).replace('\\', '/'), 'visibility_sha256': file_hash(mask_path)}
        trials.append(trial)
        print(canonical_json({'intervals': intervals, 'overlap_p10': {k: v['p10'] for k, v in checks.items()}, 'all_p10_pass': trial['all_p10_pass']}), flush=True)
    after = {name: {'sha256': file_hash(ROOT / name), 'mtime_ns': (ROOT / name).stat().st_mtime_ns} for name in before}
    assert after == before
    result = {'status': 'density_investigation_complete_not_production_acceptance', 'source_id': sid, 'reason': 'Thin-plate visibility changes near grazing azimuths; preserve the overlap threshold and all directions, test uniformly denser complete spirals.', 'method': 'Same fixed 30000 area-distributed surface samples, foreground first hit, table occlusion, unchanged incidence and two-direction minimum overlap; exact old camera matrices are reused.', 'quality_gate_unchanged': .5, 'protocol_config_sha256': digest(cfg), 'script_sha256': file_hash(Path(__file__)), 'production_inputs_unchanged': before, 'trials': trials, 'minimum_tested_passing_intervals': next((x['intervals'] for x in trials if x['all_p10_pass']), None), 'time': time.time()}
    atomic_json(folder / 'density_investigation.json', result)
    print(canonical_json({'source': sid, 'minimum_tested_passing_intervals': result['minimum_tested_passing_intervals']}), flush=True)


if __name__ == '__main__':
    main()
