# Authors: The MNE-Python contributors.
# License: BSD-3-Clause
# Copyright the MNE-Python contributors.

from ..utils import logger
from .constants import FIFF
from .tag import find_tag, has_tag
from .write import (
    end_block,
    start_block,
    write_float_matrix,
    write_int,
    write_name_list,
)


def _transpose_named_matrix(mat):
    """Transpose mat inplace (no copy)."""
    mat["nrow"], mat["ncol"] = mat["ncol"], mat["nrow"]
    mat["row_names"], mat["col_names"] = mat["col_names"], mat["row_names"]
    mat["data"] = mat["data"].T


def _read_named_matrix(fid, node, matkind, indent="    ", transpose=False):
    """Read named matrix from the given node.

    Parameters
    ----------
    fid : file
        The opened file descriptor.
    node : dict
        The node in the tree.
    matkind : int
        The type of matrix.
    transpose : bool
        If True, transpose the matrix. Default is False.
    %(verbose)s

    Returns
    -------
    mat: dict
        The matrix data
    """
    #   Descend one level if necessary
    if node["block"] != FIFF.FIFFB_MNE_NAMED_MATRIX:
        for k in range(node["nchild"]):
            if node["children"][k]["block"] == FIFF.FIFFB_MNE_NAMED_MATRIX:
                if has_tag(node["children"][k], matkind):
                    node = node["children"][k]
                    break
        else:
            logger.info(
                f"{indent}Desired named matrix (kind = {matkind}) not available"
            )
            return None
    else:
        if not has_tag(node, matkind):
            logger.info(
                f"{indent}Desired named matrix (kind = {matkind}) not available"
            )
            return None

    #   Read everything we need
    tag = find_tag(fid, node, matkind)
    if tag is None:
        raise ValueError("Matrix data missing")
    else:
        data = tag.data

    nrow, ncol = data.shape
    tag = find_tag(fid, node, FIFF.FIFF_MNE_NROW)
    if tag is not None and tag.data != nrow:
        raise ValueError(
            "Number of rows in matrix data and FIFF_MNE_NROW tag do not match"
        )

    tag = find_tag(fid, node, FIFF.FIFF_MNE_NCOL)
    if tag is not None and tag.data != ncol:
        raise ValueError(
            "Number of columns in matrix data and FIFF_MNE_NCOL tag do not match"
        )

    tag = find_tag(fid, node, FIFF.FIFF_MNE_ROW_NAMES)
    row_names = tag.data.split(":") if tag is not None else []

    tag = find_tag(fid, node, FIFF.FIFF_MNE_COL_NAMES)
    col_names = tag.data.split(":") if tag is not None else []

    mat = dict(
        nrow=nrow, ncol=ncol, row_names=row_names, col_names=col_names, data=data
    )
    if transpose:
        _transpose_named_matrix(mat)
    return mat


def write_named_matrix(fid, kind, mat):
    """Write named matrix from the given node.

    Parameters
    ----------
    fid : file
        The opened file descriptor.
    kind : int
        The kind of the matrix.
    matkind : int
        The type of matrix.
    """
    # let's save ourselves from disaster
    n_tot = mat["nrow"] * mat["ncol"]
    if mat["data"].size != n_tot:
        ratio = n_tot / float(mat["data"].size)
        if n_tot < mat["data"].size and ratio > 0:
            ratio = 1 / ratio
        raise ValueError(
            f"Cannot write matrix: row ({mat['nrow']}) and column ({mat['ncol']}) "
            f"total element ({n_tot}) mismatch with data size ({mat['data'].size}), "
            f"appears to be off by a factor of {ratio:g}x"
        )
    start_block(fid, FIFF.FIFFB_MNE_NAMED_MATRIX)
    write_int(fid, FIFF.FIFF_MNE_NROW, mat["nrow"])
    write_int(fid, FIFF.FIFF_MNE_NCOL, mat["ncol"])

    if len(mat["row_names"]) > 0:
        # let's prevent unintentional stupidity
        if len(mat["row_names"]) != mat["nrow"]:
            raise ValueError('len(mat["row_names"]) != mat["nrow"]')
        write_name_list(fid, FIFF.FIFF_MNE_ROW_NAMES, mat["row_names"])

    if len(mat["col_names"]) > 0:
        # let's prevent unintentional stupidity
        if len(mat["col_names"]) != mat["ncol"]:
            raise ValueError('len(mat["col_names"]) != mat["ncol"]')
        write_name_list(fid, FIFF.FIFF_MNE_COL_NAMES, mat["col_names"])

    write_float_matrix(fid, kind, mat["data"])
    end_block(fid, FIFF.FIFFB_MNE_NAMED_MATRIX)
