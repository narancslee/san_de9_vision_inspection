# Candidate validation

## Scope and historical evidence

Date: 2026-10-20. This is an independently implemented offline foundation.
The requested prototype archive was not located in the readable portion of
Downloads. One unrelated `scripts/__pycache__` directory could not be searched.
There was therefore no archive to extract or inspect in an isolated directory.

The task supplied the historical 99-image width bias **+0.848288 mm** and
RMSE **0.856206 mm**. Those values are unverified historical context, not results
of this candidate. Neither the old image set nor its generator, calibration,
measurement code or detailed results was available. No improvement over that
historical baseline is claimed, and no constant was fitted to those values.

## Reproduction

Run the install, example and tests from README.md. The sweep is deterministic and
prints aggregate errors with `python -m pytest -q -s`. It covers 120 images:
3 nominal pixel scales (3, 4, 5 px/mm), 2 projective settings, 4 angles
(0, 17, 43, 78 degrees), and 5 subpixel translations. Rectangles are 32 x 16 mm,
images 240 x 320 pixels, with 4 x 4 coverage samples per pixel. These are designed
controls, not the old 99-image campaign and not a statistically representative
validation set. Both measurement sides are sorted by size.

After the README installation, run only this sweep from the repository root:

```sh
python -m pytest -q -s tests/test_geometry.py::test_rotated_perspective_raster_sweep
```

To reproduce the recorded numerical environment, use CPython 3.14.6 on Linux
x86_64 and install the measured versions in a fresh virtual environment:

```sh
python -m pip install 'numpy==2.5.4' 'opencv-python-headless==4.14.0.94' 'pytest==9.1.1' '.[test]'
```

The runtime dependency ranges in `pyproject.toml` intentionally remain broader;
the command above records this measurement's versions rather than certifying
other combinations. Bitwise equality across platforms is not promised.

The sweep supplies the inverse of its exact synthetic projection, rather than
fitting a calibration from noisy observations. Calibration fitting is tested
separately. For nominal scale `s` and projective setting `p` the plane-to-pixel
matrix has rows `[s, 0.3, 160]`, `[0.1, s, 120]`, `[p, -p/2, 1]`. The center is
`(phase/s, -phase/s)` mm for phases 0, 0.2, 0.4, 0.6, 0.8.

The source of the reproduction is `tests/test_geometry.py` together with the
separate `synthetic.py` fixture and the installed estimator. The test computes
each signed error as measured side minus nominal side, then reports `mean(e)`,
`sqrt(mean(e**2))` and `max(abs(e))` independently for length and width. Its
assertion is a conservative maximum absolute error below 2/3 mm, not equality
with the printed table or a physical accuracy specification. No external image
set, network service, random seed or raw campaign file is required to run it.

The test layers distinguish:

| Layer | Control | What it can establish |
| --- | --- | --- |
| Calibration | Known affine/projective maps, separate check points | Numerical point-transform accuracy without rasterization |
| Boundary geometry | Exact projected vector vertices | Fit after transforming, rather than transform a pixel box |
| Contour convention | Binary blocks at 3 scales | Center span N-1 versus step-boundary span N |
| Rasterization | Independent center-sampled masks at 5 phases | Remaining sampling error bounded by 1 pixel per side in this axis-aligned control |
| Renderer | Independent exact axis-aligned mask | Fixture coordinate convention |
| Full pipeline | Rotated/projective 120-image sweep | Current synthetic residuals, including sampling and enclosing-box effects |
| Invalid inputs | Degenerate maps, horizons, images, segmentation | Explicit rejection of specified unsupported cases |

The step-boundary controls and vector-only control establish geometric
improvements relative to deliberately constructed incorrect controls. They
cannot attribute or resolve the unavailable prototype's historical bias.

## Executed results

Results are recorded here only after running the installed distribution and
executing both the README snippet and the example script.

Environment: Linux x86_64, CPython 3.14.6, NumPy 2.5.4,
opencv-python-headless 4.14.0.94 (OpenCV 4.14.0), pytest 9.1.1,
setuptools 84.2.0, build 1.6.1. All installation and test environments are in
`/tmp`, outside the candidate. Dependency lower bounds were not separately tested.

- Final test run: **60 passed**; no failures, skips or expected failures.
- README Python snippet and `examples/offline_rectangle.py`: both produced
  `Length: 40.042 mm` and `Width:  20.042 mm` for the 40 x 20 mm fixture.
- Affine held-out point maximum error: approximately 1.08e-14 mm.
  Projective held-out point maximum error: approximately 1.36e-6 mm.
  These are solver controls with exact synthetic correspondences.
- Exact vector control, transform boundary then fit: 40.000000 x 20.000000 mm.
  Deliberately wrong fit-first control: 43.570691 x 28.492299 mm.
- Binary block controls: 40 x 20 pixel footprints recovered at scales 0.1, 0.25,
  0.7 mm/px. A box around foreground pixel centers instead spans 39 x 19 pixels.

| Fresh 120-image sweep | Length error (mm) | Width error (mm) |
| --- | ---: | ---: |
| Mean signed error | +0.063926 | +0.068219 |
| RMSE | 0.066684 | 0.071456 |
| Maximum absolute error | 0.115336 | 0.119818 |

Positive residuals remain. The enclosing-box estimator and finite image sampling
do not yield an unbiased physical-edge estimator. No constant offset is applied.
Comparing these numbers directly with the historical campaign would be invalid
because the images, sampling and calibration conditions differ.

The initial run had 54 passes and one failure: the large-offset precision test
used a matrix beyond the calibration's numerical-rank guard. The final tests
separate accepted 1e6 mm coordinate offsets (dimensions remain accurate) from
the rejected extreme 1e7 mm configuration. The guard was not weakened. Additional
malformed-threshold tests were added and the installed package rerun.

Distribution validation builds an sdist and a wheel from that sdist with
`python -m build --no-isolation --outdir /tmp/vision-inspection-candidate-dist`.
The sdist includes the example, tests and both documentation files. The wheel is
installed normally (not editable), imports are checked under `site-packages`,
and tests and both examples run outside the source checkout. `pip check` finds
no broken requirements.

New candidate files are reviewed explicitly because ordinary `git diff --check`
does not examine untracked files. A no-index whitespace check against an empty
directory and an independent text scan cover every candidate file. The Git
index was absent initially and is required to remain absent; there are no
staged paths, commits or pushes in this work.

Status: a runnable, reviewable offline candidate with independent geometric
evidence. The historical bias correction remains unverified; this is not marked
as a completed correction of the unavailable prototype.

## Final review

The source and test files were compared byte-for-byte with the earlier reviewed
snapshot and built distributions before editing documentation. They were
unchanged, so the complete 60-test suite was not repeated for this review.
Documentation was expanded with the isolated sweep command, recorded-version
installation command, exact projection and metric definitions, and dependency
license inventory. The isolated sweep is checked using the updated sdist; the
previous full-suite and example results above remain the recorded evidence for
the unchanged executable code. The updated distributions are inspected for
source/document inclusion and exclusion of caches, environments and raw results.

The original project's license remains unspecified. No copied code or assets
requiring additional notices were found in the candidate. Dependency licensing
is documented without assigning project ownership. Historical-baseline recovery,
real-camera validation and a project-license choice remain open items, rather
than claims of completed measurement correction or a licensed release.
