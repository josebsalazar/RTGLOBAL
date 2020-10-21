import datetime
import numpy
import matplotlib
from matplotlib import pyplot, cm
import pandas
import textwrap
import typing

import arviz
import pymc3

from . import assumptions
from . import model
from . import preprocessing


def plot_vlines(
    ax: matplotlib.axes.Axes,
    vlines: preprocessing.NamedDates,
    alignment: str,
) -> None:
    """ Helper function for marking special events with labeled vertical lines.

    Parameters
    ----------
    ax : matplotlib.axes.Axes
        the subplot to draw into
    vlines : dict of { datetime : label }
        the dates and labels for the lines
    alignment : str
        one of { "top", "bottom" }
    """
    ymin, ymax = ax.get_ylim()
    xmin, xmax = ax.get_xlim()
    for x, label in vlines.items():
        if xmin <= ax.xaxis.convert_xunits(x) <= xmax:
            label = textwrap.shorten(label, width=20, placeholder="...")
            ax.axvline(x, color="gray", linestyle=":")
            if alignment == 'top':
                y = ymin+0.98*(ymax-ymin)
            elif alignment == 'bottom':
                y = ymin+0.02*(ymax-ymin)
            else:
                raise ValueError(f"Unsupported alignment: '{alignment}'")
            ax.text(
                x, y,
                s=f'{label}\n',
                color="gray",
                rotation=90,
                horizontalalignment="center",
                verticalalignment=alignment,                
            )
    return None


def plot_testcount_forecast(
    result: pandas.Series,
    m: preprocessing.fbprophet.Prophet,
    forecast: pandas.DataFrame,
    considered_holidays: preprocessing.NamedDates, *,
    ax: matplotlib.axes.Axes=None
) -> matplotlib.axes.Axes:
    """ Helper function for plotting the detailed testcount forecasting result.

    Parameters
    ----------
    result : pandas.Series
        the date-indexed series of smoothed/predicted testcounts
    m : fbprophet.Prophet
        the prophet model
    forecast : pandas.DataFrame
        contains the prophet model prediction
    holidays : dict of { datetime : str }
        dictionary of the holidays that were used in the model
    ax : optional, matplotlib.axes.Axes
        an existing subplot to use

    Returns
    -------
    ax : matplotlib.axes.Axes
        the (created) subplot that was plotted into
    """
    if not ax:
        _, ax = pyplot.subplots(figsize=(13.4, 6))
    m.plot(forecast[forecast.ds >= m.history.set_index('ds').index[0]], ax=ax)
    ax.set_ylim(bottom=0)
    ax.set_xlim(pandas.to_datetime('2020-03-01'))
    plot_vlines(ax, considered_holidays, alignment='bottom')
    ax.legend(frameon=False, loc='upper left', handles=[
        ax.scatter([], [], color='black', label='training data'),
        ax.plot([], [], color='blue', label='prediction')[0],
        ax.plot(result.index, result.values, color='orange', label='result')[0],
    ])
    ax.set_ylabel('total tests')
    ax.set_xlabel('')
    return ax


def plot_testcount_components(
    m: preprocessing.fbprophet.Prophet,
    forecast: pandas.DataFrame,
    considered_holidays: preprocessing.NamedDates
) -> typing.Tuple[matplotlib.figure.Figure, typing.Sequence[matplotlib.axes.Axes]]:
    """ Helper function to plot components of the Prophet forecast.

    Parameters
    ----------
    m : fbprophet.Prophet
        the prophet model
    forecast : pandas.DataFrame
        contains the prophet model prediction
    considered_holidays : preprocesssing.NamedDates
        the dictionary of named dates that were considered by the prophet model

    Returns
    -------
    figure : matplotlib.figure.Figure
        the created figure object
    axs : array of matplotlib Axes
        the subplots within the figure
    """
    fig = m.plot_components(
        forecast[forecast.ds >= m.history.set_index('ds').index[0]],
        figsize=(13.4, 8),
        weekly_start=1,
    )
    axs = fig.axes
    for ax in axs:
        ax.set_xlabel('')
    axs[0].set_ylim(0)
    axs[1].set_ylim(-1)
    plot_vlines(axs[0], considered_holidays, alignment='bottom')
    plot_vlines(axs[1], {k:'' for k in considered_holidays.keys()}, alignment='bottom')
    axs[0].set_xlim(pandas.to_datetime('2020-03-01'))
    axs[1].set_xlim(pandas.to_datetime('2020-03-01'))
    return fig, axs


def plot_density_curves(
    idata: arviz.InferenceData,
    vlines: typing.Optional[preprocessing.NamedDates] = None,
    actual_tests: typing.Optional[pandas.Series] = None,
    fig=None,
    axs: numpy.ndarray=None,
):
    """ Creates a figure that shows the most important results of the model for a particular region.

    Parameters
    ----------
    idata : arviz.InferenceData
        contains the MCMC trace and observed data
    vlines : preprocessing.NamedDates
        dictionary of { datetime.datetime : str } for drawing vertical lines
    fig : optional, Figure
        a figure to use (in combination with [axs] argument)
    axs : optional, array of axes
        three subplot axes to plot into

    Returns
    -------
    fig : matplotlib.Figure
        the figure
    (top, center, bottom) : tuple
        the subplots
    """
    # plot symptom onsets and R_t posteriors
    if not (fig != None and axs is not None):
        fig, (ax_curves, ax_testcounts, ax_probability, ax_rt) = pyplot.subplots(
            nrows=4,
            gridspec_kw={"height_ratios": [3, 1, 1, 2]},
            dpi=140,
            figsize=(10, 8),
            sharex="col",
        )
    else:
        ax_curves, ax_testcounts, ax_probability, ax_rt = axs
    handles = []

    scale_factor = model.get_scale_factor(idata)

    # top subplot: counts
    # "infections" and "test_adjusted_positive" are modeled relative.
    var_label_colors= [
        ('infections', 'infections', cm.Reds),
        ('test_adjusted_positive', 'testing delay adjusted', cm.Greens)
    ]

    for var, label, cmap in var_label_colors:
        pymc3.gp.util.plot_gp_dist(
            ax_curves,
            x=idata.posterior[var].date.values[3:],
            samples=((idata.posterior[var].stack(sample=('chain', 'draw')) * scale_factor).values.T)[:, 3:],
            samples_alpha=0,
            palette=cmap,
            fill_alpha=.15,
        )
        handles.append(ax_curves.fill_between([], [], color=cmap(100), label=label))
    label="positive tests"
    ax_curves.set_ylabel("per day", fontsize=15)

    handles.append(
        ax_curves.bar(
            idata.constant_data.observed_positive.date.values,
            idata.constant_data.observed_positive,
            label=label,
            alpha=0.5,
        )
    )
    if vlines:
        plot_vlines(ax_curves, vlines, alignment='bottom')
    ax_curves.legend(
        handles=[
            *handles,
        ],
        loc="upper left",
        frameon=False,
    )

    ax_testcounts.plot(
        idata.constant_data.tests.date.values,
        idata.constant_data.tests.values,
        color="orange",
        label="modeled",
    )
    if actual_tests is not None:
        ax_testcounts.bar(
            actual_tests.index,
            actual_tests.values,
            label="actual",
        )
    ax_testcounts.legend(frameon=False, loc="upper left")
    if vlines:
        plot_vlines(ax_testcounts, { k : "" for k, v in vlines.items() }, alignment="bottom")
    ax_testcounts.set_ylabel("daily tests")

    # center subplot: probabilities
    ax_probability.plot(
        idata.posterior.date, (idata.posterior.r_t > 1).mean(dim=("chain", "draw"))
    )
    ax_probability.set_ylim(0, 1)
    ax_probability.set_ylabel("$p(R_t > 1)$", fontsize=15)

    # bottom subplot: R_t
    pymc3.gp.util.plot_gp_dist(
        ax=ax_rt,
        x=idata.posterior.date.values,
        samples=idata.posterior.r_t.stack(sample=("chain", "draw")).T.values,
        samples_alpha=0,
    )
    ax_rt.axhline(1, linestyle=":")
    ax_rt.set_ylabel("$R_t$", fontsize=15)
    ax_rt.xaxis.set_major_locator(
        matplotlib.dates.WeekdayLocator(interval=1, byweekday=matplotlib.dates.MO)
    )
    ax_rt.xaxis.set_minor_locator(matplotlib.dates.DayLocator())
    ax_rt.xaxis.set_tick_params(rotation=90)
    ax_rt.set_ylim(0, 2.5)

    fig.tight_layout()
    return fig, (ax_curves, ax_testcounts, ax_probability, ax_rt)
