"""Versioned per-source uniform sampling density, with stable old noise streams.

Only acquisition scheduling and public metadata use this module. Reconstruction
continues to consume measured ranges and camera matrices without CAD access.
"""
from fractions import Fraction
from .common import ROOT, config, digest, file_hash, load_json, IDS

POLICY_PATH = ROOT/'configs/sampling_density_v2.json'


def sampling_policy():
    if not POLICY_PATH.exists():
        freeze = ROOT/'reports/protocol_freeze.json'
        if freeze.exists() and load_json(freeze).get('physical_sampling_policy'):
            raise RuntimeError('The active sampling policy is missing; do not fall back to a different density')
        return None
    policy = load_json(POLICY_PATH)
    if policy.get('status') != 'frozen':
        raise RuntimeError('Sampling density policy must pass controls before production')
    freeze = ROOT/'reports/protocol_freeze.json'
    binding = load_json(freeze).get('physical_sampling_policy') if freeze.exists() else None
    if binding:
        assert binding['path'] == 'configs/sampling_density_v2.json'
        assert file_hash(POLICY_PATH) == binding['sha256'], 'Sampling policy changed after the physical freeze'
    cfg = config()
    assert policy['schema'] == 'uniform_sampling_density_v2'
    assert policy['protocol'] == 'physical_scan_v2_overlap_density'
    assert policy['base_config_sha256'] == digest(cfg)
    assert policy['base_intervals'] == cfg['scan']['intervals']
    assert policy['quality_gates_changed'] is False
    assert policy['overlap_p10_min'] == .5
    assert policy['allowed_multipliers'] == [1,2,4,8]
    for sid, intervals in policy['source_intervals'].items():
        assert sid in IDS and isinstance(intervals,int)
        assert intervals % policy['base_intervals'] == 0 and intervals % 4 == 0
        assert intervals // policy['base_intervals'] in policy['allowed_multipliers']
    return policy


def source_scan_settings(source_id):
    settings = dict(config()['scan'])
    policy = sampling_policy()
    if policy is not None:
        settings['intervals'] = policy['source_intervals'].get(source_id,policy['base_intervals'])
    return settings


def noise_frame_key(camera, scan_settings):
    """Old physical positions retain the original integer RNG stream identifier.

New positions use an exact rational parameter on the original mother grid.
This prevents densification from silently changing noise at old positions.
"""
    base = config()['scan']['intervals']
    parameter = Fraction(int(camera['mother_frame_id'])*base,int(scan_settings['intervals']))
    return parameter.numerator if parameter.denominator == 1 else f'base_grid:{parameter.numerator}/{parameter.denominator}'


def case_sampling_contract(source_id, level, placement_count):
    cfg = config()
    scan = source_scan_settings(source_id)
    policy = sampling_policy()
    stride = cfg['difficulty'][level]['stride']
    return {
        'schema':'sampling_contract_v2',
        'protocol':policy['protocol'] if policy else cfg['protocol'],
        'base_protocol':cfg['protocol'],
        'base_config_sha256':digest(cfg),
        'sampling_policy_sha256':file_hash(POLICY_PATH) if policy else None,
        'mother_intervals':scan['intervals'],
        'turns_per_placement':scan['turns'],
        'elevation_top_deg':scan['beta_top_deg'],
        'elevation_bottom_deg':scan['beta_bottom_deg'],
        'difficulty':level,
        'stride':stride,
        'actual_placements':placement_count,
        'frames_per_placement':scan['intervals']//stride+1,
        'noise_parameter_grid_intervals':cfg['scan']['intervals'],
        'noise_frame_key':'integer on original grid, otherwise base_grid:numerator/denominator',
        'noise_algorithm':scan['noise_algorithm'],
        'noise_and_reconstruction_settings_changed':False,
    }


def verify_case_sampling_contract(record,out):
    path = out/'sampling_contract.json'
    expected = case_sampling_contract(record['source_id'],record['level'],record['placement_count'])
    assert load_json(path) == expected, 'Public sampling contract differs from the active physical protocol'
    assert record['sampling_contract_sha256'] == file_hash(path), 'Case sampling-contract hash differs'
    assert record['protocol'] == expected['protocol'], 'Case physical-protocol version differs'
    return expected
