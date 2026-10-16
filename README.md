# Chronic Pain / Opioid Risk Generator

## Quick start (first time)

> **No Python?** Windows users can run the portable version instead: unzip
> `Generator-portable.zip` and double-click `Start Generator.bat`. See
> [Sharing with someone who has no Python](#sharing-with-someone-who-has-no-python-portable-windows-version).

1. Install [Python 3.10 or later](https://www.python.org/downloads/) (tick
   **Add Python to PATH** during installation) and
   [Git](https://git-scm.com/downloads), or use **Code > Download ZIP** on
   GitHub and unzip it.
2. Open PowerShell (Windows) or Terminal (Mac) and run:

   ```powershell
   git clone https://github.com/ILstabel/Generator.git
   cd Generator
   python -m pip install -r requirements.txt
   python -m streamlit run app.py
   ```

3. The app opens in your browser at `http://localhost:8501`. To try it, pick
   **All Assessments** in the sidebar, choose the `2026_10_14` folder and select
   **Calculate and save scores**. The included forms (`10001`-`10003`) are
   synthetic test forms, not real patients.

For step-by-step instructions, worked examples and troubleshooting, see the
[User Manual](USER_MANUAL.md).

Everything runs on your own computer; no forms or results are uploaded.
Results are written to a `patient_results` folder, which Git ignores. New PDFs
you add to `patient_forms` are also ignored by Git, so real patient forms are
never committed by accident.

## Running the app

Run the Streamlit app with Python 3.10 or later:

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Use the same Python environment for installation and running Streamlit.
If you see `ModuleNotFoundError: No module named 'cv2'`, install
`opencv-python-headless` through the Python executable running the app;
`cv2` is its import name, not its package name. For the base Anaconda
environment with NumPy 1.x, run these commands from the project directory:

```powershell
& "$env:USERPROFILE\anaconda3\python.exe" -m pip install -r requirements.txt "numpy<2"
& "$env:USERPROFILE\anaconda3\python.exe" -m streamlit run app.py
```

The NumPy constraint preserves compatibility with existing NumPy 1.x packages
in that shared environment. Restart Streamlit after installing dependencies.

The **Clinical Teal** colour theme is set in `.streamlit/config.toml`; edit
`primaryColor` and the background colours there to change it. The sidebar's
green background (`#CFE6DD`) is set by `SIDEBAR_STYLE` in `app.py`. Tables
stretch to the page width and show every row; their header rows (and input
boxes) use the sage `secondaryBackgroundColor` `#DCEBE4`. The report's
risk banner is green for Low, amber for Moderate, red for High and grey when
the assessment is incomplete.

The app has three tabs: **Assessment** (forms, scores and reports),
**Insights** (charts of the clinic's saved assessments and patient trends) and **About** (a plain-language summary of
what the app does, how risk points are calculated, and the questionnaire
scoring rules with references).

## Sharing with someone who has no Python (portable Windows version)

The `portable` folder builds a self-contained Windows 64-bit copy that includes
its own Python, so the recipient installs nothing.

**Build it** (on a Windows computer with internet and Python 3.12, the same
minor version as the bundled Python): double-click `portable\Build portable.bat`,
or run

```powershell
$env:GENERATOR_BUILD_PYTHON = "C:\path\to\python3.12\python.exe"   # if `python` is another version
powershell -ExecutionPolicy Bypass -File portable\build_portable.ps1   # add -NoZip to skip zipping
```

This downloads the python.org embeddable Python 3.12.7, installs the pinned
`requirements.txt` packages into it, copies the app, the Git-tracked sample
forms and the synthetic **TEST01–TEST08** patients (created fresh by
`make_test_records.py`), checks the imports and writes
`dist\Generator-portable.zip`. Local patient forms and saved results are never
copied. `dist` is Git-ignored.

**Send the zip** (it is too large for most e-mail; use OneDrive, Google Drive or
a USB stick). The recipient:

1. Extracts the zip to a writable folder (for example Documents).
2. Double-clicks `Generator\Start Generator.bat`. The browser opens
   `http://localhost:8765` (localhost only, not visible on the network).
3. Closes the black window to stop the app.

Windows SmartScreen may ask once: **More info > Run anyway**. Forms go in
`Generator\app\patient_forms` and results are saved in
`Generator\app\patient_results`. `READ ME FIRST.txt` in the zip repeats these
steps. To remove the TEST patients, delete the `TEST*` files in
`patient_results`.

## Sharing a public demo (Streamlit Community Cloud)

Use made-up forms only. Everything in `patient_forms/` that is committed to
GitHub is visible to every visitor of the demo.

1. Push this repository to GitHub.
2. Sign in at <https://share.streamlit.io> with GitHub and choose **Create app**.
3. Pick the repository, branch `main` and main file `app.py`. Under
   **Advanced settings**, choose Python 3.12 and paste this into **Secrets**:

   ```toml
   DEMO_MODE = "true"
   ```

   This shows a "do not enter real patient information" banner.
4. Choose **Deploy**. When it is running, open the app's **Share** settings and
   make it public to get a link anyone can open.

Saved results on the demo are shared by all visitors and are cleared whenever
the site restarts or redeploys. `requirements.txt` pins the versions the tests
were run with.

## Assessment workflow

### Calculate scanned patient forms by date folder

Store patient PDFs locally, outside Git, in this structure:

```text
patient_forms\
  2026_10_14\
    Patient A.pdf
    Patient B.pdf
  2026_10_15\
    Patient C.pdf
```

1. In the **Select Assessment** sidebar, choose what to calculate:
   - **All Assessments:** pick one folder name from the **Folder** dropdown.
     Every PDF directly inside it is calculated.
   - **Individual Assessments:** type or pick a code (for example `10001`) in
     **Patient / record score**. Every date folder containing `10001.pdf` is
     inspected (listed under **Visits found**); the newest visit is saved.
     Turn on **Manual / visual inspection** to see scan previews and every
     detected response.

   Folder names are visit-date labels (`YYYY_MM_DD`); the app does not infer
   visit dates or identity from handwriting.
2. The PDFs must use the supported six-page layout, in this order: PHQ-9,
   PEG, PDI, ORT-OUD, COMM-16 page 1 and COMM-16 page 2. Each page's scan
   size, table header, columns and response boxes are checked automatically;
   a PDF that does not match is rejected with an error.
3. Select **Calculate and save scores**. Each PDF is inspected separately and
   its scores are saved automatically as `<code>_score.json` and
   `<code>_score.txt` (see below). An unreadable or unsupported PDF produces
   an explicit error without blocking other files.
4. The **All Assessments Scores** table shows one compact row per patient
   (visit date, overall risk, each total with its band, `*` for provisional
   totals, response-review and saved status). Pick a **Patient code** under
   **Individual Total Scores** for the full details (in **Individual
   Assessments** mode the headings read **Individual Assessment Scores** and,
   with manual inspection on, **Individual Manual Inspection**). Its
   calculated totals automatically fill the **Paste text** box and review
   fields (marked as not verified); select **Complete assessment** to use them.
5. To verify responses, use **Individual Assessments** with **Manual / visual
   inspection** on. Check each response crop, correct detected values and leave
   truly missing or ambiguous responses unresolved. Confirm the review, then
   select **Load reviewed responses into assessment** or **Save reviewed
   results to patient record**. Loading clears previous assessment data,
   diagnoses, baseline comparisons and attestations. Complete UDS/PDMP,
   refill/context and documentation fields independently. Reports include the
   imported folder/file label.

Changing the mode, folder or patient code, or re-running the calculation, clears
old batch reviews and any assessment imported from them. Editing an imported form's batch responses
also clears that imported assessment; reload the reviewed result before reporting.

### Patient codes and saved results

Name each PDF with the patient code, for example
`patient_forms\2026_10_14\10001.pdf`. Codes may contain letters, digits, `-`
and `_` (no spaces). Files without a valid code are calculated but not saved.
A code appearing twice in one date folder is not saved.

Each patient code has **one** saved record, directly in `patient_results`:

```text
patient_results\
  10001_score.txt    readable generator report (same layout as the original HTML template)
  10001_score.json   visit folder, scores, item responses, summary rows, flags, risk, repeat interval, status
  10001_history.json totals of every saved visit (one entry per visit folder), used for patient trends
```

Every save overwrites the patient's previous record, whatever its visit date
or status (the latest save always wins). Per-patient sub-folders left by
earlier versions are deleted on the next save.

| Status | Created when |
|---|---|
| Automatic draft - responses NOT verified | Automatically after **Calculate and save scores** |
| Responses verified by user - clinician report pending | **Save reviewed results to patient record** after confirming the response review |
| Final report - clinician verification confirmed by user | **Save final report to patient record** after loading the form, generating the report and confirming clinician review |

Automatic and response-reviewed records have UDS/PDMP, refill behavior and
clinical context marked as not documented. Only the final report includes
those clinician entries.

**Visits:** when a patient has forms in several date folders, a **Visit**
selector under *Individual Total Scores* defaults to the latest visit and drives
the score details and the pre-filled assessment scores.

**Saved patient records:** choose a patient code to see the saved visit
folder, status, risk and score summary, and to view or download the report. The
code follows the patient selected under *Individual Total Scores*, so the saved
report matches the scores on screen; if an older visit is selected, a note says
the saved record is the latest visit.

`patient_results` is Git-ignored. Saved records contain patient health
information; protect this folder with appropriate access controls and backups.

**Optical-reading limits:** this is a local, experimental template-based mark
detector, not general OCR or a clinically validated document reader. It aligns
the printed table headers and suggests checkbox/circle responses only for the
current six-page portrait scan layout. It does not recognize patient identity,
signatures, narrative notes or arbitrary questionnaire versions. Other layouts,
rotation, unclear marks and missing/overlapping circles require human review.
No guarantee of detection accuracy is implied by an automatically filled field;
**every response must be verified against the displayed scan**.

All PDF/image processing stays on the computer running Streamlit, using pypdf,
Pillow, NumPy and OpenCV. It uses no external OCR/AI endpoint. With a remotely
hosted app, "local" means the server's disk, not the browser's computer. Page
images and response crops stay in the Streamlit session. Calculated results
and reports are written only to `patient_results` (see above). The
`patient_forms` and `patient_results` directories are
Git-ignored. This alone does **not** provide access controls, encryption,
compliance certification or a production-safe medical-record system.

The current six-page forms contain **ORT-OUD and modified COMM-16**. As in the
original HTML template, their totals feed the integrated risk level and repeat
interval (see the risk rules below); these mappings are not validated for
ORT-OUD or modified COMM forms. Forms from different folders are never treated automatically as the same
patient or used to populate longitudinal baselines.

### Manual assessment entry

1. Paste labeled scores and select **Complete assessment**, or choose
   **Manual entry**. Review and correct extracted values. Blank means
   missing, not zero.
2. Select the COMM form maximum, clinical context, UDS/PDMP status and refill
   behavior. Confirm the review fields and resolve parser errors before generating.
3. Optionally select clinician-established diagnoses and enter actual QHP time.
   Patient feedback and personal-time attestations require separate confirmations.
   No diagnoses are automatically assigned. Entered minutes are split as in the
   original template (review/scoring 20%, interpretation 35%, decision-making
   25%, documentation 15%, remainder feedback/care coordination).
4. Select **Generate reviewed report**, then download it. The on-screen report
   shows the Score Summary table, Clinical Flags and the template sections
   (Interval Clinical Impression, Integrated Opioid Risk Interpretation,
   Suicide Risk Assessment, Opioid Treatment Guidance, Feedback, Billing codes,
   QHP Time & Attestation). Unverified reports are marked as drafts.
   Changing inputs hides the previous report until it is regenerated; changing
   scores or context also clears score-review, patient-feedback and clinician
   confirmations. Changing actual time clears its attestation.

**Reset assessment** clears all assessment inputs and confirmations before real
data entry.

Accepted examples:

```text
PEG: 8 + 10 + 6 / 3 = 8
PDI Total: 40 / 70
PHQ-9 Score: 19 / 27
Question 9. Answer: 0
COMM-16 Total: 0 / 64
ORT: 4 / Moderate Risk
```

PEG can also be entered as `PEG Average: 8 / 10`. Only PHQ-9 is scored for
mood. Explicit COMM maxima of 68, 64 and 28 are supported;
an unspecified form defaults to 68 **with a review warning**. Repeated score
labels, invalid ranges, inconsistent denominators and conflicting ORT labels
are flagged rather than silently resolved. The parser is a convenience for
labeled text, not a general document-extraction system.

## Insights tab

The **Insights** tab summarises the saved records in `patient_results`: one
row per patient code, using the latest saved visit and the overall risk as
saved. Nothing leaves the computer.

- **Filters** for visit date, record status and overall risk (empty = **All**).
  Small selections and mixed risk-threshold presets are flagged.
- **Headline numbers** (patients, high risk, item 9 positive, insufficient
  information, final reports) and a **follow-up list**, most urgent first:
  item 9 positive, missing answers, unverified drafts, overdue repeat battery.
- **Charts:** score heatmap (outlined cells meet a clinical flag), overall-risk
  donut, PHQ-9 severity bars, clinical-flag lollipops, PEG vs PDI scatter,
  assessments per visit date, and a score distribution for a chosen measure.
- **All saved assessments** table with CSV download.
- **Patient trend** for a chosen patient (also shown in the Assessment tab):
  score lines with flag thresholds, overall risk per visit and change since the
  first visit for PEG and PDI, read from `<code>_history.json`.

`make_test_records.py` creates synthetic patients **TEST01–TEST08** (one to four
visits each, reports marked *SYNTHETIC TEST DATA*) so the tab can be tried
without real data; `python make_test_records.py --remove` deletes them.

## Questionnaire scoring rules

Interpretation labels, bands, thresholds and improvement criteria are read from
[`scoring_config.json`](scoring_config.json) (the clinical evaluation reference
table). `scoring_config.py` validates it when the app starts: every instrument
must be present and bands must be contiguous, non-overlapping and cover the
full range, otherwise the app refuses to start. Bands are inclusive whole-number
ranges; a fractional score (for example a mean-imputed PDI of 29.5) uses the
band whose minimum it has reached. Edit the JSON to change a rule. Calculation
methods (sums, proration, imputation) stay in code.

| Tool | Range | Metric | Interpretation (configured) |
|---|---|---|---|
| **PEG** | 0.0-10.0 | Continuous average | Tracking metric. Improvement: drop **>=1.0 point OR >=30%** |
| **PDI** | 0-70 | Integer sum | **0-20** Mild disability; **21-40** Moderate disability; **41-70** Severe disability (original HTML template bands). Improvement: >=30% reduction from baseline |
| **PHQ-9** | 0-27 | Integer sum | **0-4** Minimal; **5-9** Mild; **10-14** Moderate (standard clinical positive threshold); **15-19** Moderately Severe; **20-27** Severe depression risk |
| **PHQ-9 guardrail** | Item 9 | Any response >=1 | **Urgent action trigger**: overrides the total score; flags high risk for self-harm |
| **ORT-OUD** | 0-9 | 9 equally weighted Yes/No factors | **<3** Low risk for Opioid Use Disorder; **>=3** High risk for Opioid Use Disorder |
| **COMM** | 0-68 | Standard 17-item sum | **>=9** positive screen; **<9** negative. Modified forms (e.g. COMM-16) get no standard interpretation |

Notes on the supplied table:
- **ORT-OUD:** the supplied table lists "0-26 sex-weighted sum", which
  describes the original 2005 ORT. No sex weights were supplied, and the
  scanned forms use nine equally weighted Yes/No ORT-OUD factors, so scoring
  stays 0-9 and the supplied <3 / >=3 threshold is applied.
- **COMM** is not in the supplied table; the earlier supplied rules are kept.

[`html_config.json`](html_config.json) is a separate, reference-only record of
the original `Generator New.html` parameters: its PEG/PDI/PHQ-9/ORT/COMM
bands and flags, integrated-risk points and levels, UDS/PDMP, refill and
context labels, QHP time split, and ICD-10 codes. The app does not read it;
use it to compare the original HTML behavior with `scoring_config.json`.

| Instrument | Applied calculation rules |
|---|---|
| **PHQ-9** | Nine-item scoring, proration for 1-2 missing answers, provisional answered-item sum for 3+, configured bands, item 9 guardrail, and separate functional impairment |
| **PEG** | Three-item mean (mean of answered items when blank), rounded clinical score, exact mean retained, and configured improvement rule against a prior score |
| **PDI** | Seven-domain sum, mean imputation for one missing domain, provisional answered-domain sum for 2+, configured bands, and baseline percentage change |
| **ORT-OUD** | Nine equally weighted Yes/No factors; blanks skipped; configured threshold; kept separate from original ORT |
| **COMM** | Standard 17-item sum, no reverse scoring, blanks skipped, positive screen >=9; modified forms clearly distinguished |

### Blank or unanswered items

Blank, unresolved or unclear answers never stop a score from being calculated
and are never scored as zero. They are skipped, the total is still shown, and
each blank item is named as **needs review** in the summary, the report and the
assessment-completeness line.

| Questionnaire | A few blanks | More blanks |
|---|---|---|
| PHQ-9 | 1-2 blank: scaled up from the answered items (proration) | 3+ blank: answered items added up, marked **PROVISIONAL** |
| PDI | 1 blank: filled with the average of the other six answers (mean imputation) | 2+ blank: answered items added up, marked **PROVISIONAL** |
| PEG | Average of the answered items, marked **PROVISIONAL** | Same |
| ORT-OUD, COMM | Answered items added up, marked **PROVISIONAL** | Same |

- If every item in a questionnaire is blank, it remains **Not scored**.
- Severity labels (for example "5 / 9; High risk") still apply to provisional
  totals. One blank PHQ-9 item (prorated) or PDI domain (mean-imputed) is
  flagged but does not block the overall risk level; any other blank, or 2+
  blank PHQ-9 items, keeps the assessment **incomplete**, so no overall risk
  level or repeat interval is assigned until the blanks are reviewed.
- As in the original HTML template, COMM points (>=9: 2; >=18: 3) apply to
  every COMM form, ORT points (>=4: 1; >=8: 3) apply to ORT-OUD too, and
  unreviewed UDS/PDMP or refill adds 0 points and is listed as pending review.
- PHQ-9 item 9 is never imputed; a blank item 9 is always flagged.
- Ambiguous scanned marks are handled separately: the reader chooses the
  number or box with the largest marked area and labels it **AMBIGUOUS -
  verify against scan**.

Item-level responses come from the scanned forms (corrected in **Manual /
visual inspection**); the assessment review fields hold totals only. Pasted
text extracts labeled totals, not questionnaire answers. Total entry cannot
verify how missing items were handled; the report states that limitation.
Never convert an unclear or double-marked answer to zero.

### PHQ-9

- Assess frequency over the **past 2 weeks**. Score items 1-9 as:
  Not at all = 0; Several days = 1; More than half the days = 2;
  Nearly every day = 3.
- All 9 answered: sum the responses, producing **0-27**.
- Exactly 1 or 2 missing: `answered-item sum * 9 / number answered`.
  Preserve the raw sum, answered count and exact result in the report, and
  round the prorated total to the nearest whole number for interpretation,
  following the APA clinician instructions. The app uses half-up rounding
  (13.5 becomes 14), not Python's ties-to-even rounding.
- At least 3 missing: answered items are added up as a **PROVISIONAL** total
  and the blank items are flagged for review.
- Severity (configured): **0-4 Minimal**, **5-9 Mild**, **10-14 Moderate
  (standard clinical positive threshold)**, **15-19 Moderately Severe**,
  **20-27 Severe depression risk**. Screening severity is not a diagnosis.
- Any observed **item 9 >= 1** is an **urgent action trigger** that overrides
  the total-score interpretation, and requires an **immediate clinician
  suicide-risk assessment and safety protocol**, even if the total cannot be calculated.
  Never impute item 9's safety response. A prorated total with item 9 missing
  remains insufficient for the app's overall-risk classification.
- Functional impairment (item 10) records work, home-life and relationship
  difficulty: Not difficult at all, Somewhat difficult, Very difficult, or
  Extremely difficult. It is optional documentation, **not added to the
  PHQ-9 total or the app's risk points**.

Sources supplied for these rules:
[PAR technical supplement](https://www.parinc.com/Portals/0/Webuploads/samplerpts/ChecKIT%20Series_PHQ-9_Tech%20Supp%20Paper.pdf),
[APA clinician scoring instructions](https://www.psychiatry.org/getmedia/a3986be5-94af-42e7-afce-19234c2f4998/APA-DSM5TR-SeverityMeasureForDepressionAdult.pdf),
[PHQ-9 calculator](https://www.mdcalc.com/calc/1725/phq9-patient-health-questionnaire9),
[BC functional-impairment form](https://www2.gov.bc.ca/assets/gov/health/practitioner-pro/bc-guidelines/depression_patient_health_questionnaire.pdf).

### PEG-3

- Enter three **0-10** ratings: pain, enjoyment interference and general
  activity interference, for the past week. A blank rating is skipped: the
  mean of the answered ratings is shown as **PROVISIONAL** and the blank is
  flagged for review.
- Calculate `(pain + enjoyment + general activity) / 3`.
  Preserve the exact mean; display the clinical score rounded to the nearest
  whole number using half-up rounding, per the supplied implementation rule.
  Pasted expressions may state either the exact mean or the rounded clinical
  score, e.g. `PEG: 6 + 4 + 4 / 3 = 5`; the exact mean is still retained.
- PEG is an individual **longitudinal pain/interference measure, not a diagnosis**.
- Optionally enter a prior PEG score (prefer the unrounded mean). Compare the
  current **unrounded mean** with that score to avoid rounding artifacts.
  A decrease of **at least 1.0 point OR at least 30%** meets the configured
  improvement criterion. A zero baseline has no defined percentage reduction,
  so only the point rule applies.
- No patient history is stored or retrieved automatically; the prior score
  must be supplied for the same patient and a comparable assessment.

Sources supplied:
[PEG form](https://northwestpainguidance.org/wp-content/uploads/2016/05/PEG-3.pdf),
[Washington AMDG form](https://amdg.wa.gov/Files/AssessmentTools/1-PEG%203%20item%20pain%20scale.pdf),
[supplied improvement discussion](https://pabau.com/blog/pain-assessment-scales/).
The whole-number rounding and improvement criterion are implemented as configured
protocol rules, not claims of universal diagnostic thresholds.

### Pain Disability Index (PDI)

- Rate seven domains **0-10**: family/home responsibilities, recreation,
  social activity, occupation, sexual behavior, self-care and life-support
  activity. Zero means no disability/interference; 10 means total.
- All seven answered: sum them for **0-70**.
- Exactly one missing: impute the missing domain using the mean of the six
  answered domains; total = `answered-item sum * 7 / 6`. Preserve the fractional
  result without rounding. Report the imputed value, observed subtotal and
  missing domain, rather than presenting it as a fully observed score.
- Two or more missing: answered domains are added up as a **PROVISIONAL**
  total and the blank domains are flagged for review.
- Configured bands: **0-20 Mild disability**, **21-40 Moderate disability**,
  **41-70 Severe disability**. A fractional imputed total takes the band
  whose minimum it has reached (20.5 is Mild, 40.5 is Moderate). These bands come from the
  supplied reference table; screening results, not diagnoses.
- Optionally enter the patient's baseline PDI score. Calculate
  `(baseline - current) / baseline * 100`. A reduction **>=30%** meets the
  supplied progress criterion. The zero-baseline percentage is undefined.
  Interpret changes cautiously when comparing observed and imputed scores.

Sources supplied:
[PDI form](https://www.caltcm.org/assets/Pain-file/pain%20disability%20index.pdf),
[study cited for missing-domain handling](https://pmc.ncbi.nlm.nih.gov/articles/PMC6137945/),
[supplied interpretation discussion](https://resref.com/pain-disability-index-assessment-guide/),
[supplied progress reference](https://www.scribd.com/document/471487635/pain-disability-index).
Mean imputation and the exact 30% progress threshold are **supplied protocol
rules**, not universal diagnostic or treatment-success guarantees.

### Revised Opioid Risk Tool (ORT-OUD)

- Select **ORT-OUD** under **Opioid risk instrument**. Switching versions
  clears the previous total and ORT-OUD responses to prevent reinterpreting
  an original ORT score as an ORT-OUD score.
- Enter its total **0-9**, or load it from a scanned form's nine factors.
  Each explicit Yes adds 1; No adds 0. Blank/unresolved answers are skipped
  (not counted as No) and flagged for review; the total is **PROVISIONAL**.
- Factors: family history of alcohol, illegal-drug and prescription-drug abuse;
  personal history of those three; age 16-45; depression history; and history
  of ADD, OCD, bipolar disorder or schizophrenia.
- **0-2 Low risk for Opioid Use Disorder; 3-9 High risk for Opioid Use
  Disorder** (configured). There is no Moderate category, no sexual-abuse
  item and no sex-based weighting in this version.
- A high result calls for clinician assessment of risk mitigation, monitoring
  and non-opioid multimodal options, not an automatic diagnosis or prescribing
  decision. Intended use is initial pain-management risk assessment.
- Pasted labeled totals such as `ORT-OUD: 5 / 9 / High Risk` are recognized
  as this version. Plain `ORT: 5` remains **Original ORT**, not ORT-OUD.
- **No validated mapping from ORT-OUD to the combined-risk formula has been
  supplied.** As in the original HTML template, the ORT points (>=4: 1;
  >=8: 3) are applied to the ORT-OUD total; the clinician must verify this.

Sources:
[NIDA ORT-OUD](https://nida.nih.gov/nidamed-medical-health-professionals/screening-tools-resources/opioid-risk-tool-oud-ort-oud),
[revised ORT-OUD scoring](https://www.mdcalc.com/calc/10483/revised-opioid-risk-tool-ort-oud).
The original ORT option remains available for existing forms with its original
0-3 / 4-7 / >=8 categories; it is not silently migrated.

### Current Opioid Misuse Measure (COMM)

- The standard instrument contains **17 items**, assessing the **past 30 days**
  in people already receiving long-term opioid therapy.
- Never = 0, Seldom = 1, Sometimes = 2, Often = 3, Very Often = 4.
  Sum all 17 responses for **0-68**, with **no reverse-scored items**.
- **>=9: positive current-misuse screen**, warranting further clinician
  assessment and consideration of monitoring/testing or plan review.
  **<9: negative screen**, not proof of absence of misuse; continue appropriate
  monitoring. A screen does not establish opioid use disorder or independently
  determine treatment.
- Some settings use a threshold of 13 for greater specificity. This app uses the
  supplied default **9** only; it does not silently select an alternative.
- Item-level scoring comes from the scanned form; a reviewer-verified total
  can also be entered. Missing/unresolved answers are skipped: the sum
  of the answered items is shown as a **PROVISIONAL** total and each blank
  item is flagged for review. No imputation/proration is applied.
- The supplied 16-item form and the previously supported 7-item format are
  labeled **modified forms**. Their raw totals (0-64 / 0-28) are interpreted
  with the standard >=9 threshold, as in the original HTML template, and labeled
  as such; no version-specific threshold has been validated. Do not assume the
  16-item form is simply the standard instrument minus one identifiable question.
- Changing the selected COMM form clears prior totals/item responses and
  review confirmations so scores cannot silently cross versions.
- The combined formula assigns 2 points at >=9 and 3 at >=18 for **every** COMM
  form, as in the original template. The 18 threshold is a custom app weight,
  not an additional validated COMM screening category.

Sources:
[standard COMM form and scoring](https://www.utahmed.org/Common/Uploaded%20files/Docs/CS_Resources/COMM%20-%20Current%20Opioid%20Misuse%20Measure.pdf),
[standard form](https://tapmipain.ca/assets/pdfs/Current%20Opioid%20Misuse%20Measures.pdf),
[supplied study](https://pmc.ncbi.nlm.nih.gov/articles/PMC6699803/),
[COMM calculator](https://www.mdcalc.com/calc/10428/current-opioid-misuse-measure-comm).

## Clinical limitations and intentional behavior changes

- The retained point formula is **app-defined, not a validated clinical
  prediction model**. The app does not establish diagnoses, treatment decisions,
  billing eligibility or acute suicide risk.
- Classification requires PEG, PDI, COMM, ORT and a PHQ-9 total with item 9
  (no other mood scale substitutes for PHQ-9). UDS/PDMP and refill reviews are recommended but do not
  block the risk level.
  ORT was previously optional; it is now required for classification to avoid
  treating an unknown baseline-risk input as negative. Pending UDS is incomplete.
- Missing required information produces **Insufficient information**, without
  an overall classification or repeat interval. Available point contributions
  and safety alerts remain visible. Missing flags read **Not assessed**.
  Completeness refers only to app-required fields, not comprehensive clinical care.
- The formula assigns COMM 2 points at 9 and 3 at 18; ORT 1 at 4 and 3 at 8
  (Original ORT and ORT-OUD); PHQ-9 1 at 15 and 2 at 20.
  Positive item 9 adds 3. Discordant UDS/PDMP adds 3, provider-review findings
  add 2. Early/lost refill concerns add 2; intermittent/review concerns add 1.
  Context adds up to 3 points. Low is 0-1, Moderate 2-4, High 5 or more.
- These are the defaults (**Original template** preset). The sidebar's
  **Risk Thresholds** section offers Conservative and Lenient presets and a
  Custom option that move the COMM, ORT and PHQ-9 thresholds and the
  Moderate/High point totals (defined in `risk_thresholds.py`). Points per
  tier, item 9, UDS/PDMP, refill and context rules do not change. Custom
  values are checked (moderate below high); invalid values fall back to the
  default. Non-default thresholds are noted in the report, Score Summary and
  saved record; the choice lasts for the browser session only.
- PEG and PDI are continuous tracking measures, not risk-point inputs.
- Retained source repeat guidance is 3 months for High, 6 for Moderate and 12
  for Low, subject to clinician review.
- A positive PHQ-9 item 9 produces an independent immediate-assessment alert.
  A zero response is a complete, normal answer (no suicidal ideation endorsed);
  only a blank item 9 is flagged as not documented, and is never treated as 0.
- Original ORT is checked for non-negative whole numbers only; ORT-OUD
  is restricted to whole-number totals 0-9.

## Tests

The suite uses standard-library `unittest` and Streamlit's installed testing API:

```powershell
python -m unittest -v test_app test_form_reader test_clinic_insights
```

Tests cover parsing, validation, exact scoring boundaries, missing information,
report confirmations, synthetic data, safety alerts, reset, stale-report hiding,
and the interactive Streamlit workflow.
Additional coverage verifies PHQ-9 proration and every severity score, independent
item 9 alerts, functional impairment, PEG rounding/change, PDI mean imputation,
missing-response limits and baseline comparisons.
ORT-OUD coverage verifies binary scoring, the 2/3 boundary, explicit version
selection, missing responses, total range and template risk points.
COMM tests cover the full 0-68 range, no reverse scoring, the 8/9 threshold,
partial subtotals, modified-form labeling and clearing scores on form changes.
Synthetic scan tests cover date-folder discovery, multiple PDFs, checkbox/circle
detection, blank and double marks, unsupported PDFs, mandatory response review,
source mapping, overwriting per-patient records and importing one reviewed form
without merging other patients. Report tests check every original-template
section. Insights tests cover loading saved records, filters, the follow-up list,
heatmap data, patient trends and the tab layout.
