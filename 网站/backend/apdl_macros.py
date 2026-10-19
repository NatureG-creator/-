"""Read-only MAPDL checks and output controls; never change model physics.

Command formats follow the ANSYS 2024 R2 Command Reference: SHPP,
OUTRES, ETABLE, *VGET (POST1 ELEM ETAB), and *VSCFUN (LMAX).
Generated checks are executable instructions, not evidence of execution.
"""
from __future__ import annotations

from .apdl_diagnostics import normalise_output_options


DIAGNOSTICS_SCHEMA_VERSION = 2


def _number(value: float) -> str:
    return format(float(value), '.17g')


def _conditions(conditions: list[str]) -> list[str]:
    lines = []
    for condition in conditions:
        lines += ['*IF,'+condition+',THEN', 'ac_pass=0', '*ENDIF']
    return lines


def _self_check_row(*, append: bool) -> list[str]:
    return [
        '*CFOPEN,apdl_self_check,csv'+(',,APPEND' if append else ''),
        '! No header: stage,node_count,element_count,fixed_count,loaded_count,passed.',
        '*VWRITE,ac_stage,ac_nn,ac_ne,ac_nf,ac_nl,ac_pass',
        "(F12.0,5(',',F12.0))", '*CFCLOS',
        '*IF,ac_pass,NE,1,THEN', '/COM,APDL_SELF_CHECK_FAILED',
        '/EXIT,NOSAVE', '*ENDIF', 'ALLSEL,ALL',
    ]


def diagnostic_macros(geometry: dict) -> dict[str, str]:
    """Check actual database entities and grips without changing constraints."""
    o = geometry['options']
    nodes = geometry['stats']['node_count']
    elements = geometry['stats']['element_count']
    direction = o.get('tensile_direction', 'X')
    axis = 'X' if direction == 'X' else 'Y'
    axis_index = 1 if direction == 'X' else 2
    axial_coords = geometry['x'] if direction == 'X' else geometry['y']
    x0, x1 = axial_coords[0], axial_coords[-1]
    axial_spacing = o['dx_mm'] if direction == 'X' else o['dy_mm']
    tolerance = geometry['stats'].get('grip_tolerance_mm', max(abs(axial_spacing) * .01, 1e-12))
    grip_nodes = int(sum(abs(float(node[axis_index]) - x0) <= tolerance
                         for node in geometry['nodes']))
    loaded_nodes = int(sum(abs(float(node[axis_index]) - x1) <= tolerance
                           for node in geometry['nodes']))
    mesh = [
        '! Actual imported database; contiguous IDs expected from nodes/elements.dat.',
        'ALLSEL,ALL', 'ac_stage=1', 'ac_pass=1', 'ac_nf=-1', 'ac_nl=-1',
        '*GET,ac_nn,NODE,0,COUNT', '*GET,ac_ne,ELEM,0,COUNT',
        '*GET,ac_nmin,NODE,0,NUM,MIN', '*GET,ac_nmax,NODE,0,NUM,MAX',
        '*GET,ac_emin,ELEM,0,NUM,MIN', '*GET,ac_emax,ELEM,0,NUM,MAX',
    ]
    mesh += _conditions([f'ac_nn,NE,{nodes}', f'ac_ne,NE,{elements}',
                         'ac_nmin,NE,1', f'ac_nmax,NE,{nodes}',
                         'ac_emin,NE,1', f'ac_emax,NE,{elements}'])
    mesh += _self_check_row(append=False)
    boundary = [
        '! Actual grip components; restore selections and the default selection tolerance.',
        'ALLSEL,ALL', 'CSYS,0', 'ac_stage=2', 'ac_pass=1',
        '*GET,ac_nn,NODE,0,COUNT', '*GET,ac_ne,ELEM,0,COUNT',
        'SELTOL,'+_number(tolerance),
        'NSEL,NONE', 'CMSEL,S,GRIP_FIXED', '*GET,ac_nf,NODE,0,COUNT',
        f'NSEL,U,LOC,{axis},'+_number(axial_coords[0]), '*GET,ac_fbad,NODE,0,COUNT',
        'NSEL,NONE', 'CMSEL,S,GRIP_LOADED', '*GET,ac_nl,NODE,0,COUNT',
        f'NSEL,U,LOC,{axis},'+_number(axial_coords[-1]), '*GET,ac_lbad,NODE,0,COUNT',
        'NSEL,NONE', 'CMSEL,S,GRIP_FIXED', 'CMSEL,R,GRIP_LOADED',
        '*GET,ac_overlap,NODE,0,COUNT', 'SELTOL',
    ]
    boundary += _conditions([f'ac_nn,NE,{nodes}', f'ac_ne,NE,{elements}',
                             f'ac_nf,NE,{grip_nodes}', f'ac_nl,NE,{loaded_nodes}',
                             'ac_fbad,NE,0', 'ac_lbad,NE,0', 'ac_overlap,NE,0'])
    boundary += _self_check_row(append=True)
    quality = [
        '! Raw ANSYS checks; file presence alone does not certify mesh quality.',
        'ALLSEL,ALL', '/OUTPUT,mesh_quality_report,txt',
        'CHECK', 'SHPP,STATUS', 'SHPP,SUMMARY', '/OUTPUT', 'ALLSEL,ALL',
    ]
    if o.get('mesh_type', 'solid185_hex') != 'solid185_hex':
        quality = [
            '! Keep native shape thresholds; summarize warnings without one message per element.',
            'ALLSEL,ALL', '/OUTPUT,mesh_quality_report,txt', 'SHPP,STATUS', 'SHPP,SUMMARY',
            'ESCHECK,ESEL,ERR', '*GET,ac_nshape,ELEM,0,COUNT',
            '*VWRITE,ac_nshape', "('APDL_SHAPE_ERROR_COUNT=',F12.0)", '/OUTPUT',
            '*IF,ac_nshape,GT,0,THEN', '/COM,APDL_SELF_CHECK_FAILED: SHAPE_ERRORS',
            '/EXIT,NOSAVE', '*ENDIF', 'ALLSEL,ALL',
        ]
    return {'mesh_quality.mac': '\n'.join(quality),
            'mesh_self_check.mac': '\n'.join(mesh),
            'boundary_self_check.mac': '\n'.join(boundary)}


def output_commands(options: dict) -> list[str]:
    """Keep curve history; selected-time requests safely use full output."""
    policy = normalise_output_options(options)
    if policy['result_save_mode'] == 'all':
        return ['OUTRES,ALL,ALL']
    if policy['result_save_mode'] == 'selected':
        # MAPDL 2025 R2 rejects mixing key-time arrays with ALL frequency.
        # Preserve every curve/material sample without changing solver stepping.
        return ['OUTRES,ALL,ALL']
    lines = ['OUTRES,ALL,NONE', 'OUTRES,NSOL,ALL', 'OUTRES,RSOL,ALL']
    lines.append('OUTRES,ESOL,LAST')
    # ESOL includes NLDAT: override it afterwards so material screening has every set.
    if options['material_model'] == 'multilinear_iso':
        lines.append('OUTRES,NLDAT,ALL')
    return lines


def material_coverage_commands() -> list[str]:
    """Screen every result set using the maximum element nodal NL,EPEQ proxy.

    Mesh self-check guarantees element IDs 1..mc_ne. *VGET loops on IDs;
    LMAX therefore gives the element ID of a maximum in that array.
    """
    return [
        '! Element nodal MAX proxy; not a verified integration-point maximum.',
        'ALLSEL,ALL', 'CSYS,0', '*GET,mc_ne,ELEM,0,COUNT',
        '*DIM,mc_values,ARRAY,mc_ne', '*CFOPEN,material_coverage_history,csv',
        '! No header: time,max_element_nodal_epeq,element_id,centroid_x,y,z.',
        '*DO,iset,1,nsets', 'SET,,,,,,,iset', '*GET,tm,ACTIVE,0,SET,TIME',
        'ALLSEL,ALL', 'ETABLE,ERAS', 'ETABLE,MCPEEQ,NL,EPEQ,MAX',
        '*VGET,mc_values(1),ELEM,1,ETAB,MCPEEQ',
        '*VSCFUN,mc_id,LMAX,mc_values(1)', 'mc_max=mc_values(mc_id)',
        '*GET,mc_x,ELEM,mc_id,CENT,X', '*GET,mc_y,ELEM,mc_id,CENT,Y',
        '*GET,mc_z,ELEM,mc_id,CENT,Z',
        '*VWRITE,tm,mc_max,mc_id,mc_x,mc_y,mc_z',
        "(E19.11,5(',',E19.11))", '*ENDDO', '*CFCLOS', 'ALLSEL,ALL',
    ]
