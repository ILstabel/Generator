# Chronic Pain / Opioid Risk Generator

Run the Streamlit app with Python 3.10 or later:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Assessment workflow

1. Paste labeled scores and select **Parse into review fields**, or choose
   **Structured entry**. Review and correct extracted values. Blank means
   missing, not zero.
2. Select the COMM form maximum, clinical context, UDS/PDMP status and refill
   behavior. Confirm the review fields and resolve parser errors before generating.
3. Optionally select clinician-established diagnoses and enter actual QHP time.
   Patient feedback and personal-time attestations require separate confirmations.
   No diagnoses or percentage-based time allocations are automatically assigned.
4. Generate and download the report. Unverified reports are marked as drafts.
   Changing inputs hides the previous report until it is regenerated; changing
   scores or context also clears score-review, patient-feedback and clinician
   confirmations. Changing actual time clears its attestation.

Sample buttons load synthetic low, moderate, high and incomplete assessments.
Complete samples include consistent UDS/PDMP and stable refill selections.
The incomplete sample also demonstrates a positive PHQ-9 item 9 alert.
Sample reports remain watermarked even after editing. **Reset assessment**
clears all assessment inputs and confirmations before real data entry.

Accepted examples:

```text
PEG: 8 + 10 + 6 / 3 = 8
PDI Total: 40 / 70
PHQ-9 Score: 19 / 27
Question 9. Answer: 0
COMM-16 Total: 0 / 64
ORT: 4 / Moderate Risk
```

PEG can also be entered as `PEG Average: 8 / 10`. PHQ-4 is supported, for
example `PHQ4: 6 / 12`. Explicit COMM maxima of 68, 64 and 28 are supported;
an unspecified form defaults to 68 **with a review warning**. Repeated score
labels, invalid ranges, inconsistent denominators and conflicting ORT labels
are flagged rather than silently resolved. The parser is a convenience for
labeled text, not a general document-extraction system.

## Clinical limitations and intentional behavior changes

- The retained point formula is **app-defined, not a validated clinical
  prediction model**. The app does not establish diagnoses, treatment decisions,
  billing eligibility or acute suicide risk.
- Classification requires PEG, PDI, COMM, ORT, a PHQ-9 or PHQ-4 total,
  completed UDS/PDMP review, and refill review. PHQ-9 also requires item 9.
  ORT was previously optional; it is now required for classification to avoid
  treating an unknown baseline-risk input as negative. Pending UDS is incomplete.
- Missing required information produces **Insufficient information**, without
  an overall classification or repeat interval. Available point contributions
  and safety alerts remain visible. Missing flags read **Not assessed**.
  Completeness refers only to app-required fields, not comprehensive clinical care.
- The unchanged formula assigns COMM 2 points at 9 and 3 at 18; ORT 1 at 4
  and 3 at 8; PHQ-9 1 at 15 and 2 at 20, or PHQ-4 1 at 6 and 2 at 9.
  Positive item 9 adds 3. Discordant UDS/PDMP adds 3, provider-review findings
  add 2. Early/lost refill concerns add 2; intermittent/review concerns add 1.
  Context adds up to 3 points. Low is 0-1, Moderate 2-4, High 5 or more.
  COMM threshold applicability to different forms is **not established** here.
- PEG and PDI affect flags, not risk points. PEG averages below 4 are low,
  4 to below 7 moderate, and 7 or above high, aligning the high category with
  the existing severe-pain flag. PHQ-9 takes precedence over PHQ-4 for both
  risk points and mood flags when both are supplied.
- Retained source repeat guidance is 3 months for High, 6 for Moderate and 12
  for Low, subject to clinician review.
- A positive PHQ-9 item 9 produces an independent same-day-assessment alert.
  A zero response does not rule out risk; an absent response is not negative.
  PHQ-4 does not assess suicidal ideation.
- ORT is checked for non-negative whole numbers only; no questionnaire-specific
  upper bound is asserted without identifying the version.

## Tests

The suite uses standard-library `unittest` and Streamlit's installed testing API:

```powershell
python -m unittest -v test_app
```

Tests cover parsing, validation, exact scoring boundaries, missing information,
report confirmations, synthetic data, safety alerts, reset, stale-report hiding,
and the interactive Streamlit workflow.
