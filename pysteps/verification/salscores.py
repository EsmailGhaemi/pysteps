# -- coding: utf-8 --
"""
pysteps.verification.salscores
==============================

The Spatial-Amplitude-Location (SAL) score by :cite:`WPHF2008`.

.. autosummary::
    :toctree: ../generated/

    sal
    sal_structure
    sal_amplitude
    sal_location
"""
from math import sqrt, hypot

import numpy as np
from scipy.ndimage.measurements import center_of_mass

from pysteps.exceptions import MissingOptionalDependency
from pysteps.feature import tstorm as tstorm_detect

try:
    import pandas as pd

    pandas_imported = True
except ImportError:
    pandas_imported = False

try:
    from skimage.measure import regionprops_table

    skimage_imported = True
except ImportError:
    skimage_imported = False


# regionprops proerty names changed with scikit-image v0.19, buld old names
# will continue to work for backwards compatibility
# see https://github.com/scikit-image/scikit-image/releases/tag/v0.19.0
REGIONPROPS = [
    "label",
    "centroid_weighted",
    "max_intensity",
    "intensity_image",
]


def sal(
    prediction,
    observation,
    thr_factor=1 / 15,
    tstorm_kwargs=None,
):
    """
    Compute the Structure-Amplitude-Location (SAL) spatial verification metric.

    Parameters
    ----------
    prediction: array-like
        Array of shape (m,n) with prediction data.
    observation: array-like
        Array of shape (m,n)  with observation data.
    thr_factor: float, optional
        Factor used to compute the detection threshold as in eq. 1 of :cite:`WHZ2009`.
        If specified, this is used to identify coherent objects enclosed by the threshold
        contour thr_factor * quantile95(precip).
    tstorm_kwargs: dict, optional
        Optional dictionary containing keyword arguments for the tstorm feature
        detection algorithm. If None, default values are used.
        See the documentation of :py:func:`pysteps.feature.tstorm.detection`.

    Returns
    -------
    sal: tuple of floats
        A tuple of floats containing the structure, amplitude, location components of SAL.

    References
    ----------
    :cite:`WPHF2008`
    :cite:`WHZ2009`
    :cite:`Feldmann2021`

    Notes
    -----
    This implementation uses the thunderstorm detection algorithm by :cite:`Feldmann2021`
    for the identification of precipitation objects within the considered domain.

    See also
    --------
    :py:mod:`pysteps.feature.tstorm`.
    """
    if np.nanmax(observation >= 0.1) & np.nanmax(
        prediction >= 0.1
    ):  # to avoid errors of nan values or very low precipitation
        structure = sal_structure(prediction, observation, thr_factor, tstorm_kwargs)
        amplitude = sal_amplitude(prediction, observation)
        location = sal_location(prediction, observation, thr_factor, tstorm_kwargs)
    else:
        structure = np.nan
        amplitude = np.nan
        location = np.nan
    return structure, amplitude, location


def sal_structure(prediction, observation, thr_factor=None, tstorm_kwargs=None):
    """This function calculates the structure component for SAL based on
    :cite:`WPHF2008`.

    Parameters
    ----------
    prediction: array-like
        Array of shape (m,n) with prediction data.
    observation: array-like
        Array of shape (m,n)  with observation data.
    thr_factor: float, optional
        Factor used to compute the detection threshold as in eq. 1 of :cite:`WHZ2009`.
        If specified, this is used to identify coherent objects enclosed by the threshold
        contour thr_factor * quantile95(precip).
    tstorm_kwargs: dict, optional
        Optional dictionary containing keyword arguments for the tstorm feature
        detection algorithm. If None, default values are used.
        See the documentation of :py:func:`pysteps.feature.tstorm.detection`.

    Returns
    -------
    structure: float
        The structure component with value between -2 to 2.
    """
    prediction_objects = _sal_detect_objects(prediction, thr_factor, tstorm_kwargs)
    observation_objects = _sal_detect_objects(observation, thr_factor, tstorm_kwargs)
    prediction_volume = _sal_scaled_volume(prediction_objects).sum()
    observation_volume = _sal_scaled_volume(observation_objects).sum()
    nom = prediction_volume - observation_volume
    denom = prediction_volume + observation_volume
    return nom / (0.5 * denom)


def sal_amplitude(prediction, observation):
    """Calculate the amplitude component for SAL based on :cite:`WPHF2008`.

    This component is the normalized difference of the domain-averaged precipitation
    in observation and forecast.

    Parameters
    ----------
    prediction: array-like
        Array of shape (m,n) with prediction data.
    observation: array-like
        Array of shape (m,n)  with observation data.

    Returns
    -------
    amplitude: float
        Amplitude parameter with value between -2 to 2 and 0
        denotes perfect forecast in terms of amplitude.
    """
    mean_obs = np.nanmean(observation)
    mean_pred = np.nanmean(prediction)
    return (mean_pred - mean_obs) / (0.5 * (mean_pred + mean_obs))


def sal_location(prediction, observation, thr_factor=None, tstorm_kwargs=None):
    """Calculate the first parameter of location component for SAL based on
    :cite:`WPHF2008`.

    This parameter indicates the normalized distance between the center of mass in
    observation and forecast.

    Parameters
    ----------
    prediction: array-like
        Array of shape (m,n) with prediction data.
    observation: array-like
        Array of shape (m,n)  with observation data.
    thr_factor: float, optional
        Factor used to compute the detection threshold as in eq. 1 of :cite:`WHZ2009`.
        If specified, this is used to identify coherent objects enclosed by the threshold
        contour thr_factor * quantile95(precip).
    tstorm_kwargs: dict, optional
        Optional dictionary containing keyword arguments for the tstorm feature
        detection algorithm. If None, default values are used.
        See the documentation of :py:func:`pysteps.feature.tstorm.detection`.

    Returns
    -------
    location: float
        The location component with value between 0 to 2 and 0
        denotes perfect forecast in terms of location.
    """
    return _sal_l1_param(prediction, observation) + _sal_l2_param(
        prediction, observation, thr_factor, tstorm_kwargs
    )


def _sal_l1_param(prediction, observation):
    """Calculate the first parameter of location component for SAL based on
    :cite:`WPHF2008`.

    This parameter indicates the normalized distance between the center of mass in
    observation and forecast.

    Parameters
    ----------
    prediction: array-like
        Array of shape (m,n) with prediction data.
    observation: array-like
        Array of shape (m,n)  with observation data.

    Returns
    -------
    location_1: float
        The first parameter of location component which has a value between 0 to 1.
    """
    maximum_distance = sqrt(
        ((observation.shape[0]) ** 2) + ((observation.shape[1]) ** 2)
    )
    obi = center_of_mass(np.nan_to_num(observation))
    fori = center_of_mass(np.nan_to_num(prediction))
    dist = hypot(fori[1] - obi[1], fori[0] - obi[0])
    return dist / maximum_distance


def _sal_l2_param(prediction, observation, thr_factor, tstorm_kwargs):
    """Calculate the second parameter of location component for SAL based on :cite:`WPHF2008`.

    Parameters
    ----------
    prediction: array-like
        Array of shape (m,n) with prediction data.
    observation: array-like
        Array of shape (m,n)  with observation data.
    thr_factor: float
        Factor used to compute the detection threshold as in eq. 1 of :cite:`WHZ2009`.
        If specified, this is used to identify coherent objects enclosed by the threshold
        contour thr_factor * quantile95(precip).
    tstorm_kwargs: dict
        Optional dictionary containing keyword arguments for the tstorm feature
        detection algorithm. If None, default values are used.
        See the documentation of :py:func:`pysteps.feature.tstorm.detection`.

    Returns
    -------
    location_2: float
        The secibd parameter of location component with value between 0 to 1.
    """
    maximum_distance = sqrt(
        ((observation.shape[0]) ** 2) + ((observation.shape[1]) ** 2)
    )
    obs_r = (_sal_weighted_distance(observation, thr_factor, tstorm_kwargs)) * (
        observation.mean()
    )
    forc_r = (_sal_weighted_distance(prediction, thr_factor, tstorm_kwargs)) * (
        prediction.mean()
    )
    location_2 = 2 * ((abs(obs_r - forc_r)) / maximum_distance)
    return float(location_2)


def _sal_detect_objects(precip, thr_factor, tstorm_kwargs):
    """This function detects thunderstorms using a multi-threshold approach from :cite:`Feldmann2021`.

    Parameters
    ----------
    precip: array-like
        Array of shape (m,n) containing input data. Nan values are ignored.
    thr_factor: float
        Factor used to compute the detection threshold as in eq. 1 of :cite:`WHZ2009`.
        If specified, this is used to identify coherent objects enclosed by the threshold
        contour thr_factor * quantile95(precip).
    tstorm_kwargs: dict
        Optional dictionary containing keyword arguments for the tstorm feature
        detection algorithm. If None, default values are used.
        See the documentation of :py:func:`pysteps.feature.tstorm.detection`.

    Returns
    -------
    precip_objects: pd.DataFrame
        Dataframe containing all detected cells and their respective properties.
    """
    if not pandas_imported:
        raise MissingOptionalDependency(
            "The pandas package is required for the SAL "
            "verification method but it is not installed"
        )
    if not skimage_imported:
        raise MissingOptionalDependency(
            "The scikit-image package is required for the SAL "
            "verification method but it is not installed"
        )
    if tstorm_kwargs is None:
        tstorm_kwargs = dict()
    if thr_factor is not None:
        zero_value = np.nanmin(precip)
        tstorm_kwargs = {
            "minsize": tstorm_kwargs.get("minsize", 5),
            "minmax": tstorm_kwargs.get("minmax", 0),
            "mindis": tstorm_kwargs.get("mindis", 5),
            "maxref": tstorm_kwargs.get("maxref", np.Inf),
            "minref": thr_factor
            * np.nanquantile(np.array(precip[precip > zero_value]), 0.95),
            # np.array() converts masked arrays which do not play well with
            # np.nanquantile, see https://github.com/numpy/numpy/issues/11990
        }
    _, labels = tstorm_detect.detection(precip, **tstorm_kwargs)
    labels = labels.astype(int)
    precip_objects = regionprops_table(
        labels, intensity_image=precip, properties=REGIONPROPS
    )
    return pd.DataFrame(precip_objects)


def _sal_scaled_volume(precip_objects):
    """Calculate the scaled volume based on :cite:`WPHF2008`.

    Parameters
    ----------
    precip_objects: pd.DataFrame
        Dataframe containing all detected cells and their respective properties
        as returned by the :py:func:`pysteps.verification.salsscores._sal_detect_objects`
        function.

    Returns
    -------
    object_volume: pd.Series
        A pandas Series with the scaled volume of each precipitation object.
    """
    if not pandas_imported:
        raise MissingOptionalDependency(
            "The pandas package is required for the SAL "
            "verification method but it is not installed"
        )
    objects_volume_scaled = []
    for _, precip_object in precip_objects.iterrows():
        intensity_sum = precip_object.intensity_image.sum()
        max_intensity = precip_object.max_intensity
        volume_scaled = intensity_sum / max_intensity
        objects_volume_scaled.append(volume_scaled)
    return pd.Series(
        data=objects_volume_scaled, index=precip_objects.label, name="scaled_volume"
    )


def _sal_weighted_distance(precip, thr_factor, tstorm_kwargs):
    """Compute the weighted averaged distance between the centers of mass of the
    individual objects and the center of mass of the total precipitation field.

    Parameters
    ----------
    precip: array-like
        Array of shape (m,n).
    thr_factor: float
        Factor used to compute the detection threshold as in eq. 1 of :cite:`WHZ2009`.
        If specified, this is used to identify coherent objects enclosed by the threshold
        contour thr_factor * quantile95(precip).
    tstorm_kwargs: dict
        Optional dictionary containing keyword arguments for the tstorm feature
        detection algorithm. If None, default values are used.
        See the documentation of :py:func:`pysteps.feature.tstorm.detection`.

    Returns
    -------
    weighted_distance: float
        The weighted averaged distance between the centers of mass of the
        individual objects and the center of mass of the total precipitation field.
    """
    if not pandas_imported:
        raise MissingOptionalDependency(
            "The pandas package is required for the SAL "
            "verification method but it is not installed"
        )
    precip_objects = _sal_detect_objects(precip, thr_factor, tstorm_kwargs)
    centroid_total = center_of_mass(np.nan_to_num(precip))
    r = []
    for i in precip_objects.label - 1:
        xd = (precip_objects["centroid_weighted-1"][i] - centroid_total[1]) ** 2
        yd = (precip_objects["centroid_weighted-0"][i] - centroid_total[0]) ** 2

        dst = sqrt(xd + yd)
        sumr = (precip_objects.intensity_image[i].sum()) * dst

        sump = precip_objects.intensity_image[i].sum()

        r.append({"sum_dist": sumr, "sum_p": sump})
    rr = pd.DataFrame(r)
    return rr.sum_dist.sum() / (rr.sum_p.sum())