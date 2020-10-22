"""
Spectral manipulations.
"""
import numpy as np
import xarray as xr
from scipy.integrate import cumtrapz
from scipy.interpolate import InterpolatedUnivariateSpline


def smear_tuv_1(x, y, xgl, xgu):
    """Smear `y`(`x`) over the region defined by [`xgl`, `xgu`].

    Parameters
    ----------
    x : array_like
        the original grid
    y : array_like
        the values y(x) to be smeared
    xgl : float
        left side x bound
    xgu : float
        right side x bound

    Notes
    -----
    Implementation based on F0AM's implementation of TUV's un-named algorithm.
    It works by applying cumulative trapezoidal integration to the original data,
    but extrapolating so that xgl and xgu don't have to be on the original x grid.
    """
    area = 0
    for k in range(x.size - 1):  # TODO: could try subsetting first instead of over whole grid
        if x[k + 1] < xgl or x[k] > xgu:  # outside window
            continue

        a1 = max(x[k], xgl)
        a2 = min(x[k + 1], xgu)

        slope = (y[k + 1] - y[k]) / (x[k + 1] - x[k])
        b1 = y[k] + slope * (a1 - x[k])
        b2 = y[k] + slope * (a2 - x[k])
        area = area + (a2 - a1) * (b2 + b1) / 2

    yg = area / (xgu - xgl)

    return yg


def smear_tuv(x, y, bins):
    """Use :func:`smear_tuv_1` to bin `y` values at `x` positions into `bins` (new x-bin edges).
    Returns an array of in-bin y-values ynew, such that the sum of ynew*dwl
    is equal to the original integral of y(x).
    """
    ynew = np.zeros(bins.size - 1)
    for i, (xgl, xgu) in enumerate(zip(bins[:-1], bins[1:])):
        ynew[i] = smear_tuv_1(x, y, xgl, xgu)
    return ynew  # valid for band, not at left edge


def smear_trapz_interp(x, y, bins, *, k=3, interp="F"):
    """Interpolate y(x) to bin values, then apply trapezoidal integration.

    Parameters
    ----------
    k : int
        Degree of the spline used (1--5). The spline passes through all data points.
    interp : str
        'F' to interpolate the cumulative trapz integral, or 'f' to interpolate the `y` data.
    """
    if interp == "f":
        spl = InterpolatedUnivariateSpline(x, y, k=k)
        y_bins = spl(bins)
        Ynew = cumtrapz(y_bins, x=bins, initial=0)
        dYnew = np.diff(Ynew)

    elif interp == "F":
        Y0 = cumtrapz(y, x, initial=0)
        spl = InterpolatedUnivariateSpline(x, Y0, k=k)
        dYnew = spl(bins[1:]) - spl(bins[:-1])

    else:
        raise ValueError(f"invalid `interp` {interp!r}")

    dxnew = np.diff(bins)

    return dYnew / dxnew


def _smear_da(da, bins, *, xname, xname_out, method, **method_kwargs):
    """Returns an `xr.Dataset` ``data_vars`` tuple."""
    x = da[xname].values
    y = da.values

    if method == "tuv":
        ynew = smear_tuv(x, y, bins)

    elif method == "trapz_interp":
        ynew = smear_trapz_interp(x, y, bins, **method_kwargs)

    else:
        raise ValueError(f"invalid `method` {method!r}")

    return (xname_out, ynew, da.attrs)


def smear_ds(ds, bins, *, xname="wl", xname_out=None, method="tuv", **method_kwargs):
    """
    Smear spectra (with coordinate variable `xname`) to new `bins`.
    The returned `xr.Dataset` consists of the data variables who have the coordinate
    variable with name `xname`.
    """
    da_x = ds[xname]
    dx = np.diff(bins)
    xnewc = bins[:-1] + 0.5 * dx

    if xname_out is None:
        xname_out = xname

    new_data_vars = {
        vn: _smear_da(
            ds[vn], bins, xname=xname, xname_out=xname_out, method=method, **method_kwargs
        )
        for vn in ds.variables
        if xname in ds[vn].coords and vn not in ds.coords
    }

    da_xo = ds[xname_out]
    xe_name = f"{da_xo.name}e"
    xe_dims = [f"{d}e" for d in da_xo.dims]
    xe_attrs = {
        "long_name": f"{da_x.attrs['long_name']} band edges",
        "units": da_xo.attrs["units"],
    }
    return xr.Dataset(
        coords={
            da_xo.name: (da_xo.dims, xnewc, da_xo.attrs),
            xe_name: (xe_dims, bins, xe_attrs),
        },
        data_vars=new_data_vars,
    )


def smear_si(ds, bins, *, xname_out="wl", **kwargs):
    """Smear spectral irradiance, computing in-bin irradiance in the new bins.
    `**kwargs` are passed to :func:`smear_ds`.
    `ds` must have 'SI_dr', 'SI_df'
    """
    # coordinate variable for the spectral irradiances
    xname = list(ds["SI_dr"].coords)[0]

    # smear the spectral irradiances
    ds_new = smear_ds(
        ds[["SI_dr", "SI_df", xname_out]], bins=bins, xname=xname, xname_out=xname_out, **kwargs
    )

    # compute irradiances
    dwl = np.diff(ds_new.wle)
    units = "W m-2"
    ds_new["I_dr"] = (
        xname_out,
        ds_new.SI_dr * dwl,
        {"units": units, "long_name": "Direct irradiance"},
    )
    ds_new["I_df"] = (
        xname_out,
        ds_new.SI_df * dwl,
        {"units": units, "long_name": "Diffuse irradiance"},
    )
    ds_new["dwl"] = (xname_out, dwl, {"units": "μm", "long_name": "Wavelength band width"})
    # TODO: ensure attrs consistency somehow

    return ds_new


def edges_from_centers(x):
    """Estimate locations of the bin edges by extrapolating the grid spacing on the edges.
    Note that the true bin edges could be different--this is just a guess!

    From specutils:
    https://github.com/astropy/specutils/blob/9ce88d6be700a06e888d9d0cdd04c0afc2ae85f8/specutils/spectra/spectral_axis.py#L46-L55
    """
    extend_left = np.r_[2 * x[0] - x[1], x]
    extend_right = np.r_[x, 2 * x[-1] - x[-2]]
    edges = (extend_left + extend_right) / 2

    return edges


def plot_binned(x, y, xc, yc, dx):
    """Compare an original spectrum to binned one.

    If `x` and `y` are `xr.DataArray` s, their attrs will be used to label the plot.

    Parameters
    ----------
    x, y :
        original/actual values at wavelengths (original spectra)
    xc, yc :
        values at wave band centers
    dx :
        wave band widths
    """
    import matplotlib.pyplot as plt
    from .utils import cf_units_to_tex

    spectrum_ls = "r-" if x.size > 150 else "r.-"
    xbounds = (x[0], x[-1])

    fig, ax = plt.subplots(figsize=(9, 5))

    ax.bar(xc, yc, width=dx, label="binned", align="center", alpha=0.7, edgecolor="blue")

    ax.plot(x, y, spectrum_ls, lw=1.5, label="spectrum")

    if isinstance(x, xr.DataArray) and isinstance(y, xr.DataArray):
        unx = cf_units_to_tex(x.attrs["units"])
        lnx = x.attrs["long_name"]
        xlabel = f"{lnx} ({unx})"
        uny = cf_units_to_tex(y.attrs["units"])
        lny = y.attrs["long_name"]
        ylabel = f"{lny} ({uny})"
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

    ax.set_xlim(xbounds)

    ax.legend()

    fig.tight_layout()


def plot_binned_ds(ds0, ds, *, yname=None):
    """Compare an original spectrum in `ds0` to binned one in `ds`.
    Uses :func:`plot_binned` with auto-detection of ``x``, ``dx``, and ``xc``.
    """
    y = ds0[yname]
    xname = list(y.coords)[0]
    x = ds0[xname]

    yc = ds[yname]
    xcname = list(yc.coords)[0]
    xc = ds[xcname]

    # get dx, either from stored variable or by comnputing from edges
    try:
        dx = ds[f"d{xcname}"]
    except KeyError:
        xe = ds[f"{xcname}e"]
        dx = np.diff(xe)

    plot_binned(x, y, xc, yc, dx)


if __name__ == "__main__":
    pass
