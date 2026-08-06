<div align="center">

# CapiCam

### Portable Infrared Eccentric Photorefraction System for Pediatric Amblyopia Risk Screening

<!-- BANNER PLACEHOLDER: replace with a project banner (e.g. device photo + logo). Recommended size ~1280x400px -->
<p align="center">

</p>

*A low-cost, child-friendly screening device that estimates refractive error to support early detection of refractive amblyopia in children aged 4–6.*

[![Status](https://img.shields.io/badge/status-research%20prototype-orange)](#limitaciones-actuales)
[![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi-c51a4a?logo=raspberrypi&logoColor=white)](#hardware-used)
[![Language](https://img.shields.io/badge/language-TBD-lightgrey)](#-confirm-with-andre-before-publishing)
[![License](https://img.shields.io/badge/license-TBD-lightgrey)](#license)
[![Ethics Approval](https://img.shields.io/badge/pediatric%20trial-pending%20IRB%20approval-yellow)](#limitations)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#contributing)

</div>

---

> **Note on project scope.** CapiCam is currently a validated engineering **proof of concept**, tested on adult volunteers. Testing on the target pediatric population (children aged 4–6) is pending approval from the PUCP and Instituto Nacional de Oftalmología ethics committees. No result in this repository should be interpreted as evidence of clinical performance in the target population.

## Table of Contents

- [Overview](#overview)
- [Motivation](#motivation)
- [Problem Statement](#problem-statement)
- [Objectives](#objectives)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Hardware Used](#hardware-used)
- [Software & Technologies](#software--technologies)
- [Development Methodology](#development-methodology)
- [Operating Workflow](#operating-workflow)
- [Results](#results)
- [Limitations](#limitations)
- [Future Work](#future-work)
- [Repository Structure](#repository-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Related Publications](#related-publications)
- [Authors](#authors)
- [License](#license)

---

## Overview

**CapiCam** is a portable screening system based on **eccentric infrared photorefraction**, designed to estimate refractive errors (sphere, cylinder, axis) and support the early detection of **refractive amblyopia risk factors** in preschool-aged children (4–6 years). <cite index="4-1">The system integrates an ocular image acquisition module using a NoIR camera and infrared illumination, processing algorithms to estimate sphere, cylinder, and axis, a database for secure storage and encoding of sensitive information, and an automated report-generation system for parents or guardians.</cite>

The device is built around a Raspberry Pi single-board computer, an infrared camera without an IR-cut filter, and an array of 850 nm infrared LEDs arranged along three angular meridians (0°, 60°, 120°), housed in a **capybara-shaped 3D-printed enclosure** designed to improve cooperation from young children during the exam.

<cite index="4-2">The prototype was built and preliminarily evaluated on five adult volunteers to verify its functioning prior to its application in the pediatric population.</cite> <cite index="4-3">Photobiological characterization confirmed adequate safety factors according to the IEC 62471 standard for retinal risk and corneal irradiance, and image processing successfully segmented the pupil and estimated refractive parameters comparable to the participants' known optical prescription.</cite> <cite index="4-4">These results demonstrate the technical feasibility of CapiCam as a portable and accessible alternative for vision screening campaigns, although clinical validation in the target pediatric population is still required to confirm its performance as a detection tool.</cite>

**Keywords:** Amblyopia · Refractive Errors · Eccentric Photorefraction · Vision Screening · Pediatric Screening

## Motivation

<cite index="4-5">According to the American Academy of Ophthalmology, amblyopia is a visual development disorder characterized by decreased visual acuity in one or both eyes caused by an abnormal binocular interaction; when the visual stimulus disorder is not corrected during the early years of life, the neural visual circuit undergoes structural changes that can lead to alterations in visual function.</cite> <cite index="4-6">Globally, the prevalence of amblyopia is around 1.36%, while in Latin America prevalence varies by region between 2% and 7%.</cite>

Beyond reduced visual acuity, amblyopia can also affect stereopsis, binocular fusion, oculomotor function, and contrast sensitivity — and in children specifically, it is associated with reading difficulties and lower self-perception linked to reduced motor skills and reading speed. <cite index="4-7">Visual acuity improves during the first months of life and visual development continues until around 7 years of age, a period of greater neural plasticity for visual connections, which makes early detection and treatment critical.</cite>

Refractive amblyopia — caused by uncorrected refractive errors, most commonly anisometropia (a difference in refractive error between the two eyes) — is a major contributor to preventable vision loss. In the Peruvian context specifically:

- A study in Cercado de Lima (children aged 6–14) identified **strabismus** as the leading risk factor, followed by **hyperopia with astigmatism**.
- A study in Los Olivos found **refractive amblyopia** predominance (90% of cases), with 67.7% of diagnosed patients being children aged 5–8.
- <cite index="4-8">Only 7.5% of children aged 3 to 5 in Peru had a visual acuity exam in 2024, reflecting low parental awareness of visual risks.</cite>

This gap motivates the need for an accessible, easy-to-deploy screening tool that can be used **directly in schools**, reducing dependence on parents attending health campaigns or clinical facilities, while clearly communicating results to parents/guardians to enable timely care.

## Problem Statement

Refractive-error measurement in clinical settings typically relies on autorefractometers and retinoscopes operated by specialists. Portable alternatives exist commercially (Retinomax, GoCheck Kids, PlusOptiX, SureSight), and are effective at detecting refractive amblyopia risk factors, but in the Peruvian context they present:

- High cost and low accessibility/availability for mass screening campaigns.
- No pediatric-user-centered design.
- Dependence on specialized personnel to operate.

School screening campaigns need to evaluate large numbers of children in short timeframes, often **without visual health specialists on site**. This requires a portable tool that is easy to operate by trained (but non-specialist) technical staff, with a design friendly enough to secure children's cooperation and minimize exam time.

## Objectives

Develop **CapiCam**, an eccentric photorefraction system to:

1. Estimate refractive errors (sphere, cylinder, axis) in a pediatric population.
2. Identify refractive amblyopia risk factors to support school-based screening campaigns.
3. Enable early detection and timely communication of results to parents/guardians.
4. Evaluate the technical feasibility and usability of the system as a screening tool.

## Key Features

- **Infrared eccentric photorefraction** using a NoIR camera and 850 nm IR LED arrays across three angular meridians (0°, 60°, 120°).
- **Automated refractive estimation** — pupil segmentation, Purkinje reflex removal, meridian intensity profiling, and power-vector calculation (M, J₀, J₄₅) to derive sphere, cylinder, and axis.
- **Secure data handling** — database storage designed to encode/protect sensitive patient information (aligned with Peru's Ley N.° 29733).
- **Automated PDF reporting** — sphere/cylinder/axis per eye, red reflex status, and a qualitative amblyopia risk classification (low/moderate/high), delivered to parents via a verified email link.
- **Child-friendly industrial design** — capybara-shaped 3D-printed enclosure, no exposed sharp parts or cables, operator-facing screen, and an interactive audio module (child-like voice) to capture the child's attention and cooperation.
- **Photobiological safety by design** — LED irradiance verified against IEC 62471 corneal and retinal exposure limits with wide safety margins.
- **Low-cost, portable form factor** — built for under S/1,300 in components, weight and dimensions compatible with transport in a standard school backpack.

## System Architecture

CapiCam's pipeline is organized into four functional modules:

```
┌─────────────────────┐     ┌──────────────────────────┐     ┌───────────────────┐     ┌────────────────────────┐
│  Image Acquisition   │ --> │   Image Processing &      │ --> │  Secure Database   │ --> │  Automated Reporting    │
│  (NoIR camera + IR   │     │   Refractive Estimation   │     │  (encoded sensitive │     │  (PDF + email delivery  │
│  LED array, 3 arms)  │     │   (pupil segmentation,    │     │   patient data)     │     │  to parent/guardian)    │
└─────────────────────┘     │   meridian profiles,       │     └───────────────────┘     └────────────────────────┘
                             │   power vectors M/J0/J45)  │
                             └──────────────────────────┘
```

1. **Acquisition:** the device captures pupil images of both eyes under sequential infrared illumination from three angular arms (0°, 60°, 120°), at six intensity levels (0–100% duty cycle) each, at a fixed 50 cm working distance in a low ambient-light setting (<50 lux).
2. **Processing:** each image is converted to 8-bit grayscale; the eye region is located with MediaPipe Face Mesh; the pupil is segmented via the Circular Hough Transform; the first Purkinje reflex is detected and removed using thresholding + morphological operations, followed by Telea inpainting; intensity profiles are extracted along the three meridians and fit via least-squares linear regression to obtain slopes, which are converted into meridional refractive powers.
3. **Refractive computation:** meridional powers R(0°), R(60°), R(120°) are combined via Fourier decomposition into power vectors M, J₀, J₄₅, which are then converted into the clinical sphere/cylinder/axis notation.
4. **Reporting & storage:** results, together with red reflex status and a qualitative amblyopia risk classification, are stored in a remote database and compiled into a PDF report, accessible to the parent/guardian via an emailed link verified against the child's identity document.

## Hardware Used

The final constructed prototype integrates:

| Component | Notes |
|---|---|
| Raspberry Pi 4 | Onboard minicomputer / processing unit |
| Raspberry Pi NoIR Camera v3 | Camera without IR-cut filter, for infrared image capture |
| 5" Raspberry Pi LCD touchscreen | Operator-facing live image display |
| Infrared LEDs, 850 nm nominal (~9 per meridian, 3 meridians) | Illumination source; distributed at 0°, 60°, 120° with 2/3/4 emitters per arm at increasing eccentricity for extended dynamic range |
| NPN 2N2222A transistor | Sequential LED-arm switching via Raspberry Pi GPIO |
| 3D-printed capybara-shaped enclosure | Child-friendly housing for all electronics |
| Adjustable tripod + custom 3D-printed mount adapter | Stable camera height adjustment during screening |


**Bill of materials (approximate, per the reference cost estimate):**

| Component | Estimated Cost (PEN) | Availability |
|---|---|---|
| IR LEDs 850 nm (×100) | S/ 83.30 | Low — import |
| Raspberry Pi NoIR Camera v3 | S/ 200.00 | High — available in Peru |
| Raspberry Pi 4 (4 GB) | S/ 510.00 | Medium — import |
| 5" Raspberry Pi LCD screen | S/ 315.00 | High — available in Peru |
| 3D printing | S/ 150.00 | High — available in Peru |
| **Total** | **S/ 1,258.00** | Moderate |

## Software & Technologies

Based on the methodology described in the paper, the processing pipeline relies on:

- **MediaPipe Face Mesh** — facial/eye-region landmark detection.
- **OpenCV** — Circular Hough Transform for pupil segmentation; Telea inpainting for Purkinje reflex correction.
- **Least-squares linear regression** — meridian intensity-profile fitting (slope, intercept, R²).
- **Custom calibration model** — `Refraction = 0.98 × slope + 1.35` (coefficients adopted from the reference calibration study [16]), plus Fourier decomposition into power vectors (M, J₀, J₄₅).
- Remote/secure **database** for encoded storage of sensitive patient data.
- **Automated PDF report generation** and **email-based delivery** with identity verification.


## Development Methodology

CapiCam was developed as an **applied engineering project**, structured in two stages:

1. **Design and prototype characterization** — definition of 6 measurable functional/ergonomic requirements, physical design and construction, and photobiological safety characterization.
2. **Experimental validation on adult subjects** — preliminary functional and usability evaluation, performed prior to the (pending) pediatric screening phase, since calibration factors for photorefractors are known to vary with the optical system, light source, and evaluated population.

**Design requirements and measurable criteria:**

| Requirement | Criterion |
|---|---|
| Portability | Total weight < 1.5 kg; dimensions compatible with a standard school backpack |
| Photobiological safety | LED irradiance never exceeds IEC 62471 corneal/retinal limits; ≥1 order-of-magnitude safety margin |
| Speed | 1–2 minutes of screening time per child |
| Low cost | Total component budget benchmarked against commercial devices (PlusOptiX, blinq®) |
| Intuitive interface | Qualitative evaluation via direct observation during pilot tests |
| Child-friendly design | Qualitative evaluation via direct observation during pilot tests |

**Applicable standards/regulations considered:**

| Standard | Description |
|---|---|
| IEC 62471 | Photobiological safety of lamps and lighting systems |
| ISO 15004-1 | Fundamental requirements for ophthalmic instrumentation |
| DIGEMID standards (Peru) | Regulatory requirements for medical devices in Peru |
| IEC 60601 | Electrical safety and essential performance of medical electrical equipment |
| Ley N.° 29733 (Peru) | Peruvian Personal Data Protection Law |
| ISO/IEC 27001 | Information security management systems |

Ethical oversight: <cite index="4-9">the experimental protocol was submitted to the PUCP Ethics Committee for review, with a subsequent evaluation planned by the Ethics Committee of the Instituto Nacional de Oftalmología before starting the pediatric screening phase.</cite> All measurements described were performed exclusively on adult volunteers under informed consent, following the principles of the Declaration of Helsinki.

## Operating Workflow

1. Operator positions the child in front of the device at a fixed 50 cm working distance, in a low-ambient-light room (<50 lux).
2. The interactive audio module engages the child's attention and gaze fixation.
3. The system sequentially illuminates each of the three LED arms (0°, 60°, 120°) at six intensity levels, capturing images of both eyes (~60–90 seconds per eye total).
4. Captured images are processed: grayscale conversion → eye localization → pupil segmentation → Purkinje reflex correction → meridian intensity-profile extraction and linear fitting.
5. Meridional powers are converted into power vectors (M, J₀, J₄₅) and then into clinical sphere/cylinder/axis values.
6. Results (per eye), red reflex status, and a qualitative amblyopia risk classification (low/moderate/high) are stored in the database.
7. A PDF report is automatically generated and a secure link is emailed to the parent/guardian, accessible after identity verification.

## Results

- **Prototype:** all electronic components were successfully integrated into a single portable enclosure, manageable by a single operator.
- **Photobiological safety (IEC 62471, 850 nm array, 1000 s conservative exposure):**
  - <cite index="6-1,6-2">Total corneal irradiance measured for the nine-LED array was 0.09 W·m⁻², representing a safety factor of approximately 1111 times below the normative limit.</cite>
  - <cite index="6-2,6-3">Retinal thermal risk radiance measured was 1147 W·m⁻²·sr⁻¹, resulting in a safety factor of approximately 9 times below the limit.</cite>
  - <cite index="6-3">Since actual device use is under 90 seconds per eye (versus the 1000 s conservative assumption), the real safety margin during a screening session is considerably higher than reported.</cite>
  - <cite index="6-3">Spectrometric measurements confirmed an emission peak around 847 nm, close to the nominal 850 nm and consistent with better NoIR sensor sensitivity compared to the 940 nm alternative evaluated initially.</cite>
- **Pupil detection:** the face-localization and pupil-segmentation algorithm consistently identified the pupil across acquired infrared images, including participants wearing corrective lenses. Purkinje reflex removal (masking + inpainting) produced intensity profiles free of abrupt discontinuities attributable to the reflex.
- **Intensity profiles:** meridian intensity profiles showed approximately linear behavior in the selected fitting region for most records, yielding coefficients of determination adequate to support conversion to refractive power.
- **Refractive parameter estimation (illustrative record):** spherical equivalent of 0.57 D (J₀ = 0.36, J₄₅ = −0.37) → sphere 1.09 D, cylinder −1.03 D, axis 157°.

| Participant | Eye | Real Sphere (D) | Percentage Error | Estimated Sphere (D) |
|---|---|---|---|---|
| Participant 1 | OD | 1.05 | 67.70% | 0.34 |
| Participant 1 | OI | 1.55 | 69.90% | 0.47 |
| Participant 2 | OD | 3.55 | 63.40% | 1.30 |
| Participant 2 | OI | 3.15 | 70.70% | 0.92 |

Across all measured records, the average percentage error between CapiCam's estimate and participants' real sphere was **≈67.93% (SD 3.27)**.

- **Reporting system:** the system successfully generated automated PDF reports (sphere/cylinder/axis, red reflex status, qualitative amblyopia risk level) and delivered them via a verified email link to a simulated parent/guardian portal.

> The percentage error above reflects an early-stage, uncalibrated system evaluated on adults (not the target pediatric population) using calibration coefficients borrowed from an external reference study. See [Limitations](#limitations).

## Limitations

- The reduced number of participants (five adult subjects), from an age group considerably different from the target population, limits the generalizability of these findings to the pediatric context.
- The direct adoption of calibration coefficients reported by an external study, without an independent recalibration process using trial lenses of known power, introduces a source of systematic error that has not yet been independently quantified.
- The pediatric testing phase is still pending approval from the relevant ethics committees; no result in this work can be interpreted as evidence of performance in the project's final target population (children aged 4–6).
- Measured percentage error (≈68% average) indicates the system currently captures the general trend of refractive error but with precision still insufficient to replace a formal ophthalmological exam.
- Usability was assessed only qualitatively via observation; a standardized instrument (e.g., adapted System Usability Scale) has not yet been applied.

## Future Work

- Independent recalibration of the system using trial lenses of known optical power.
- Expansion of the validation sample size.
- Upon ethics approval, execution of pilot screening tests with children aged 4–6 in educational institutions in the San Miguel district (Lima, Peru).
- Formal usability evaluation of the device by non-specialist technical operators, including a standardized usability scale (e.g., SUS) and measurement of unassisted learning time.

## Usage

> **Placeholder.** Usage instructions (running the acquisition pipeline, processing a captured session, generating a report) will be documented here once the corresponding code is published in Phase 2.

## Related Publications

> Palomino Mozo, A. A., Chavez Rivas, A. S., Gamarra Leyva, A. I., Vallejo Canchanya, A., & Cárdenas Paniagua, D. B. L. (2026). *CapiCam: sistema portátil de fotorrefracción excéntrica infrarroja para el tamizaje de factores de riesgo de ambliopía refractiva en niños de 4 a 6 años.* Pontificia Universidad Católica del Perú.

> A DOI, conference/journal name, or preprint link was not included in the provided document — let me know if you'd like it added once available.

## Authors

Developed by a Biomedical Engineering team at **Pontificia Universidad Católica del Perú (PUCP)**, Lima, Perú:

| Name | Email |
|---|---|
| André Alexis Palomino Mozo | a20223107@pucp.edu.pe |
| Allen Stirs Chavez Rivas | a20223042@pucp.edu.pe |
| Alejandra Ivonne Gamarra Leyva | a20223089@pucp.edu.pe |
| André Vallejo Canchanya | a20233774@pucp.edu.pe |
| Daniel Bagkdan Lehinad Cárdenas Paniagua | daniel.cardenasp@pucp.edu.pe |

> GitHub handles/roles for each author, plus a link to the supervising professor, are not in the paper — let me know if you'd like these added or a `CONTRIBUTORS.md`/`AUTHORS.md` file created for Phase 2.

## License

No license has been selected yet. For a research/portfolio-oriented hardware + software project like CapiCam, the **MIT License** is a common, straightforward recommendation: it's short, highly permissive, well recognized by recruiters and collaborators, and doesn't impose copyleft obligations that could complicate future clinical or commercial partnerships (e.g., with PUCP or a health institution). If patent protection around the device design becomes a concern later, **Apache 2.0** is a solid alternative, since it includes an explicit patent grant.

This is only a starting recommendation — final choice should also consider PUCP's institutional IP policies before publishing.

---

<div align="center">

*This README documents CapiCam as of the state described in the associated paper. Content will be expanded in Phase 2 as the repository structure, code, and documentation are built out.*

</div>
