# Vision-Based Dimensional Inspection Cell

An offline Python foundation for measuring a single bright planar rectangle in a
calibrated grayscale image. It estimates a **minimum-area enclosing rectangle**
in millimeters. It has no ROS2 integration, cell control, conformity decision,
nominal-size input or learned size correction.

Execution and independent geometric controls have been verified. The unavailable
historical prototype's measurement correction remains unverified; this candidate
is not qualified as a completed correction of that baseline.

## Install and run

Use Python 3.11 or newer and an isolated environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[test]'
python examples/offline_rectangle.py
python -m pytest -q -s
```

Both the script and the Python snippet below printed `Length: 40.042 mm` and
`Width:  20.042 mm` in the recorded validation environment. These are synthetic
observations, not an accuracy guarantee.

Runtime dependencies are NumPy and headless OpenCV; pytest is a test extra.
The dependency list is in `pyproject.toml`. No GUI or camera is required.

The example synthesizes an image separately from the measurement code. Its
known dimensions are supplied only to the renderer, never to the estimator:

```python
import numpy as np
from vision_inspection import PlanarCalibration, measure_rectangle
from vision_inspection.synthetic import render_rectangle

calibration = PlanarCalibration.from_correspondences(
    [[40, 40], [280, 40], [280, 220], [40, 220]],
    [[-30, -20], [30, -20], [30, 20], [-30, 20]],
)
image = render_rectangle(
    image_shape=(240, 320),
    plane_to_pixel=np.array([[4, 0, 160], [0, 4.5, 130], [0, 0, 1.0]]),
    center_mm=(0, 0), size_mm=(40, 20), angle_deg=23, samples_per_axis=8,
)
result = measure_rectangle(image, calibration)
print(f"Length: {result.length_mm:.3f} mm")
print(f"Width:  {result.width_mm:.3f} mm")
```

For a real image, replace the fixture with a 2D `np.uint8` grayscale array
(for example `cv2.imread(path, cv2.IMREAD_GRAYSCALE)`, checking for `None`). Supply
independently measured calibration correspondences from the same imaging setup.

## Coordinates, calibration and measurement plane

- An array has shape `(height, width)` and indexing `image[y, x]`.
- Pixel points are `(x, y)`, with integer coordinates at sample centers;
  x increases rightward and y downward. A pixel footprint spans +/-0.5.
- Plane points are `(X, Y)` in **millimeters**, with axes and origin chosen by
  the calibration target. The example uses X rightward and Y downward.
- `pixel_to_plane` is a 3x3 homography: `[X, Y, 1] ~ H @ [x, y, 1]`.
  Homogeneous division is mandatory. Matrix scale has no physical meaning.
- At least four distinct paired points in projectively general position are
  needed. More points fit all correspondences using OpenCV `findHomography`
  with `method=0`; there is no RANSAC or automatic outlier rejection. Degenerate
  configurations are rejected. Matrix conditioning checks are numerical guards,
  not a certificate of calibration quality.
- `calibration.residuals_mm(pixels, plane_mm)` returns pointwise Euclidean
  residuals. Check both fitting points and **independent** points distributed
  over the measurement region. Four fitting points alone cannot validate scale.
- All measured edges must lie in the calibrated plane (conventionally Z=0).
  This is a planar metric calibration, not a camera-intrinsic calibration.
  Correct lens distortion upstream and calibrate in that corrected coordinate
  system. Keep crop, resolution, focus and camera/plane pose unchanged.

## Algorithm and geometric controls

1. Segment `image > threshold`, default intensity 127.5 in the 0..255 range.
   Require exactly one contour, no holes, no foreground at the frame border and
   contour area at least 4 square pixels. There is no morphology or smoothing.
2. Find threshold crossings along horizontal and vertical grid edges. Linearly
   interpolate intensities between adjacent sample centers. For a binary
   0/255 step at threshold 127.5 this places the crossing at the midpoint.
3. Transform these boundary points into the measurement plane. Reject a boundary
   at, near or straddling the projective horizon.
4. Fit OpenCV `minAreaRect` **in millimeters**, centering and scaling coordinates
   before its float32 computation. Return the longer side as `length_mm`, the
   shorter as `width_mm`, and four cyclic, otherwise unlabeled `corners_mm`.

An axis-aligned run of N foreground pixels has N pixel footprints but its first
and last centers are only N-1 apart. The step-edge control tests this distinction
at three metric scales. Midpoint interpolation is a geometric image convention,
not an empirical millimeter offset. It does not make arbitrary rasterized edges
exact: center sampling still leaves phase-dependent dimensional uncertainty.

A projective map preserves straight lines but generally not right angles or
minimum-area enclosing rectangles. The vector-only test maps exact rectangle
vertices through a known projective transform. Mapping the boundary back before
fitting recovers the dimensions; deliberately fitting a pixel rectangle first
does not. That deliberately wrong control is newly constructed, not recovered
prototype code. These controls establish independent geometric mechanisms;
they do not establish the cause of an unavailable earlier implementation's bias.

The synthetic fixture inverse-maps regular subpixel samples and averages binary
coverage. It avoids rounded polygon vertices and uses no estimator calls. An
independent axis-aligned mask tests the renderer, and separate center-sampled
masks expose rasterization error. No dimension or reference qualification is
accepted by `measure_rectangle(image, calibration, *, threshold=127.5)`.

## Validation and provenance

See [validation.md](validation.md) for the fresh test environment, observed
results and the historical baseline's status. Synthetic tests are numerical
regressions, not a real-camera accuracy or tolerance claim. Raw campaign outputs,
virtual environments, caches and build artifacts are excluded from the candidate.

This repository was initially empty. The requested
`inspection-prototype-20261019.zip` was not found in the readable portion of
`~/Downloads`; an unrelated project's `scripts/__pycache__` was inaccessible.
No prototype code, prior report or assets were imported. No authorship or
license-ownership metadata is asserted; a repository license still needs an
owner's decision before redistribution under a chosen license.

### Dependency licenses

No third-party source, binary, image or dataset is bundled in this candidate's
sdist or wheel. Dependencies are installed separately by pip. Their licenses
do not select a license for this project's original code.

The recorded environment's distribution metadata and installed notices were
reviewed, alongside these upstream sources:

| Dependency | Verified license information |
| --- | --- |
| NumPy 2.5.4 | [Upstream license](https://numpy.org/doc/stable/license.html): BSD-3-Clause. Installed distribution metadata: `BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0`. Its binary wheel also contains bundled-library notices. |
| opencv-python-headless 4.14.0.94 | [Python packaging license](https://github.com/opencv/opencv-python/blob/master/LICENSE.txt): MIT; [OpenCV library license](https://opencv.org/license/): Apache-2.0 for this version. The wheel includes `LICENSE.txt` and `LICENSE-3RD-PARTY.txt`; its metadata's `Apache 2.0` label alone does not describe every bundled component. |

The tested pytest, setuptools and build distributions declare MIT in their
installed metadata. Complete dependency notices remain in the installed
distributions; the table is an inventory, not a replacement for those texts.
No project `LICENSE` or license expression has been fabricated.

## Assumptions and limitations

- A single bright, filled, sufficiently resolved rectangle on a dark background
  is assumed. Multiple objects, holes and clipping raise `ValueError`; a concave
  or nonrectangular solid object can still produce an enclosing rectangle.
  Rectangularity and product acceptance are not certified.
- The fitted box encloses threshold crossings. It is sensitive to threshold,
  noise, blur, shadows, outliers and corner sampling. Subpixel interpolation is
  not equivalent to subpixel metrological accuracy. A threshold change may
  change the measured dimensions.
- Lens distortion, object height above the plane, perspective calibration error,
  target uncertainty and optical effects are not estimated or compensated.
  The image does not carry geometry metadata: a wrong calibration, crop or
  resize may produce plausible but wrong dimensions.
- A homography is extrapolated outside its controls without a validity-region
  check. Near-degenerate configurations and extreme coordinate scales may be
  unreliable even when they pass numerical checks. Inputs near a horizon are
  rejected, but there is no application-specific conditioning threshold.
- There is no uncertainty budget, traceable calibration, real-image validation,
  automatic polarity/threshold selection, or classification strategy.
- Only the recorded Python/dependency combination was executed. Minimum supported
  versions are declared compatibility bounds, not a tested version matrix.

## Method references

The implementation is written for this candidate; no third-party source snippets
were copied. It calls these libraries and follows their documented methods:

- [OpenCV homography tutorial](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html):
  planar projective geometry and homogeneous division.
- [OpenCV calibration API](https://docs.opencv.org/4.x/d9/d0c/group__calib3d.html):
  `findHomography` and camera/lens-model context. The normalized DLT design matrix
  is used only as a degeneracy check; the actual fit is OpenCV's.
- [OpenCV shape API](https://docs.opencv.org/4.x/d3/dc0/group__imgproc__shape.html):
  `findContours`, `contourArea`, `minAreaRect` and `boxPoints`.
- [NumPy numerical rank](https://numpy.org/doc/stable/reference/generated/numpy.linalg.matrix_rank.html):
  the default SVD-based rank threshold used for numerical degeneracy guards.

Grid-edge intensity interpolation is the elementary linear equation
`fraction = (threshold - I0) / (I1 - I0)` on a straddling sample pair. There is no
ordered marching-squares contour or external subpixel-contour implementation.
