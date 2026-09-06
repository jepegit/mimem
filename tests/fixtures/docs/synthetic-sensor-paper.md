# Thermal drift compensation in resonant strain sensors using a paired reference resonator

Ada Fenwick, Bo Lindqvist, Chidi Okonkwo

Institute for Synthetic Measurement, Northgate, and Department of Applied Physics, Westmere University

**Keywords:** thermal drift, resonant strain sensor, compensation network, reference resonator, drift coefficient

## Abstract

Resonant strain sensors lose accuracy as they warm, and the loss is not noise: it is a
systematic thermal drift that tracks the temperature of the substrate rather than the strain the
sensor was built to measure. We show that a paired reference resonator, held mechanically free
on the same die, reproduces the thermal drift of the measurement resonator closely enough that
subtracting the two removes most of it. Across forty devices the residual drift coefficient fell
from 0.0142 %/K to 0.0031 %/K, a reduction of 78 %, without any change to the measurement
resonator itself. The compensation network needed to do this is passive, occupies 0.42 mm2, and
costs one additional wire bond. We argue that the residual drift is dominated by the difference
in clamping stress between the two resonators, and that this difference, not the temperature
coefficient of the material, sets the floor on what paired compensation can achieve.

## 1 Introduction

A resonant strain sensor measures strain by tracking the frequency of a mechanical resonator
whose stiffness the strain modifies. The technique is old, well understood, and unusually
sensitive: a device with a nominal resonance of 12.7 kHz shifts by roughly 40 Hz per microstrain,
which a modest counter can resolve. The difficulty is that stiffness depends on temperature as
well as on strain, and the resonator has no way to tell the two apart.

The resulting thermal drift is large. In an uncompensated resonant strain sensor built on a
silicon substrate, the drift coefficient is typically between 0.010 and 0.020 %/K. A device
operating over a 40 K ambient range therefore reports an apparent strain that varies by more
than the strain most structures ever experience. Every practical deployment of a resonant strain
sensor is, in effect, a scheme for removing thermal drift.

Three families of scheme exist. The first measures temperature separately and corrects in
software, which works but requires a calibration per device and degrades as the calibration
ages. The second builds the resonator from a material whose temperature coefficient is small,
which is expensive and constrains every other property of the device. The third, which this
paper takes up, places a second resonator on the same die and uses it as a reference.

The reference resonator is mechanically decoupled from the structure under test. It therefore
sees the same temperature as the measurement resonator and almost none of the strain. Its
frequency shift is thermal drift and nothing else, and subtracting it should leave strain alone.
This is an old idea and it is not new here. What is new is a quantitative account of why the
subtraction is imperfect, and a demonstration that the imperfection is dominated by a mechanism
nobody has been correcting for.

The remainder of this paper is organised as follows. Section 2 describes the devices and the
measurement. Section 3 reports the residual drift coefficient across forty devices and its
dependence on clamping geometry. Section 4 argues that clamping stress, not material, sets the
floor. Section 5 concludes.

## 2 Methods

Forty resonant strain sensors were fabricated on 150 mm silicon-on-insulator wafers with a
device layer thickness of 20 µm. Each die carries a measurement resonator, clamped at both ends
to the die frame, and a reference resonator of identical nominal geometry clamped at one end
only. Both are driven electrostatically and sensed capacitively at a bias of 1.85 V.

The resonant frequency of a clamped-clamped beam under axial stress is

$$
f(T) = f_0 \sqrt{1 + \gamma \frac{\sigma(T)}{E}}
$$

where $f_0$ is the unstressed resonance, $\sigma(T)$ the axial stress, $E$ the Young's modulus of
the device layer, and $\gamma$ a geometric factor near 0.24 for the beams used here. Both the
stress and the modulus depend on temperature, and it is their combination that produces the
thermal drift the compensation network is meant to remove.

The compensation network forms the difference of the two resonator frequencies. Writing the
drift coefficient as the fractional frequency change per kelvin,

$$
\alpha = \frac{1}{f} \frac{df}{dT}
$$

the residual after compensation is the difference of the two coefficients, and the quality of
the compensation is set by how nearly equal they are rather than by how small either one is.

Devices were cycled between 253 K and 333 K in a thermal chamber, twenty-five times, with
frequency recorded every 2 s. The first three cycles of every device were discarded: the drift
coefficient measured during them differs systematically from later cycles, which we attribute to
stress relaxation in the die attach and do not analyse further here.

Strain was applied with a four-point bending rig calibrated against a foil gauge. Reported
strain values are the rig's, not the sensor's.

## 3 Results

Thermal drift in the uncompensated measurement resonator was consistent across the batch. The
mean drift coefficient was 0.0142 %/K with a standard deviation of 0.0009 %/K, in line with
published values for this material system. The reference resonator drifted at 0.0138 %/K, close
but not equal.

| Configuration | Drift coefficient (%/K) | Standard deviation (%/K) | Devices |
|---|---|---|---|
| Measurement resonator, uncompensated | 0.0142 | 0.0009 | 40 |
| Reference resonator, uncompensated | 0.0138 | 0.0011 | 40 |
| Paired, single-end clamp | 0.0031 | 0.0006 | 40 |
| Paired, matched double clamp | 0.0009 | 0.0004 | 12 |

Table 1. Drift coefficient before and after compensation, by clamping configuration.

![A plot of residual drift coefficient against clamping stress difference, showing a rising trend with two outliers below the line](fig1.png)

Figure 1. Residual drift coefficient against the difference in clamping stress between the two
resonators, for all forty devices. The relationship is close to linear over the measured range,
with two devices falling well below the trend; both had visible die-attach voids.

Compensation reduced the residual drift coefficient to 0.0031 %/K, a reduction of 78 %. The
residual is far larger than the measurement noise floor of 0.0002 %/K, so it is a real effect
and not a limit of the instrument.

The residual drift did not scale with the absolute drift of either resonator. Devices whose
measurement resonator drifted most were not the devices with the worst residual. It did scale
with the difference in clamping stress, estimated from the release-etch undercut measured
optically on each die. Over the range sampled, a 1 MPa difference in clamping stress produced
about 0.0008 %/K of residual drift.

A subset of twelve devices was fabricated with the reference resonator clamped at both ends and
mechanically isolated by a compliant serpentine rather than by a free end. In these the residual
drift coefficient fell to 0.0009 %/K, and the dependence on undercut disappeared within the
measurement uncertainty.

## 4 Discussion

The result that matters is the negative one. The residual drift after compensation is not
predicted by the drift of either resonator alone, which rules out the explanation everybody
reaches for first: that the two resonators are made of slightly different material, or sit at
slightly different temperatures. Either of those would produce a residual proportional to the
absolute drift, and it is not.

Clamping stress explains it. A clamped-clamped beam and a beam clamped at one end respond
differently to the same substrate expansion, because only the first has its length constrained.
The measurement resonator is therefore loaded by thermal expansion of the die frame in a way the
reference resonator is not, and that loading appears in the difference as residual thermal
drift. The twelve matched-clamp devices are the test of this account, and they pass it: making
the clamping conditions the same removed the effect.

This has a practical consequence that the paired-resonator literature has mostly missed.
Matching the two resonators as *resonators* — same material, same geometry, same nominal
frequency — is not sufficient and not the hard part. Matching their *boundary conditions* is
what sets the floor, and a reference resonator that is mechanically free, which is the obvious
way to keep strain out of it, is for that exact reason badly matched to a clamped measurement
resonator.

The compensation network itself is not the limiting element. It is passive, contributes 0.0002
%/K of its own drift, and occupies 0.42 mm2.

We did not test above 333 K, and the clamping-stress account predicts a departure from linearity
once the die attach begins to yield. That is the obvious next measurement and we have not made
it.

## 5 Conclusion

A paired reference resonator reduces the thermal drift of a resonant strain sensor by 78 %, from
0.0142 %/K to 0.0031 %/K, at the cost of one wire bond and 0.42 mm2. The residual is set by the
difference in clamping stress between the two resonators rather than by any property of the
material, and matching the clamping conditions reduces it by a further factor of three, to 0.0009
%/K. Designers of compensation networks should treat boundary-condition matching as the primary
design variable.

## Funding

This work was supported by the Northgate Institute under grant number SM-2019-4471.

## Conflicts of Interest

The authors declare no conflicts of interest.

## Acknowledgements

We thank the Westmere cleanroom staff for the release etch, and two anonymous reviewers whose
objection to our first explanation of the residual led to the matched-clamp experiment.

## References

1. Fenwick, A. and Okonkwo, C. Resonant strain sensing at low bias. Journal of Synthetic
   Measurement, 12, 44 (2018).
2. Lindqvist, B. Thermal drift in silicon resonators. Proceedings of the Northgate Workshop, 91
   (2020).
