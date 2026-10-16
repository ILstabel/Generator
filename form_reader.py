"""Local, review-required optical marks for the six-page chronic-pain form."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from pypdf import PdfReader
from pypdf.errors import PdfReadError


FORMS_ROOT = Path(__file__).parent / "patient_forms"
WIDTH, HEIGHT = 1600, 2071
MAX_PDF_BYTES = 30 * 1024 * 1024


@dataclass
class Response:
    instrument: str
    item: int
    page: int
    value: float | None
    note: str
    crop: bytes


@dataclass
class FormInspection:
    folder: str
    filename: str
    responses: list[Response]
    page_previews: list[bytes] = field(default_factory=list)


class FormReadError(ValueError):
    pass


def date_folders(root: Path = FORMS_ROOT) -> list[str]:
    if not root.exists():
        return []
    folders = []
    for path in root.iterdir():
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            datetime.strptime(path.name, "%Y_%m_%d")
        except ValueError:
            continue
        if len(path.name) == 10:
            folders.append(path.name)
    return sorted(folders, reverse=True)


def folder_pdfs(folder: str, root: Path = FORMS_ROOT) -> list[Path]:
    if folder not in date_folders(root):
        raise FormReadError("Select an existing YYYY_MM_DD folder inside patient_forms.")
    directory = root / folder
    return sorted(
        (path for path in directory.iterdir() if path.is_file() and not path.is_symlink() and path.suffix.lower() == ".pdf"),
        key=lambda path: path.name.casefold(),
    )


# Reference geometry is anchored to each page's printed table header, not file names.
HEADERS = [
    (51, 593, 1572, 690), (169, 459, 1440, 530), (205, 495, 1409, 561),
    (99, 611, 1555, 680), (144, 495, 1462, 591), (146, 463, 1464, 560),
]
CHECKBOXES = {
    0: ([736, 960, 1210, 1467], [729, 795, 877, 961, 1027, 1127, 1261, 1405, 1540]),
    3: ([1142, 1295], [731, 820, 910, 999, 1087, 1177, 1266, 1355, 1444]),
    4: ([771, 918, 1077, 1232, 1385], [660, 787, 913, 1041, 1167, 1279, 1391, 1503]),
    5: ([772, 918, 1077, 1232, 1385], [629, 755, 866, 963, 1076, 1218, 1344, 1457]),
}
RATINGS = {
    1: ([944, 964, 983, 1003, 1022, 1042, 1061, 1081, 1100, 1120, 1144], [586, 707, 843]),
    2: ([694, 713, 732, 752, 771, 791, 810, 830, 849, 869, 894], [597, 665, 734, 816, 901, 968, 1053]),
}


def png_bytes(image: Image.Image) -> bytes:
    from io import BytesIO

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def aligned_page(image: Image.Image, page: int) -> np.ndarray:
    gray = np.array(image.convert("L").resize((WIDTH, HEIGHT)))
    left, top, right, bottom = HEADERS[page]
    ink = gray < 200
    rows = np.flatnonzero(ink.sum(axis=1) > 800)
    rows = rows[(rows > top - 45) & (rows < bottom + 45)]
    if len(rows) == 0:
        raise FormReadError(f"Page {page + 1}: expected table header not found; unsupported layout.")
    groups = np.split(rows, np.flatnonzero(np.diff(rows) > 2) + 1)
    band = max(groups, key=len)
    if not 45 <= len(band) <= 115:
        raise FormReadError(f"Page {page + 1}: table header does not match the supported form.")
    columns = np.flatnonzero(ink[int(np.median(band))])
    actual_left, actual_right = int(columns.min()), int(columns.max())
    if abs(actual_left - left) > 45 or abs(actual_right - right) > 45:
        raise FormReadError(f"Page {page + 1}: table columns do not match the supported form.")
    scale = (right - left) / (actual_right - actual_left)
    transform = np.array([[scale, 0, left - actual_left * scale], [0, scale, top - band.min() * scale]], dtype=np.float32)
    return cv2.warpAffine(gray, transform, (WIDTH, HEIGHT), borderValue=255)


def checkbox_responses(gray: np.ndarray, page: int) -> list[Response]:
    xs, ys = CHECKBOXES[page]
    ink = gray < 130
    counts = [
        [int(ink[y - 24:y + 24, x - 24:x + 24].sum()) for x in xs]
        for y in ys
    ]
    baseline = float(np.median([min(row) for row in counts]))
    if not 60 <= baseline <= 300:
        raise FormReadError(f"Page {page + 1}: printed response boxes could not be verified.")
    responses = []
    for index, (y, row) in enumerate(zip(ys, counts), 1):
        candidates = [choice for choice, count in enumerate(row) if count - baseline >= 60 and count >= baseline * 1.25]
        # Ink alone is a suggestion, never a verified patient response.
        value = float(candidates[0]) if len(candidates) == 1 else None
        note = "Detected mark; verify against scan." if value is not None else "No unique mark: blank, faint or unclear response."
        if len(candidates) > 1:
            inks = [row[choice] for choice in candidates]
            if inks.count(max(inks)) == 1:
                value = float(candidates[inks.index(max(inks))])
                note = f"AMBIGUOUS: {len(candidates)} boxes marked; chose the box with the most marked area. Verify against scan."
            else:
                note = "Multiple boxes marked equally: unclear response."
        if page == 3 and value is not None:
            value = 1.0 if value == 0 else 0.0
        instrument = "PHQ-9" if page == 0 else "ORT-OUD" if page == 3 else "COMM-16"
        item = index + (8 if page == 5 else 0)
        crop = Image.fromarray(gray).crop((xs[0] - 60, y - 44, xs[-1] + 60, y + 44))
        responses.append(Response(instrument, item, page + 1, value, note, png_bytes(crop)))
    return responses


def _shift(mask: np.ndarray, dx: int, dy: int) -> np.ndarray:
    return np.roll(np.roll(mask, dy, axis=0), dx, axis=1)


def majority_choice(extra: np.ndarray, printed: np.ndarray, xs: list[int], left: int) -> float | None:
    """Number whose printed area is most enclosed by the pen marks (each mark filled as its convex hull)."""
    joined = cv2.dilate(extra, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(joined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    enclosed = np.zeros_like(extra)
    for contour in contours:
        cv2.fillPoly(enclosed, [cv2.convexHull(contour)], 1)
    edges = [left] + [round((a + b) / 2) for a, b in zip(xs, xs[1:])] + [xs[-1] + 40]
    shares = []
    for start, stop in zip(edges, edges[1:]):
        cell = printed[:, start - left:stop - left] > 0
        area = int(cell.sum())
        shares.append(int((cell & (enclosed[:, start - left:stop - left] > 0)).sum()) / area if area else 0.0)
    best = max(shares)
    if best < 0.25 or shares.count(best) > 1:
        return None
    return float(shares.index(best))


def rating_responses(gray: np.ndarray, page: int) -> list[Response]:
    """Detect circled numerals by removing the printed 0-10 scale and locating the remaining pen ink.

    Every row prints the same numerals, so the pixel-wise median of the rows is a clean printed template.
    Pen circles usually touch the numerals, so they cannot be separated by connected components alone.
    """
    xs, ys = RATINGS[page]
    spacing = float(np.median(np.diff(xs)))
    left, half = xs[0] - 40, 34
    crops = [gray[y - half:y + half, left:xs[-1] + 40] for y in ys]
    inks = [(crop < 150).astype(np.uint8) for crop in crops]
    # A digit circled in most rows would enter the template and read as blank (missing), never as another value.
    template = np.median(np.stack(inks), axis=0) >= 0.5
    responses = []
    for index, (crop, ink) in enumerate(zip(crops, inks), 1):
        dx, dy = max(
            ((dx, dy) for dx in range(-4, 5) for dy in range(-4, 5)),
            key=lambda shift: int((_shift(template, *shift) & (ink > 0)).sum()),
        )
        printed = cv2.dilate(_shift(template, dx, dy).astype(np.uint8), np.ones((5, 5), np.uint8))
        extra = cv2.morphologyEx(((ink > 0) & (printed == 0)).astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        columns = np.nonzero(extra)[1] + left
        value = None
        if len(columns) < 25:
            note = "No pen mark detected: blank or very faint response."
        else:
            low, high = np.percentile(columns, 2), np.percentile(columns, 98)
            centre = (low + high) / 2
            choice = int(np.argmin([abs(centre - choice_x) for choice_x in xs]))
            between = int(np.searchsorted(xs, centre)) - 1
            position = (centre - xs[between]) / (xs[between + 1] - xs[between]) if 0 <= between < len(xs) - 1 else 0.0
            if high - low > 2.6 * spacing or 0.35 < position < 0.65:
                value = majority_choice(extra, _shift(template, dx, dy), xs, left)
                note = (
                    "No number is mostly enclosed by the pen marks: unclear response." if value is None else
                    f"AMBIGUOUS mark (spans or sits between numbers): chose {value:g}, the number with the largest "
                    "area inside the marks. Verify against scan."
                )
            else:
                value = float(choice)
                note = "Detected circle; verify against scan."
        responses.append(Response("PEG" if page == 1 else "PDI", index, page + 1, value, note, png_bytes(Image.fromarray(crop))))
    return responses


def inspect_form(path: Path, root: Path = FORMS_ROOT) -> FormInspection:
    resolved = path.resolve()
    if path.is_symlink() or resolved.parent.parent != root.resolve() or path not in folder_pdfs(path.parent.name, root):
        raise FormReadError("PDF must be inside a selected date folder within patient_forms.")
    if path.stat().st_size > MAX_PDF_BYTES:
        raise FormReadError("PDF exceeds the 30 MB local processing limit.")
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            raise FormReadError("Encrypted PDFs are not supported.")
        if len(reader.pages) != 6:
            raise FormReadError("Only the current six-page scanned battery is supported (PHQ-9, PEG, PDI, ORT-OUD, COMM-16).")
        responses = []
        previews = []
        for index, page in enumerate(reader.pages):
            images = list(page.images)
            if len(images) != 1:
                raise FormReadError(f"Page {index + 1}: expected one full-page scanned image.")
            image = images[0].image
            if image.width < 1000 or not 1.25 <= image.height / image.width <= 1.35 or page.rotation != 0:
                raise FormReadError(f"Page {index + 1}: scan size/orientation does not match the supported portrait layout.")
            gray = aligned_page(image, index)
            previews.append(png_bytes(image.convert("RGB").resize((1000, 1294))))
            responses.extend(checkbox_responses(gray, index) if index in CHECKBOXES else rating_responses(gray, index))
    except (PdfReadError, OSError, cv2.error) as error:
        raise FormReadError(f"Cannot inspect PDF: {error}") from error
    return FormInspection(path.parent.name, path.name, responses, previews)
