# Chronic Pain / Opioid Risk Generator — User Manual

This manual explains how to install, start and use the app step by step. It is
for clinic staff and clinicians and assumes no programming knowledge. Words in
**bold** are the exact labels you will see on screen.

> **Safety first.** This app is a support tool. It reads forms and adds up
> scores, but a qualified clinician must check every score, risk level,
> recommendation, diagnosis and report before use. A positive answer to PHQ-9
> question 9 (thoughts of self-harm) always needs a same-day clinician
> suicide-risk assessment, whatever the other scores are.

## Contents

1. [What the app does](#1-what-the-app-does)
2. [What you need](#2-what-you-need)
3. [Installing the app (first time only)](#3-installing-the-app-first-time-only)
4. [Starting, stopping and updating the app](#4-starting-stopping-and-updating-the-app)
5. [A tour of the screen](#5-a-tour-of-the-screen)
6. [Preparing patient forms](#6-preparing-patient-forms)
7. [Scoring a whole visit day (All Assessments)](#7-scoring-a-whole-visit-day-all-assessments)
8. [Scoring one patient (Individual Assessments)](#8-scoring-one-patient-individual-assessments)
9. [Checking and correcting answers (Manual / visual inspection)](#9-checking-and-correcting-answers-manual--visual-inspection)
10. [Completing the assessment form](#10-completing-the-assessment-form)
11. [Documentation confirmations](#11-documentation-confirmations)
12. [Generating, downloading and saving the report](#12-generating-downloading-and-saving-the-report)
13. [Entering scores without a scanned form](#13-entering-scores-without-a-scanned-form)
14. [Saved patient records](#14-saved-patient-records)
15. [The Insights tab](#15-the-insights-tab)
16. [The About tab](#16-the-about-tab)
17. [Worked examples with the sample forms](#17-worked-examples-with-the-sample-forms)
18. [How scores and risk are calculated](#18-how-scores-and-risk-are-calculated)
19. [Privacy and data](#19-privacy-and-data)
20. [Troubleshooting](#20-troubleshooting)
21. [Frequently asked questions](#21-frequently-asked-questions)
22. [Glossary](#22-glossary)

---

## 1. What the app does

Patients fill in a six-page paper questionnaire packet at their visit. The
packet contains five questionnaires:

| Questionnaire | What it measures | Questions | Score range |
|---|---|---|---|
| **PHQ-9** | Depression / mood, including question 9 on thoughts of self-harm | 9 (0–3 each) | 0–27 |
| **PEG** | Pain intensity and how pain interferes with enjoyment and activity | 3 (0–10 each) | average 0–10 |
| **PDI** (Pain Disability Index) | How pain limits seven areas of daily life | 7 (0–10 each) | 0–70 |
| **ORT-OUD** (Opioid Risk Tool) | Risk factors for opioid use disorder | 9 (Yes = 1, No = 0) | 0–9 |
| **COMM-16** (modified Current Opioid Misuse Measure) | Possible misuse of prescribed opioids in the last 30 days | 16 (0–4 each) | 0–64 |

The app:

1. **Reads the scanned forms** on your computer. It finds the ticked boxes and
   circled numbers on each page. It does not use any internet or cloud
   service.
2. **Adds up each questionnaire** with the published scoring rules. Blank
   answers are never counted as zero. They are flagged so someone checks the
   scan.
3. **Lets you check and correct** each answer next to a picture of the original
   mark.
4. **Combines the results** with the clinician's review of drug tests and the
   prescription database (UDS/PDMP), refill behaviour and the reason for the
   visit. It then gives an overall opioid risk level (**Low**, **Moderate** or
   **High**) and how often to repeat the questionnaires (12, 6 or 3 months).
5. **Writes a report** that follows the clinic's original template. The report
   includes clinical flags, a suicide-risk statement, treatment guidance,
   billing codes and a time attestation. Each patient's latest result is saved
   in the `patient_results` folder.

The app also has an **Insights** tab with charts and trends from your saved
assessments, and an **About** tab that explains how it works.

---

## 2. What you need

- A Windows 10/11 or macOS computer. Linux also works.
- **Python 3.10 or later**, unless you use the **portable Windows version**
  ([3.0](#30-no-python-the-portable-windows-version)), which includes Python.
  Anaconda is fine.
- **Git** (optional). You can download the app as a ZIP file instead.
- About 500 MB of free disk space for Python packages.
- A modern web browser: Chrome, Edge, Firefox or Safari.
- Scanned patient forms as PDF files: the six-page packet, one PDF per patient
  per visit.

You do **not** need an internet connection to use the app once it is
installed. You only need one for the installation step.

---

## 3. Installing the app (first time only)

### 3.0 No Python? The portable Windows version

If you received **Generator-portable.zip**, you do not need to install
anything:

1. Right-click the zip, choose **Extract All**, and extract it to a folder you
   can write to, such as **Documents** or **Desktop** (not Program Files).
2. Open the extracted **Generator** folder and double-click
   **Start Generator.bat**.
3. A black window opens and, after a few seconds, your browser opens at
   **http://localhost:8765**. Keep the black window open while you use the app;
   close it to stop the app.

If Windows shows *Windows protected your PC*, click **More info**, then **Run
anyway**. Your forms go in `Generator\app\patient_forms` and results are
saved in `Generator\app\patient_results`. To upgrade, extract the new zip and
copy your `patient_forms` and `patient_results` folders into its `app` folder.
Skip to [section 5](#5-a-tour-of-the-screen).

**Making the portable zip (for whoever shares the app):** on a Windows
computer with internet and Python 3.12, double-click
`portable\Build portable.bat` (set `GENERATOR_BUILD_PYTHON` to the Python 3.12
executable if `python` is a different version). It creates
`dist\Generator-portable.zip`, containing Python, the app, the sample forms and
the TEST01–TEST08 test patients. Your own patient forms and saved results are
never included.

### 3.1 Install Python

1. Go to <https://www.python.org/downloads/> and download the latest Python 3
   installer.
2. Run the installer. **On the first screen, tick "Add Python to PATH"**, then
   select **Install Now**.
3. To check that it worked, open **PowerShell** (Windows: press the Start
   button, type *PowerShell* and press Enter) or **Terminal** (Mac), then type:

   ```powershell
   python --version
   ```

   You should see something like `Python 3.12.4`. If Windows says `python` is
   not recognised, try `py --version`. If that works, type `py` instead of
   `python` in every command in this manual.

### 3.2 Get the app

**Option A: with Git (recommended, because updates are easier)**

1. Install Git from <https://git-scm.com/downloads>. The default options are
   fine.
2. In PowerShell, go to the folder where you want the app, for example your
   Documents folder, and download it:

   ```powershell
   cd $HOME\Documents
   git clone https://github.com/ILstabel/Generator.git
   cd Generator
   ```

**Option B: without Git**

1. Open <https://github.com/ILstabel/Generator> in your browser.
2. Select the green **Code** button, then **Download ZIP**.
3. Unzip the file, for example to `Documents\Generator`. The unzipped folder
   may be called `Generator-main`.
4. In PowerShell, go into that folder:

   ```powershell
   cd $HOME\Documents\Generator-main
   ```

   Tip: in File Explorer you can also open the folder, click the address bar,
   type `powershell` and press Enter. PowerShell then opens already inside the
   folder.

### 3.3 Install the app's packages

From inside the app folder, run:

```powershell
python -m pip install -r requirements.txt
```

This downloads Streamlit, OpenCV, pandas and the other building blocks the app
needs. It can take a few minutes. Warnings in yellow are usually harmless. Red
**ERROR** lines mean something failed; see [Troubleshooting](#20-troubleshooting).

**Anaconda users:** use Anaconda's Python for both installing and running:

```powershell
& "$env:USERPROFILE\anaconda3\python.exe" -m pip install -r requirements.txt "numpy<2"
```

---

## 4. Starting, stopping and updating the app

### Start

1. Open PowerShell inside the app folder (see 3.2).
2. Run:

   ```powershell
   python -m streamlit run app.py
   ```

   Anaconda users: `& "$env:USERPROFILE\anaconda3\python.exe" -m streamlit run app.py`

3. Your browser opens at **http://localhost:8501**. If it does not open by
   itself, copy that address into your browser.
4. **Leave the PowerShell window open** while you use the app. Closing it
   stops the app.

The first start may ask for an e-mail address. Just press **Enter** to skip.

### Stop

Click the PowerShell window and press **Ctrl + C**. You can then close the
browser tab.

### Restart (after changes or updates)

The app does not pick up new program files or colour-theme changes until it is
restarted. Press **Ctrl + C**, then run the start command again.

Adding or changing PDF forms does **not** need a restart. Just select the
folder or patient again.

### Update to the latest version

If you installed with Git:

```powershell
git pull
python -m pip install -r requirements.txt
```

Then restart the app. Your `patient_forms` and `patient_results` folders are
not touched by updates.

If you installed from a ZIP, download the new ZIP and copy your
`patient_forms` and `patient_results` folders into the new folder.

---

## 5. A tour of the screen

```
┌───────────────┬──────────────────────────────────────────────────────────┐
│ SIDEBAR       │  Chronic Pain / Opioid Risk Generator                      │
│ (green)       │  [ Assessment ]  [ Insights ]  [ About ]   ← tabs          │
│               │                                                            │
│ Select        │  All Assessments Scores        (results table)             │
│ Assessment    │  Individual Total Scores       (one patient's details)     │
│               │  Saved patient records ▸                                   │
│ Calculate     │  Reset assessment                                          │
│ ○ All Assess. │  Entry method:  ● Paste text   ○ Manual entry              │
│ ○ Individual  │  Review and correct scores                                 │
│               │  Clinical Context · UDS / PDMP · Refill Behavior           │
│ Folder ▾      │  Documentation confirmations                               │
│               │  [Generate reviewed report]                                │
│ [Calculate    │  Risk banner, Score Summary, Clinical Flags, report        │
│  and save     │                                                            │
│  scores]      │                                                            │
└───────────────┴──────────────────────────────────────────────────────────┘
```

- **Sidebar (left, green):** choose which forms to score. Below that,
  **Risk Thresholds** lets you pick a preset (or Custom) for the thresholds that
  make each test Moderate or High risk (see 18.3). You can hide the sidebar
  with the **«** arrow at its top and bring it back with **»**.
- **Assessment tab:** everything to do with scoring patients and writing
  reports.
- **Insights tab:** charts, a follow-up list and patient trends built from
  your saved assessments.
- **About tab:** a plain-language summary, the point rules and the
  questionnaire references.
- **Menu (⋮, top right):** Streamlit's own menu. **Rerun** refreshes the page,
  and **Settings** lets you change light or dark mode. If the colours look
  wrong, choose **Settings → Theme → Use system setting** or **Custom Theme**.
  The clinic theme is set in the app's configuration file.

Tables stretch to the full page width and show every row. You can sort a table
by clicking a column header. Hovering over a table shows a small toolbar with
**search** and **full-screen** buttons, plus a **download as CSV** button.

---

## 6. Preparing patient forms

### 6.1 Folder layout

Scanned forms live in the `patient_forms` folder inside the app folder. Make
one sub-folder per visit day, named **year_month_day**:

```
Generator\
└── patient_forms\
    ├── 2026_10_14\
    │   ├── 10001.pdf
    │   └── 10003.pdf
    └── 2026_10_15\
        ├── 10002.pdf
        └── 10003.pdf
```

Rules:

- The folder name **is** the visit date the app uses. For example,
  `2026_10_14` means 14 October 2026. The app never guesses dates from the
  handwriting.
- Use four digits for the year and two digits each for the month and day,
  separated by underscores: `2026_03_05`, not `2026_3_5`.
- Put the PDFs **directly** in the date folder, not in further sub-folders.

### 6.2 File names = patient codes

Name each PDF with the patient's code, for example `10001.pdf`. Use letters,
numbers, `-` or `_` only. Do not use names or other identifying details.

- The code is how the app links visits and saved records for the same
  patient.
- The same patient can appear in several date folders (for example `10003`
  above). Each visit is scored separately; visits are never merged.
- A file without a usable code can still be scored and viewed, but its
  results cannot be saved to a patient record.

### 6.3 Scanning tips

The app finds marks by looking at the page, so scan quality matters.

- Scan all **six pages in the original order** into one PDF.
- Use **300 dpi**, black-and-white or greyscale. Avoid "photo" mode with heavy
  compression.
- Keep pages **straight**. The app corrects small tilts but not upside-down or
  sideways pages.
- Ask patients to use a **dark pen** and to make one clear mark per question.
  Light pencil, crossed-out answers and marks between two boxes may be
  flagged as unclear (*ambiguous*) or left blank.
- Do not scan with sticky notes, staples or folded corners covering the
  answer areas.

The app comes with four **synthetic test forms** (patients `10001`, `10002`
and `10003`) so you can practise. They are not real patients.

---

## 7. Scoring a whole visit day (All Assessments)

Use this mode at the end of a clinic day to score every form in one go.

1. In the sidebar under **Calculate**, choose **All Assessments**.
2. In **Folder**, choose the visit day. The newest day is listed first.
3. Select **Calculate and save scores**. A spinner shows *"Inspecting local
   scans; no patient forms are uploaded..."*. Each form takes a few seconds.
4. The **All Assessments Scores** table appears. It has one row per PDF.

Every form is saved automatically as a **draft** record (see
[section 14](#14-saved-patient-records)). Drafts are clearly marked as not
verified.

### 7.1 Reading the All Assessments Scores table

| Column | Meaning |
|---|---|
| **Patient** | Patient code from the file name. `MISSING CODE` means the file name is not a valid code. |
| **Visit date** | The date folder the PDF came from. |
| **Overall risk** | **Low**, **Moderate** or **High**, or **Insufficient information** if something needed for the risk level is missing. At this stage it is based on the questionnaires only (see note below). |
| **PHQ-9** | Total out of 27 and the depression band, for example `8 / 27 - Mild`. Shows `URGENT: item 9 positive` if question 9 is above 0. |
| **Item 9** | Answer to PHQ-9 question 9 (0–3). Anything above 0 needs same-day clinician follow-up. |
| **PEG** | Average pain score out of 10. |
| **PDI** | Disability total out of 70 and its band, for example `42 / 70 - Severe disability`. |
| **ORT-OUD** | Opioid risk-factor total out of 9 and the risk band. |
| **COMM-16** | Medication-misuse total out of 64. |
| **Responses** | **Verified** once someone has ticked the response check for that form in Manual inspection. Otherwise **Not verified**. |
| **Saved record** | Status of the patient's saved record: **Draft (not verified)**, **Responses verified** or **Final report**. |

**An asterisk `*` after a score** (for example `35 / 64*`) means the total is
**provisional**. Some answers were blank, so the app added up only the answered
questions and flagged the result for review. A blank is never counted as 0.

**Note on overall risk:** in this table the drug-test and prescription
database review (UDS/PDMP), refill behaviour and clinical context have not been
entered yet. They count as 0 points and are listed as pending. The full risk
level is calculated in the assessment form ([section 10](#10-completing-the-assessment-form)).

### 7.2 Individual Total Scores

Below the table, under **Individual Total Scores**, choose a patient in
**Patient code**. You will see:

- A **Measure / Calculated result** table with the full explanation for each
  questionnaire. For example: *"Prorated: raw sum 7 x 9 / 8 answered =
  7.8750; rounded to 8. Missing responses are not assumed to be zero."*
- A **red alert** if PHQ-9 question 9 is positive, or a **yellow warning** if
  question 9 could not be read. An unread answer must never be treated as
  "no".

Choosing a patient here also **pre-fills the assessment form** further down the
page with that patient's scores (see [section 10](#10-completing-the-assessment-form)).

To check the actual marks on the scans, switch to **Individual Assessments**
(next section).

---

## 8. Scoring one patient (Individual Assessments)

Use this mode to look at one patient in detail, check the scan, or prepare a
final report.

1. In the sidebar under **Calculate**, choose **Individual Assessments**.
2. In **Patient / record score**, type or choose the patient code, for example
   `10003`. You can start typing to filter the list.
3. The sidebar shows **Visits found**, for example `2026_10_15, 2026_10_14`.
   Every visit for that patient is scored and shown separately.
4. Optionally turn on **Manual / visual inspection** to see the scans (see
   [section 9](#9-checking-and-correcting-answers-manual--visual-inspection)).
5. Select **Calculate and save scores**.

The results table is titled **Individual Assessment Scores** and has the same
columns as in [7.1](#71-reading-the-all-assessments-scores-table), with one row
per visit. Only the **newest** visit is saved as the patient's score record.

When a patient has more than one visit, a **Visit** box appears under
**Individual Total Scores**. It starts on the latest visit, marked
*(latest)*, and controls the score details and the scores pre-filled into the
assessment form. Choose an older visit to look at it; the **Saved patient
records** box then notes that the saved record is the latest visit.

If you change the patient, folder or mode, the old results disappear. Select
**Calculate and save scores** again to refresh them.

---

## 9. Checking and correcting answers (Manual / visual inspection)

The app reads marks automatically, but **automatic reading can be wrong**. A
stray pen mark, a crossed-out answer or a poor scan can fool it. Before a
report is relied on, someone should check the answers against the scan.

1. Choose **Individual Assessments**, choose the patient and turn on
   **Manual / visual inspection**.
2. Select **Calculate and save scores**.
3. Under **Individual Manual Inspection**, choose the visit in **Patient
   code**. Each visit opens in a box titled, for example, *Patient 10003:
   2026_10_14 / 10003.pdf*.
4. **Original page preview:** choose a page number (1–6) to see the whole
   scanned page. Use this to confirm the right form and page order.
5. Below the preview, each questionnaire (**PHQ-9**, **PEG**, **PDI**,
   **ORT-OUD**, **COMM-16**) lists every question. Each question has:
   - **on the left**, a drop-down with the value the app detected;
   - **on the right**, a cropped picture of that question's answer area from
     the scan, with a note underneath. For example, *AMBIGUOUS* means two
     marks were close, and *blank* means no mark was found.
6. Compare every picture with its value. If one is wrong, pick the correct
   value from the drop-down:
   - For PHQ-9 choose 0–3, for PEG and PDI 0–10, and for COMM 0–4. For ORT-OUD
     choose **Yes (1)** or **No (0)**.
   - Choose **Missing / unresolved** if the patient truly did not answer or
     the mark cannot be read. Do **not** choose 0 for a blank.
7. The **Measure / Calculated result** table under the questions updates
   immediately with your corrections.
8. When every question has been checked, tick **"I checked every response
   crop and corrected detection errors; unresolved values are genuinely
   missing."**
9. Then either:
   - **Save reviewed results to patient record 10003** saves the corrected
     answers with the status **Responses verified**; or
   - **Load reviewed responses into assessment** copies the corrected scores
     into the assessment form below, so you can complete the full report
     ([section 10](#10-completing-the-assessment-form)).

Both buttons stay greyed out until the check box is ticked. **Changing any
answer after ticking clears the tick**, so the confirmation always matches the
final values.

Your corrections are kept while you work. If you turn **Manual / visual
inspection** off, the summary uses your corrected values.

---

## 10. Completing the assessment form

The assessment form is in the lower half of the **Assessment** tab. It
combines the questionnaire scores with information only the clinician has.

### 10.1 How scores get into the form

There are three ways:

1. **Automatically.** When results are shown, the selected patient's newest
   visit pre-fills the form. A yellow banner says *"Scores auto-filled from
   optical detection of the scanned form; responses are NOT verified."* Check
   the answers in Manual inspection before relying on them.
2. **After checking.** **Load reviewed responses into assessment** (section 9)
   fills the form with verified answers. A blue banner names the source form,
   for example *Assessment imported from: 2026_10_14 / 10003.pdf*.
3. **By hand.** Paste text or type the scores ([section 13](#13-entering-scores-without-a-scanned-form)).

Importing a form clears any previous patient's context, diagnoses and
confirmations, so information never carries over from one patient to the next.

### 10.2 Review and correct scores

| Field | What to do |
|---|---|
| **Opioid risk instrument** | **ORT-OUD** for the scanned packet. Choose **Original ORT** only if the older ORT was used. |
| **COMM form maximum** | **Modified form: 16 items / 64** for the scanned packet. Choose **Standard COMM: 17 items / 68** or **Modified form: 7 items / 28** if a different form was used. Always check this. |
| **PEG average**, **PDI**, **PHQ-9**, **PHQ-9 item #9**, **COMM**, **ORT-OUD total / 9** | Pre-filled scores. Correct any value if needed. **Clear a box to mark it missing; never type 0 for "unknown".** |
| **Prior PEG score / 10 (optional)** | The PEG score from the previous visit. If given, the report states whether pain has improved (a drop of at least 30% is meaningful). |
| **Baseline PDI score / 70 (optional)** | The PDI score from the first (baseline) visit. Used to judge progress. |

Grey notes under the fields explain how each total was calculated, for
example how a missing PHQ-9 answer was handled. Red messages mean a value is
impossible, such as a PHQ-9 total above 27, and must be fixed before a report
can be made.

Safety messages:

- **Red "Safety alert: positive PHQ-9 item #9"** — immediate clinician
  suicide-risk assessment and safety protocol are required.
- **Yellow "PHQ-9 item #9 not documented"** — the answer is unknown. Do not
  assume it was "no".
- **Green "PHQ-9 item #9 = 0: no suicidal ideation endorsed."** — the patient
  answered 0 ("not at all"). This is a complete, normal answer, not missing
  information or a problem. Anything above 0 is a positive screen and shows the
  red safety alert instead.

### 10.3 Clinical context, UDS/PDMP and refill behaviour

These three boxes add the clinician's knowledge to the risk level.

**Clinical Context / Trigger (select all that apply)** — why the patient is
being assessed now. The default is *Routine interval chronic opioid
monitoring*. Options and their risk points:

| Option | Points |
|---|---|
| Routine interval chronic opioid monitoring | 0 |
| High pain interference with ongoing opioid therapy | 0 |
| Post-procedure / post-intervention reassessment | 0 |
| Treatment agreement / opioid safety reassessment | 0 |
| Worsening pain/function trajectory | 1 |
| Mood deterioration affecting pain/opioid risk | 1 |
| Documented history of opioid-related aberrant medication-use behavior | 1 |
| Opioid escalation request | 2 |
| Elevated opioid misuse-risk screen | 2 |
| Discordant UDS/PDMP or refill concern | 2 |

The clinical-context total is **capped at 3 points**.

**UDS / PDMP** — the result of the urine drug screen and the prescription drug
monitoring program check:

| Option | Points |
|---|---|
| Not reviewed / not available at time of assessment | 0, listed as *pending review* |
| UDS pending; PDMP review without concerning findings | 0, listed as *pending review* |
| Consistent with prescribed medication regimen and no concerning PDMP findings | 0 |
| UDS consistent; PDMP review without concerning findings | 0 |
| UDS/PDMP findings require provider review and closer monitoring | 2 |
| Discordant UDS and/or concerning PDMP findings noted | 3 |

**Refill Behavior:**

| Option | Points |
|---|---|
| Not reviewed / refill behavior not documented | 0, listed as *pending review* |
| Stable refill behavior without early refill pattern | 0 |
| No concerning refill behavior reported at this interval | 0 |
| Intermittent refill timing concerns requiring monitoring | 1 |
| Refill behavior requires provider review and closer monitoring | 1 |
| Early refill request or dose-escalation request noted | 2 |
| Lost/stolen medication report or medication-management concern noted | 2 |

### 10.4 Completeness message

Below these boxes, one of three messages appears:

- **Yellow "Assessment incomplete. Missing: …"** — something required is
  missing, such as a PEG, PDI, COMM or ORT score, or a blank COMM answer. The
  report will say *Insufficient information* and give **no** risk level or
  repeat interval. Fix the listed items first.
- **Blue "Overall risk calculated. Pending review: …"** — a risk level was
  calculated, but some items still need review, such as UDS/PDMP not yet
  reviewed or one PHQ-9 answer prorated. These add 0 points until they are
  updated.
- **Green "All app-required assessment inputs are present."** — everything the
  app needs is entered. This does not by itself mean the clinical assessment is
  complete.

---

## 11. Documentation confirmations

These fields go into the billing and attestation parts of the report.

| Field | Notes |
|---|---|
| **Clinician-established diagnoses (optional; never inferred from scores)** | Choose *F11.20 - Opioid dependence, uncomplicated* and/or *G89.4 - Chronic pain syndrome* **only** if the clinician has made that diagnosis. The app never picks a diagnosis by itself. |
| **Actual QHP evaluation time / minutes** | The clinician's real time spent. 0 means not documented. The report splits the time as in the original template: review/scoring 20%, interpretation 35%, decision-making 25%, documentation 15%, and the remainder for feedback/care coordination. |
| **I confirm assessment results were reviewed with the patient.** | Tick only if feedback was given. |
| **I attest I personally spent the actual minutes entered…** | Tick only if the minutes are correct. Requires minutes above 0. |
| **I am the reviewing clinician and have verified the assessment and generated documentation.** | Needed to save a **final** report. Without it, the report is marked as a draft. |
| **I verified/corrected every review field, resolved any parser errors, and verified the COMM form maximum.** | Required before the report can be generated. |

**Changing a score or context clears these confirmations**, and changing the
minutes clears the time attestation. This is deliberate: the ticks must always
refer to the final values.

---

## 12. Generating, downloading and saving the report

1. Select **Generate reviewed report**. The button is greyed out until the
   score-verification box is ticked and there are no red errors.
2. A coloured **risk banner** appears at the top of the report:
   - **green** — Low risk (repeat every 12 months);
   - **amber** — Moderate risk (repeat every 6 months);
   - **red** — High risk (repeat every 3 months);
   - **grey** — Insufficient information (no level or interval).
3. Below the banner:
   - **Score Summary** — each measure with its score and interpretation.
   - **Clinical Flags** — ☑ means the flag applies, ☐ means it does not, and
     ❔ *Not assessed* means the information is missing. Flags include
     *PEG ≥ 7 — severe pain impact*, *PDI ≥ 41 — severe disability*, *PHQ-9
     item #9 > 0 — suicide risk assessment indicated*, *COMM >= 9* and the
     ORT-OUD risk.
   - The template sections: **Interval Clinical Impression**, **Integrated
     Opioid Risk Interpretation**, **Suicide Risk Assessment**, **Opioid
     Treatment Guidance**, **Feedback**, **Billing codes** and **QHP Time &
     Attestation**.
   - **Readable Report** — the whole report as plain text, ready to copy into
     the medical record.
4. Select **Download readable report (.txt)** to save the text file
   (`opioid_risk_report.txt`) to your Downloads folder.
5. If the scores came from a scanned form named with a patient code, select
   **Save final report to patient record 10001 (2026_10_14)**. This button
   needs the reviewing-clinician box ticked. It stores the report with the
   status **Final report**.

If you change anything after generating, the report disappears until you
select **Generate reviewed report** again. This prevents an out-of-date report
from being copied.

When you are finished with a patient, select **Reset assessment** to clear the
form before the next one.

---

## 13. Entering scores without a scanned form

You can use the report generator with scores from another source, such as a
paper total or another system.

1. Select **Reset assessment**.
2. Under **Entry method** choose:
   - **Paste text** — paste labelled scores into **Paste scores or copied text
     from a filled form**, then select **Complete assessment**. The values
     appear in **Review and correct scores** for checking.
   - **Manual entry** — type each score straight into the review fields.
3. Continue from [section 10.2](#102-review-and-correct-scores).

Examples of text the app understands (one per line):

```text
PEG: 8 + 10 + 6 / 3 = 8
PDI Total: 40 / 70
PHQ-9 Score: 19 / 27
Question 9. Answer: 0
COMM-16 Total: 0 / 64
ORT: 4 / Moderate Risk
```

- PEG can also be written `PEG Average: 8 / 10`.
- If no COMM maximum is written, 68 is assumed **with a warning**, so you
  should always check **COMM form maximum**.
- Repeated or conflicting labels and impossible values are reported as
  yellow warnings. They are never guessed silently.

Reports made from pasted or typed scores can be downloaded, but they are not
linked to a scanned form, so the **Save final report** button is not shown.

---

## 14. Saved patient records

### 14.1 What is saved and where

Each patient has **one** saved record, which always holds the latest result.
Two files are saved in the `patient_results` folder:

- `10001_score.txt` — the readable report or score summary;
- `10001_score.json` — the same data in a structured form for other programs;
- `10001_history.json` — the totals of every saved visit, used for the patient
  trend.

Each new save **replaces** the previous one for that patient, including over a
final report. Keep downloaded reports or your medical record as the permanent
copy.

### 14.2 Record statuses

| Status (table label) | Created by | Meaning |
|---|---|---|
| **Draft (not verified)** | **Calculate and save scores** | Automatic reading only; nobody has checked the answers. |
| **Responses verified** | **Save reviewed results to patient record** | Answers checked against the scan; clinician report still pending. |
| **Final report** | **Save final report to patient record** | Full report with reviewing-clinician confirmation. |

### 14.3 Viewing saved records

1. Open **Saved patient records (N patient codes)** in the Assessment tab.
2. Choose a **Patient code**. It follows the patient you selected under
   **Individual Total Scores**, so the saved report matches the scores you are
   looking at; you can still choose any other code.
3. You will see:
   - the visit folder, status, save time (in UTC), integrated risk and source
     PDF;
   - the score summary;
   - the full saved report.

   Anything other than a final report shows a warning that it is not a final
   clinical document.
4. Select **Download saved report (.txt)** to save a copy.

---

## 15. The Insights tab

The Insights tab summarises **your clinic's saved assessments** from the
`patient_results` folder: one row per patient code, using that patient's
latest saved visit. Overall risk is shown as it was saved. Nothing leaves your
computer. If no records are saved yet, the tab says so; use **Calculate and
save scores** in the Assessment tab first.

The made-up patients **TEST01**–**TEST08** let you try the tab before real
records exist (see [15.5](#155-test-patients)).

### 15.1 Filters

Open **Filter saved assessments**. **Visit date**, **Record status** and
**Overall risk** show **All** by default. Click a box to choose one or more
values; remove them all to go back to **All**. With only a few patients
selected, a note warns that percentages will change a lot as more records are
saved. If records were saved with different risk-threshold presets, a warning
says their risk levels are not directly comparable.

### 15.2 Headline numbers and follow-up list

**Patients**, **High risk**, **Item 9 positive**, **Insufficient information**
and **Final reports** count the selected patients.

The **Follow-up list** shows the patients who need action, most urgent first:
a positive PHQ-9 question 9, missing answers, unverified automatic drafts, and
a repeat questionnaire that is overdue (12, 6 or 3 months after the last visit,
depending on risk).

### 15.3 Charts

| Chart | How to read it |
|---|---|
| **Score heatmap** | One row per patient (highest risk first), one column per measure. Darker colour = higher score for that scale; the number is the raw score. Outlined cells meet a clinical flag (PHQ-9 ≥ 15, item 9 > 0, PEG ≥ 7, PDI ≥ 41, ORT-OUD ≥ 3, COMM ≥ 9). Grey = not scored. |
| **Overall risk** | Donut: how many patients are Low, Moderate, High or Insufficient information. |
| **PHQ-9 depression severity** | Bars: patients in each PHQ-9 severity band. |
| **Clinical flags** | Lollipops: the share of patients with each flag, among patients with that measure scored. |
| **Pain interference vs disability** | One dot per patient: PEG average against PDI total, coloured by risk. |
| **Saved assessments by visit date** | Stacked bars: patients per visit date, split by risk. |
| **Score distribution** | Pick a measure to see every patient's score as a tick, coloured by risk. |

Hover over any chart for exact numbers. Charts have a **⋯** menu to save them
as an image. **All saved assessments** lists the rows behind the charts and can
be downloaded as a CSV file.

### 15.4 Patient trend

Choose a patient under **Patient trend** to see their saved visits over time:
score lines with the flag threshold marked, overall risk per visit, and
**Change since first visit** for PEG and PDI (with the improvement criteria).
The same view appears in the Assessment tab as **Patient trend: <code> (saved
visits)** when you select a patient. Trends use each visit's totals as they
were saved, from the patient's `<code>_history.json` file.

### 15.5 Test patients

`make_test_records.py` creates eight made-up patients, **TEST01**–**TEST08**,
with one to four visits each (improving, worsening, overdue, item 9 positive,
blank answers, and so on). Their reports say *SYNTHETIC TEST DATA*. The
portable version already includes them. To create or remove them yourself:

```powershell
python make_test_records.py           # create TEST01-TEST08
python make_test_records.py --remove  # delete every TEST* record
```

---

## 16. The About tab

The About tab is a reference page you can show to colleagues:

- **What this app does** — a plain-language summary.
- A **support-tool notice** about clinician verification.
- **How the app calculates points** — the risk-point table, the risk levels and
  the repeat intervals.
- **Questionnaire scoring rules and references** — the rules for each
  questionnaire, with links to the published sources.

---

## 17. Worked examples with the sample forms

These examples use the included synthetic forms. Your screen should show the
same results.

### Example 1 — a complete form (patient 10001, 2026_10_14)

1. Choose **All Assessments**, folder **2026_10_14**, then select **Calculate
   and save scores**.
2. The row for **10001** shows:

   | PHQ-9 | Item 9 | PEG | PDI | ORT-OUD | COMM-16 | Overall risk |
   |---|---|---|---|---|---|---|
   | 8 / 27 - Mild | 0 | 7 / 10 | 42 / 70 - Severe disability | 5 / 9 - High risk | 23 / 64 | Moderate |

3. In **Individual Total Scores**, choose **10001**. The PHQ-9 line explains
   that question 2 was blank, so the total was **prorated**: 7 × 9 ÷ 8 answered
   = 7.875, rounded to **8**.
4. Why **Moderate**? COMM 23 is 18 or more, which gives **3 points**. ORT-OUD 5
   is between 4 and 7, which gives **1 point**. That makes **4 points**, which
   is Moderate (2–4), so the repeat interval is 6 months. UDS/PDMP and refills
   are still *pending review*.
5. Scroll down to the pre-filled assessment form. Suppose the clinician enters:
   - **UDS / PDMP:** *UDS/PDMP findings require provider review and closer
     monitoring* (+2);
   - **Refill Behavior:** *Intermittent refill timing concerns requiring
     monitoring* (+1);
   - **Clinical Context:** add *Opioid escalation request* (+2).

   The total becomes 3 + 1 + 2 + 1 + 2 = **9 points**, which is **High** (red
   banner, repeat every 3 months).
6. Tick the confirmations, select **Generate reviewed report**, check it, then
   download it and save the final report.

### Example 2 — a form that needs checking (patient 10003, 2026_10_14)

1. The row for **10003** shows:

   | PHQ-9 | Item 9 | PDI | COMM-16 | Overall risk |
   |---|---|---|---|---|
   | 14 / 27 - URGENT: item 9 positive | 1 | 31.5 / 70 - Moderate disability | 35 / 64* | Insufficient information |

2. **PHQ-9 question 9 = 1.** A red alert appears. This patient needs a
   same-day clinician suicide-risk assessment, whatever the other results
   are.
3. **PDI 31.5.** One domain was blank, so the average of the six answered
   domains (4.5) was used for it. This is called *mean-imputed* and is flagged
   in the details.
4. **COMM 35 / 64\*.** COMM questions 9 and 14 were blank, so the total is
   provisional and the overall risk is **Insufficient information**.
5. To resolve this, choose **Individual Assessments**, patient **10003**, and
   turn on **Manual / visual inspection**. Then select **Calculate and save
   scores**.
6. In the 2026_10_14 visit, look at COMM questions 9 and 14. If the scan
   really is blank, leave them as **Missing / unresolved**; the patient may
   need to complete them. Also look at COMM question 10, which is flagged
   *AMBIGUOUS*, and confirm the value.
7. Tick the check box and save or load the reviewed responses.

### Example 3 — one patient over two visits (patient 10003)

In **Individual Assessments**, the sidebar shows **Visits found: 2026_10_15,
2026_10_14**. Both visits appear as separate rows. Only the newest
(2026_10_15) is saved as the patient record.

---

## 18. How scores and risk are calculated

### 18.1 Questionnaires

| Questionnaire | Total | Blank answers | Bands |
|---|---|---|---|
| **PHQ-9** | Sum of 9 answers (0–27) | 1–2 blank: scaled up (sum × 9 ÷ answered, rounded). 3 or more blank: provisional total of answered items, flagged. | 0–4 minimal, 5–9 mild, 10–14 moderate, 15–19 moderately severe, 20–27 severe. **Question 9 above 0 is always an urgent flag.** |
| **PEG** | Average of 3 ratings (0–10) | All 3 needed for a full score | Under 4 low, 4–6 moderate, 7 or more high pain interference |
| **PDI** | Sum of 7 domains (0–70) | 1 blank: the average of the others is used. 2 or more blank: provisional, flagged. | 0–20 mild, 21–40 moderate, 41–70 severe disability |
| **ORT-OUD** | Count of "Yes" answers (0–9) | Flagged for review; blocks the overall risk level | 0–2 low risk, 3–9 high risk for opioid use disorder |
| **COMM-16** | Sum of 16 answers (0–64) | Provisional total of answered items, flagged; blocks the overall risk level | 9 or more is an elevated misuse-risk signal |

The exact bands and thresholds are listed in the **About** tab and in the
`scoring_config.json` file.

### 18.2 Overall risk points

| Input | Points |
|---|---|
| COMM (any form) | 9–17: 2; 18 or more: 3 |
| ORT / ORT-OUD | 4–7: 1; 8 or more: 3 |
| PHQ-9 total | 15–19: 1; 20 or more: 2 |
| PHQ-9 question 9 above 0 | 3, plus an urgent safety alert |
| UDS / PDMP | Requires review: 2; discordant: 3 |
| Refill behaviour | Intermittent or requires review: 1; early/escalation or lost/stolen: 2 |
| Clinical context | 1 or 2 per item (see 10.3), capped at 3 |
| PEG and PDI | Reported and flagged, but **no** risk points |

| Total points | Overall risk | Repeat the questionnaires |
|---|---|---|
| 0–1 | **Low** | every 12 months |
| 2–4 | **Moderate** | every 6 months |
| 5 or more | **High** | every 3 months |

If required information is missing, the result is **Insufficient
information** and no interval is given. Missing information is never treated
as a normal result.

This point system comes from the clinic's original template. It is
decision support, **not** a validated prediction model.

### 18.3 Risk-threshold presets (sidebar)

Below **Select Assessment**, the sidebar has a **Risk Thresholds** section.
It lets you choose which scores add points for each test, and how many total
points make the overall risk **Moderate** or **High**. Points per tier stay
the same (for example, COMM always adds 2 at its moderate threshold and 3 at its
high threshold); only the thresholds move. PHQ-9 question 9, UDS/PDMP, refill
behaviour and clinical context always use the rules in 18.2.

| Preset | COMM (2 / 3 pts) | ORT (1 / 3 pts) | PHQ-9 (1 / 2 pts) | Moderate / High overall |
|---|---|---|---|---|
| **Original template (default)** | 9 / 18 | 4 / 8 | 15 / 20 | 2 / 5 points |
| **Conservative (flags more patients)** | 9 / 14 | 3 / 6 | 10 / 15 | 2 / 4 points |
| **Lenient (flags fewer patients)** | 12 / 24 | 5 / 9 | 20 / 25 | 3 / 6 points |
| **Custom** | your choice | your choice | your choice | your choice |

How to use it:

1. Open **Preset** and pick one. The **Thresholds** box shows the values in use
   (greyed out for the built-in presets).
2. To set your own values, choose **Custom**. The boxes start from the preset
   you had selected and become editable. Each moderate threshold must be lower
   than its high threshold. If they are not, a red message appears and the
   original template values are used until you correct them.
3. If a report was already generated, it disappears when you change the
   preset. Click **Generate reviewed report** again.

The default preset gives exactly the results described in 18.2. When any
other preset is active:

- the sidebar shows a warning that the thresholds are a local choice, not
  validated;
- the report adds a **RISK THRESHOLDS** line under the repeat interval, and
  the Score Summary adds a **Risk Thresholds** row. Saved records therefore
  show which thresholds were used;
- the **All Assessments Scores** table, the **Individual Total Scores** and
  the **About** tab's point table all use the selected thresholds.

The choice lasts for your browser session only. Reloading the page or
restarting the app returns to the original template.

---

## 19. Privacy and data

- **Everything stays on your computer.** Forms are read locally. No PDF,
  score or report is sent to the internet or to any cloud service.
- The app only opens in your own browser (`localhost`). Other people on the
  network cannot see it unless someone changes the settings.
- **Use patient codes, not names**, for file names.
- `patient_forms` and `patient_results` hold health information. Keep them on
  an encrypted, access-controlled computer and follow your clinic's
  record-retention policy.
- If you use Git, new forms and all results are excluded from uploads
  automatically. Only the four synthetic sample forms are in the shared
  repository. **Never** e-mail or upload real patient files to share the app.

---

## 20. Troubleshooting

| Problem | What to do |
|---|---|
| `python` is not recognised | Reinstall Python with **Add Python to PATH** ticked, or use `py` instead of `python`. |
| `No module named streamlit` (or `cv2`, `fitz`, `altair`) | The packages are not installed for the Python you are using. Run `python -m pip install -r requirements.txt` with the **same** Python you use to start the app. `cv2` comes from `opencv-python-headless`. |
| NumPy errors with Anaconda | Use the Anaconda command in 3.3, which includes `"numpy<2"`. |
| Browser shows "This site can't be reached" | The app is not running. Start it again (section 4) and keep PowerShell open. |
| "Port 8501 is already in use" | The app is already running in another window. Use that window, or stop it with Ctrl + C. To run a second copy, add `--server.port 8502`. |
| Sidebar says *"Add PDFs to patient_forms\YYYY_MM_DD\ to enable folder selection."* | No date folders were found. Check the folder name format (`2026_10_14`) and that it is inside `patient_forms`. |
| *"No PDFs named with a patient code … were found."* | Rename the PDFs to patient codes, e.g. `10001.pdf`. |
| A patient shows **MISSING CODE** | The file name contains spaces or symbols. Rename it with letters, numbers, `-` or `_` only. |
| Many answers are blank or wrong | The scan is probably poor: crooked, light, low resolution or out of order. Rescan at 300 dpi with pages in order, or correct the answers in Manual inspection. |
| Results disappeared | You changed the folder, patient or mode. Select **Calculate and save scores** again. |
| **Generate reviewed report** is greyed out | Tick the score-verification box, fix any red errors, and if the time attestation is ticked, enter minutes above 0. |
| **Save final report** is greyed out | Tick *"I am the reviewing clinician…"*. |
| **Save final report** button is missing | The scores were pasted or typed, not loaded from a scanned form with a patient code. |
| Report disappeared after a change | Expected. Select **Generate reviewed report** again. |
| Colours or layout look old after an update | Restart the app (Ctrl + C, then start again) and refresh the browser. If colours still look wrong, open **⋮ → Settings** and choose the custom theme. |
| Insights tab says "No saved patient records yet" | Save at least one assessment with **Calculate and save scores**, or create the test patients with `python make_test_records.py`. |
| Portable version: *Windows protected your PC* | Click **More info**, then **Run anyway**. This appears because the .bat file is not signed. |
| Portable version: the browser does not open | Wait a few seconds and open **http://localhost:8765** yourself. If the black window closed straight away, make sure the zip was fully extracted (not opened inside the zip) to a folder you can write to. |
| Portable version: firewall prompt | The app only listens on this computer (localhost), so you can click **Cancel**. |
| An error box with red text (a "Traceback") | Copy the text and restart the app. If it happens again, send the text, **without any patient information**, to the person who maintains the app. |

---

## 21. Frequently asked questions

**Does the app replace the clinician's judgement?**
No. It scores and drafts. A clinician must verify everything before use.

**Why is a blank answer not counted as zero?**
A blank means *unknown*. Counting it as 0 would make the patient look lower
risk than they may be. This is especially important for question 9.

**Why doesn't the app use online text recognition (OCR)?**
The forms are mostly ticks and circles, not text. Sending patient forms to an
online service would also raise privacy and legal (HIPAA) concerns, add
costs, and still need human checking. Local mark detection keeps everything
on your computer.

**Can I re-score a form after correcting the scan?**
Yes. Replace the PDF in its date folder and select **Calculate and save
scores** again. The saved record is replaced.

**I saved a final report and then recalculated — what happened?**
The newest save always replaces the patient's record, so the final report
in `patient_results` was replaced by a draft. Keep downloaded final reports or
copy them into the medical record.

**Can two people use it at once?**
Each person should run their own copy on their own computer. The app is
designed for single-user local use.

**Can I change the colours?**
Yes. They are in `.streamlit\config.toml` (see the README). Restart the app
after editing.

---

## 22. Glossary

| Term | Meaning |
|---|---|
| **Ambiguous** | Two possible marks were found for one question; a person must decide. |
| **Band** | A named score range, such as *Mild* or *Severe disability*. |
| **COMM** | Current Opioid Misuse Measure: questions about recent medication-use behaviour. |
| **Draft** | An automatic result that nobody has checked yet. |
| **Mean-imputed** | A missing PDI domain is filled with the average of the answered domains. |
| **ORT-OUD** | Opioid Risk Tool for Opioid Use Disorder: a yes/no risk-factor checklist. |
| **PDI** | Pain Disability Index: how pain limits seven areas of life. |
| **PDMP** | Prescription Drug Monitoring Program: a state database of controlled-substance prescriptions. |
| **PEG** | Pain, Enjoyment of life, General activity: a 3-question pain scale. |
| **PHQ-9** | Patient Health Questionnaire-9: a depression screen. Question 9 asks about thoughts of self-harm. |
| **Prorated** | A missing PHQ-9 answer is accounted for by scaling up the answered items. |
| **Provisional** (`*`) | A total from the answered questions only, because some were blank; needs review. |
| **QHP** | Qualified Health Professional: the clinician whose time is attested. |
| **UDS** | Urine Drug Screen. |
| **Visit folder** | A `patient_forms` sub-folder named with the visit date, e.g. `2026_10_14`. |
