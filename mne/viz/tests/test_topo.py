# Authors: The MNE-Python contributors.
# License: BSD-3-Clause
# Copyright the MNE-Python contributors.

from collections import namedtuple
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest

from mne import Epochs, compute_proj_evoked, read_cov, read_events
from mne.channels import read_layout
from mne.io import read_raw_fif
from mne.time_frequency.tfr import AverageTFRArray
from mne.utils import _record_warnings
from mne.viz import (
    _get_presser,
    mne_analyze_colormap,
    plot_evoked_topo,
    plot_topo_image_epochs,
)
from mne.viz.evoked import _line_plot_onselect
from mne.viz.topo import _imshow_tfr, _plot_update_evoked_topo_proj, iter_topography
from mne.viz.utils import _fake_click, _fake_keypress

base_dir = Path(__file__).parents[2] / "io" / "tests" / "data"
evoked_fname = base_dir / "test-ave.fif"
raw_fname = base_dir / "test_raw.fif"
event_name = base_dir / "test-eve.fif"
cov_fname = base_dir / "test-cov.fif"
event_id, tmin, tmax = 1, -0.2, 0.2
layout = read_layout("Vectorview-all")


def _get_events():
    """Get events."""
    return read_events(event_name)


def _get_picks(raw):
    """Get picks."""
    return [0, 1, 2, 6, 7, 8, 306, 340, 341, 342]  # take a only few channels


def _get_epochs():
    """Get epochs."""
    raw = read_raw_fif(raw_fname)
    raw.add_proj([], remove_existing=True)
    events = _get_events()
    picks = _get_picks(raw)
    # bad proj warning
    epochs = Epochs(raw, events[:10], event_id, tmin, tmax, picks=picks)
    return epochs


def _get_epochs_delayed_ssp():
    """Get epochs with delayed SSP."""
    raw = read_raw_fif(raw_fname)
    events = _get_events()
    picks = _get_picks(raw)
    reject = dict(mag=4e-12)
    with pytest.warns(RuntimeWarning, match="projection"):
        epochs_delayed_ssp = Epochs(
            raw,
            events[:10],
            event_id,
            tmin,
            tmax,
            picks=picks,
            proj="delayed",
            reject=reject,
        )
    return epochs_delayed_ssp


def test_plot_joint():
    """Test joint plot."""
    evoked = _get_epochs().average()
    evoked.plot_joint(ts_args=dict(time_unit="s"), topomap_args=dict(time_unit="s"))

    def return_inds(d):  # to test function kwarg to zorder arg of evoked.plot
        return list(range(d.shape[0]))

    evoked.plot_joint(
        title="test",
        topomap_args=dict(contours=0, res=8, time_unit="ms"),
        ts_args=dict(spatial_colors=True, zorder=return_inds, time_unit="s"),
    )
    with pytest.raises(ValueError, match="If one of `ts_args` and"):
        evoked.plot_joint(ts_args=dict(axes=True, time_unit="s"))

    axes = plt.subplots(nrows=3)[-1].flatten().tolist()
    evoked.plot_joint(
        times=[0],
        picks=[6, 7, 8],
        ts_args=dict(axes=axes[0]),
        topomap_args={"axes": axes[1:], "time_unit": "s"},
    )
    with pytest.raises(ValueError, match="of length 4"):
        evoked.plot_joint(
            picks=[6, 7, 8],
            ts_args=dict(axes=axes[0]),
            topomap_args=dict(axes=axes[2:]),
        )
    plt.close("all")

    # test proj options
    assert len(evoked.info["projs"]) == 0
    evoked.pick(picks="meg")
    evoked.add_proj(compute_proj_evoked(evoked, n_mag=1, n_grad=1, meg="combined"))
    assert len(evoked.info["projs"]) == 1
    with pytest.raises(ValueError, match="must match ts_args"):
        evoked.plot_joint(ts_args=dict(proj=True), topomap_args=dict(proj=False))
    evoked.plot_joint(
        ts_args=dict(proj="reconstruct"), topomap_args=dict(proj="reconstruct")
    )
    plt.close("all")

    # test sEEG (gh:8733)
    evoked.del_proj().pick("mag")  # avoid overlapping positions error
    mapping = {ch_name: "seeg" for ch_name in evoked.ch_names}
    evoked.set_channel_types(mapping, on_unit_change="ignore")
    evoked.plot_joint()

    # test DBS (gh:8739)
    evoked = _get_epochs().average().pick("mag")
    mapping = {ch_name: "dbs" for ch_name in evoked.ch_names}
    evoked.set_channel_types(mapping, on_unit_change="ignore")
    evoked.plot_joint()
    plt.close("all")


def test_plot_topo():
    """Test plotting of ERP topography."""
    # Show topography
    evoked = _get_epochs().average()
    # should auto-find layout
    plot_evoked_topo([evoked, evoked], merge_grads=True, background_color="w")

    plot_evoked_topo(
        [evoked, evoked], merge_grads=True, background_color="w", color="blue"
    )

    # test legend colors
    colors = ["red", "blue"]
    fig = plot_evoked_topo([evoked, evoked], merge_grads=True, color=colors)
    legend = fig.axes[0].get_legend()
    legend_colors = [
        line.properties()["markeredgecolor"] for line in legend.get_lines()
    ]
    assert legend_colors == colors

    with pytest.raises(ValueError, match="must be .*tuple, list, str,.*"):
        plot_evoked_topo(
            [evoked, evoked], merge_grads=True, color=np.array(["blue", "red"])
        )

    picked_evoked = evoked.copy().pick(evoked.ch_names[:3])
    picked_evoked_eeg = evoked.copy().pick(picks="eeg")
    picked_evoked_eeg.pick(picked_evoked_eeg.ch_names[:3])

    # test scaling
    for ylim in [dict(mag=[-600, 600]), None]:
        plot_evoked_topo([picked_evoked] * 2, layout, ylim=ylim)

    for evo in [evoked, [evoked, picked_evoked]]:
        pytest.raises(ValueError, plot_evoked_topo, evo, layout, color=["y", "b"])

    evoked_delayed_ssp = _get_epochs_delayed_ssp().average()
    ch_names = evoked_delayed_ssp.ch_names[:3]  # make it faster
    picked_evoked_delayed_ssp = evoked_delayed_ssp.pick(ch_names)
    fig = plot_evoked_topo(picked_evoked_delayed_ssp, layout, proj="interactive")
    func = _get_presser(fig)
    event = namedtuple("Event", ["inaxes", "xdata", "ydata"])
    func(
        event(
            inaxes=fig.axes[0],
            xdata=fig.axes[0]._mne_axs[0].pos[0],
            ydata=fig.axes[0]._mne_axs[0].pos[1],
        )
    )
    func(event(inaxes=fig.axes[0], xdata=0, ydata=0))
    params = dict(
        evokeds=[picked_evoked_delayed_ssp],
        times=picked_evoked_delayed_ssp.times,
        fig=fig,
        projs=picked_evoked_delayed_ssp.info["projs"],
    )
    bools = [True] * len(params["projs"])
    with pytest.warns(RuntimeWarning, match="projection"):
        _plot_update_evoked_topo_proj(params, bools)

    # should auto-generate layout
    plot_evoked_topo(
        picked_evoked_eeg.copy(),
        fig_background=np.zeros((4, 3, 3)),
        proj=True,
        background_color="k",
    )
    # Test RMS plot of grad pairs
    picked_evoked.plot_topo(merge_grads=True, background_color="w")
    plt.close("all")
    for ax, idx in iter_topography(evoked.info, legend=True):
        ax.plot(evoked.data[idx], color="red")
        # test status bar message
        if idx != -1:
            assert evoked.ch_names[idx] in ax.format_coord(0.5, 0.5)
    assert idx == -1
    plt.close("all")
    cov = read_cov(cov_fname)
    cov["projs"] = []
    evoked.pick(picks="meg").plot_topo(noise_cov=cov)
    plt.close("all")

    # Test exclude parameter
    exclude = ["MEG 0112"]
    fig = picked_evoked.plot_topo(exclude=exclude)
    n_axes_expected = len(picked_evoked.info["ch_names"]) - len(exclude)
    n_axes_found = len(fig.axes[0].lines)
    assert n_axes_found == n_axes_expected

    # test plot_topo
    evoked.plot_topo()  # should auto-find layout
    _line_plot_onselect(0, 200, ["mag", "grad"], evoked.info, evoked.data, evoked.times)
    plt.close("all")

    for ax, idx in iter_topography(evoked.info):  # brief test with false
        ax.plot([0, 1, 2])
        break
    plt.close("all")

    # Test plot_topo with selection of channels enabled.
    fig = evoked.plot_topo(select=True)
    ax = fig.axes[0]
    _fake_click(fig, ax, (0.05, 0.62), xform="data")
    _fake_click(fig, ax, (0.2, 0.62), xform="data", kind="motion")
    _fake_click(fig, ax, (0.2, 0.7), xform="data", kind="motion")
    _fake_click(fig, ax, (0.05, 0.7), xform="data", kind="motion")
    _fake_click(fig, ax, (0.05, 0.7), xform="data", kind="release")
    assert fig.lasso.selection == ["MEG 0113", "MEG 0112", "MEG 0111"]


def test_plot_topo_nirs(fnirs_evoked):
    """Test plotting of ERP topography for nirs data."""
    fnirs_evoked.pick(picks="hbo")
    fig = plot_evoked_topo(fnirs_evoked)
    assert len(fig.axes) == 1
    plt.close("all")


def test_plot_topo_single_ch():
    """Test single channel topoplot with time cursor."""
    evoked = _get_epochs().average()
    evoked2 = evoked.copy()
    # test plotting several evokeds on different time grids
    evoked.crop(-0.19, 0)
    evoked2.crop(0.05, 0.19)
    fig = plot_evoked_topo([evoked, evoked2], background_color="w")
    # test status bar message
    ax = plt.gca()
    assert "MEG 0113" in ax.format_coord(0.065, 0.63)
    num_figures_before = len(plt.get_fignums())
    _fake_click(fig, fig.axes[0], (0.08, 0.65))
    assert num_figures_before + 1 == len(plt.get_fignums())
    fig = plt.gcf()
    ax = plt.gca()
    _fake_click(fig, ax, (0.5, 0.5), kind="motion")  # cursor should appear
    assert isinstance(ax._cursorline, matplotlib.lines.Line2D)
    _fake_click(fig, ax, (1.5, 1.5), kind="motion")  # cursor should disappear
    assert ax._cursorline is None
    plt.close("all")


def test_plot_topo_image_epochs():
    """Test plotting of epochs image topography."""
    title = "ERF images - MNE sample data"
    epochs = _get_epochs()
    epochs.load_data()
    cmap = mne_analyze_colormap(format="matplotlib")
    data_min = epochs._data.min()
    plt.close("all")
    fig = plot_topo_image_epochs(
        epochs, sigma=0.5, vmin=-200, vmax=200, colorbar=True, title=title, cmap=cmap
    )
    assert epochs._data.min() == data_min
    num_figures_before = len(plt.get_fignums())
    _fake_click(fig, fig.axes[0], (0.08, 0.64))
    assert num_figures_before + 1 == len(plt.get_fignums())
    # test for auto-showing a colorbar when only 1 sensor type
    ep = epochs.copy().pick(picks="eeg")
    fig = plot_topo_image_epochs(ep, vmin=None, vmax=None, colorbar=None, cmap=cmap)
    ax = [x for x in fig.get_children() if isinstance(x, matplotlib.axes.Axes)]
    # include inset axes (newer MPL)
    ax.extend(
        y for x in ax for y in x.get_children() if isinstance(y, matplotlib.axes.Axes)
    )
    qm_cmap = [
        y.cmap
        for x in ax
        for y in x.get_children()
        if isinstance(y, matplotlib.collections.QuadMesh)
    ]
    assert len(qm_cmap) >= 1
    assert qm_cmap[0] is cmap


def test_plot_topo_select():
    """Test selecting sensors in an ERP topography plot."""
    # Show topography
    evoked = _get_epochs().average()
    fig = plot_evoked_topo(evoked, select=True)
    ax = fig.axes[0]

    # Lasso select 3 out of the 6 sensors.
    _fake_click(fig, ax, (0.05, 0.5), xform="data")
    _fake_click(fig, ax, (0.2, 0.5), xform="data", kind="motion")
    _fake_click(fig, ax, (0.2, 0.6), xform="data", kind="motion")
    _fake_click(fig, ax, (0.05, 0.6), xform="data", kind="motion")
    _fake_click(fig, ax, (0.05, 0.5), xform="data", kind="motion")
    _fake_click(fig, ax, (0.05, 0.5), xform="data", kind="release")
    assert fig.lasso.selection == ["MEG 0132", "MEG 0133", "MEG 0131"]

    # Add another sensor with a single click.
    _fake_keypress(fig, "control")
    _fake_click(fig, ax, (0.11, 0.65), xform="data")
    _fake_click(fig, ax, (0.21, 0.65), xform="data", kind="release")
    _fake_keypress(fig, "control", kind="release")
    assert fig.lasso.selection == ["MEG 0111", "MEG 0132", "MEG 0133", "MEG 0131"]


def test_plot_tfr_topo():
    """Test plotting of TFR data."""
    epochs = _get_epochs()
    n_freqs = 3
    nave = 1
    data = np.random.RandomState(0).randn(
        len(epochs.ch_names), n_freqs, len(epochs.times)
    )
    tfr = AverageTFRArray(
        info=epochs.info,
        data=data,
        times=epochs.times,
        freqs=np.arange(n_freqs),
        nave=nave,
    )
    plt.close("all")
    fig = tfr.plot_topo(baseline=(None, 0), mode="ratio", vmin=0.0, vmax=14.0)

    # test complex
    tfr.data = tfr.data * (1 + 1j)
    plt.close("all")
    fig = tfr.plot_topo(baseline=(None, 0), mode="ratio", vmin=0.0, vmax=14.0)

    # test opening tfr by clicking
    num_figures_before = len(plt.get_fignums())
    # could use np.reshape(fig.axes[-1].images[0].get_extent(), (2, 2)).mean(1)
    with _record_warnings(), pytest.warns(RuntimeWarning, match="not masking"):
        _fake_click(fig, fig.axes[0], (0.08, 0.65))
    assert num_figures_before + 1 == len(plt.get_fignums())
    plt.close("all")

    tfr.plot([4], baseline=(None, 0), mode="ratio", show=False, title="foo")
    pytest.raises(ValueError, tfr.plot, [4], yscale="lin", show=False)

    # nonuniform freqs
    freqs = np.logspace(*np.log10([3, 10]), num=3)
    tfr = AverageTFRArray(
        info=epochs.info, data=data, times=epochs.times, freqs=freqs, nave=nave
    )
    fig = tfr.plot([4], baseline=(None, 0), mode="mean", vlim=(None, 14.0), show=False)
    assert fig[0].axes[0].get_yaxis().get_scale() == "log"

    # one timesample
    tfr = AverageTFRArray(
        info=epochs.info,
        data=data[:, :, [0]],
        times=epochs.times[[1]],
        freqs=freqs,
        nave=nave,
    )

    with _record_warnings():  # matplotlib equal left/right
        tfr.plot([4], baseline=None, vlim=(None, 14.0), show=False, yscale="linear")

    # one frequency bin, log scale required: as it doesn't make sense
    # to plot log scale for one value, we test whether yscale is set to linear
    vmin, vmax = 0.0, 2.0
    fig, ax = plt.subplots()
    tmin, tmax = epochs.times[0], epochs.times[-1]
    with _record_warnings(), pytest.warns(RuntimeWarning, match="not masking"):
        _imshow_tfr(
            ax,
            3,
            tmin,
            tmax,
            vmin,
            vmax,
            None,
            tfr=data[:, [0], :],
            freq=freqs[[-1]],
            x_label=None,
            y_label=None,
            colorbar=False,
            cmap=("RdBu_r", True),
            yscale="log",
        )
    fig = plt.gcf()
    assert fig.axes[0].get_yaxis().get_scale() == "linear"

    # ValueError when freq[0] == 0 and yscale == 'log'
    these_freqs = freqs[:3].copy()
    these_freqs[0] = 0
    with _record_warnings(), pytest.warns(RuntimeWarning, match="not masking"):
        pytest.raises(
            ValueError,
            _imshow_tfr,
            ax,
            3,
            tmin,
            tmax,
            vmin,
            vmax,
            None,
            tfr=data[:, :3, :],
            freq=these_freqs,
            x_label=None,
            y_label=None,
            colorbar=False,
            cmap=("RdBu_r", True),
            yscale="log",
        )
