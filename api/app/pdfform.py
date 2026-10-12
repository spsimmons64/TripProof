###################################################################################################
# Drawing on an official PDF form.
#
# Four things were being done the same way in more than one place - find where a field sits on the
# blank, write inside it, tick a box, and put the audit stamp beside a signature. Three copies of
# one routine is how the I-9 and the W-4 came to disagree about which font a signature is drawn in,
# so there is one copy of each here and the forms hold the answers rather than the drawing.
#
# Nothing in this module knows what an I-9 is. It knows a blank has named boxes and that text goes
# inside them.
###################################################################################################
import io
from pathlib import Path

from fpdf import FPDF
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject
from sqlalchemy import text

LETTER = (612, 792)          # US Letter, in points, as the federal forms are laid out
INK = (15, 58, 67)
FAINT = (116, 133, 138)


def mdy(value) -> str:
    """A date as every box on these forms asks for it: mm/dd/yyyy.

    Our dates arrive as YYYY-MM-DD. The I-9 and the W-4 both label every date field
    "(mm/dd/yyyy)" and both were formatting it themselves - the W-4 with the separators and the
    I-9 without, so the same day printed as 10/07/2026 on one form and 10072026 on the other.
    """
    text = str(value or "")
    if len(text) < 10:
        return ""
    return f"{text[5:7]}/{text[8:10]}/{text[0:4]}"


def company(conn, accountid: str) -> dict:
    """The employer as a federal form asks for it: who they are, where they are, and their EIN.

    Both forms ask for this and they must not answer it differently - an I-9 and a W-4 filed for
    the same person on the same day, giving two different addresses for the same company, is a
    discrepancy somebody has to explain to an auditor.
    """
    held = conn.execute(text(
        "SELECT name, dba, address1, address2, city, state, zip, ein "
        "FROM accounts WHERE recordid = :a"), {"a": accountid}).mappings().first() or {}
    street = " ".join(x for x in [held.get("address1"), held.get("address2")] if x)
    where = ", ".join(x for x in [
        street, held.get("city"),
        " ".join(x for x in [held.get("state"), held.get("zip")] if x)] if x)
    return {"orgname": held.get("dba") or held.get("name") or "",
            "orgaddress": where, "ein": held.get("ein") or ""}


def boxes(page) -> dict[str, tuple[float, float, float, float]]:
    """Where each field sits, read from the form's own widget annotations.

    A widget that belongs to a field group carries no name of its own and points at the parent
    that does, which is how the radio groups on these forms are built."""
    out = {}
    for annot in page.get("/Annots") or []:
        obj = annot.get_object()
        name = obj.get("/T")
        if name is None and obj.get("/Parent") is not None:
            name = obj["/Parent"].get_object().get("/T")
        rect = obj.get("/Rect")
        if name and rect:
            out[str(name)] = tuple(float(v) for v in rect)
    return out


class Pen:
    """A transparent sheet the size of the page, drawn on in the blank's own coordinates.

    PDF measures up from the bottom of the page and FPDF measures down from the top, so every
    y here is converted once, in one place, rather than at each call site."""

    def __init__(self, where: dict, fontdir: Path | None = None, page=LETTER):
        self.where = where
        self.fontdir = fontdir
        self.page = page
        self.pdf = FPDF(unit="pt", format=page)
        self.pdf.add_page()
        self.pdf.set_text_color(*INK)
        self.pdf.set_font("Helvetica", size=10)
        self._faces = set()

    def face(self, fontfile: str) -> str:
        """Register a signature face once and give back the name to draw it under."""
        key = Path(fontfile).stem
        if key not in self._faces:
            self.pdf.add_font(key, "", str((self.fontdir or Path(".")) / fontfile))
            self._faces.add(key)
        return key

    def write(self, field: str, text: str, size: int = 10, font: str = "Helvetica",
              maxwidth: float | None = None):
        """Vertically centred in its box, shrunk to fit rather than allowed to run past the end.

        `maxwidth` holds it inside part of the box instead of all of it, for a box that has to
        carry something else beside it."""
        box = self.where.get(field)
        if not box or not text:
            return
        left, bottom, right, top = box
        height = top - bottom
        self.pdf.set_font(font, size=size)
        width = min(right - left - 4, maxwidth) if maxwidth else right - left - 4
        while self.pdf.get_string_width(text) > width and size > 5:
            size -= 1
            self.pdf.set_font(font, size=size)
        self.pdf.text(x=left + 2, y=self.page[1] - bottom - (height - size) / 2 - size * 0.22,
                      txt=text)

    def comb(self, field: str, text: str, cells: int, size: int = 10):
        """One character per cell, across a box the form has divided into a character grid.

        The I-9's Social Security number is nine ruled cells, not a line. Written as an ordinary
        run of text the digits bunch up at the left and sit across the rules, which reads as a
        number somebody has typed over the boxes rather than into them.
        """
        box = self.where.get(field)
        if not box or not text:
            return
        left, bottom, right, top = box
        step = (right - left) / cells
        self.pdf.set_font("Helvetica", size=size)
        y = self.page[1] - bottom - ((top - bottom) - size) / 2 - size * 0.22
        for n, ch in enumerate(str(text)[:cells]):
            self.pdf.text(x=left + n * step + (step - self.pdf.get_string_width(ch)) / 2,
                          y=y, txt=ch)

    def tick(self, field: str, size: int = 12, dx: float = 3.5, dy: float = 2):
        box = self.where.get(field)
        if not box:
            return
        left, bottom, right, top = box
        self.pdf.set_font("Helvetica", "B", size=min(size, top - bottom))
        self.pdf.text(x=left + (right - left) / 2 - dx, y=self.page[1] - bottom - dy, txt="X")

    def stamp(self, field: str, stamp: dict | None, reserve: float = 0, size: float = 4.6):
        """Which signing this was, when it was made in UTC and where from - small, at the right
        end of the signature box, so it reads as belonging to the hand beside it.

        `reserve` is the room the signature itself takes at the left. The two halves of a
        signature box are MEASURED against each other rather than assumed to fit: the employee's
        box on an I-9 is 323pt wide and the employer's is 191pt, and a stamp laid out for the
        first runs straight through the hand on the second. Where the room is short, the time and
        the address go on their own lines instead of sharing one.
        """
        box = self.where.get(field)
        if not stamp or not box:
            return
        left, bottom, right, top = box
        when = str(stamp.get("signedon") or "").replace("T", " ")[:19]
        ip = stamp.get("ip") or "not recorded"
        self.pdf.set_font("Helvetica", size=size)

        room = (right - left) - reserve - 4
        lines = [str(stamp.get("recordid") or ""), f"{when} UTC · IP {ip}"]
        if any(self.pdf.get_string_width(x) > room for x in lines):
            lines = [str(stamp.get("recordid") or ""), f"{when} UTC", f"IP {ip}"]
        # Centred on the box rather than pinned to its top, so a three-line stamp sits level with
        # the signature instead of climbing out of a box that is only a line and a half tall.
        leading = size * 1.17
        block = len(lines) * leading
        y = self.page[1] - top + max(leading, ((top - bottom) - block) / 2 + leading)

        self.pdf.set_text_color(*FAINT)
        for n, line in enumerate(lines):
            self.pdf.text(x=right - 2 - self.pdf.get_string_width(line), y=y + n * leading,
                          txt=line)
        self.pdf.set_text_color(*INK)

    def note(self, field: str, lines: list[str], size: float = 7, leading: float = 1.45):
        """Several lines down a tall box, from its top edge.

        For the boxes a form sets aside for the filer's own words, where `write` - which centres
        one line in its box - says nothing useful."""
        box = self.where.get(field)
        if not box or not lines:
            return
        left, bottom, right, top = box
        # Shrunk as a block, not line by line, so the lines stay the same size as each other.
        width = right - left - 6
        self.pdf.set_font("Helvetica", size=size)
        while size > 5 and max(self.pdf.get_string_width(x) for x in lines) > width:
            size -= 0.5
            self.pdf.set_font("Helvetica", size=size)
        y = self.page[1] - top + size
        for line in lines:
            if y > self.page[1] - bottom:
                break
            self.pdf.text(x=left + 3, y=y, txt=line)
            y += size * leading

    def onto(self, pages) -> bytes:
        """Merge the drawing onto the first page and keep the whole form behind it.

        THE WHOLE FORM. These are four-page documents and their own footers say so - an I-9 that
        prints "Page 1 of 4" and is one page long reads as a record somebody has torn up. The
        pages after the first carry the instructions, the Lists of Acceptable Documents and the
        supplements. Nothing is written on them; they are kept because what gets filed is the
        form, not the part of it that has answers on it.

        Every page comes out flat: nothing on any of them can be typed over later, which is what
        8 CFR 274a.2(e)(1)(ii) asks of an electronically stored I-9, and it is the reason a
        signature on one of these cannot be argued with afterwards.
        """
        pages = list(pages) if isinstance(pages, (list, tuple)) else [pages]
        pages[0].merge_page(PdfReader(io.BytesIO(self.pdf.output())).pages[0])
        writer = PdfWriter()
        for page in pages:
            if "/Annots" in page:
                del page[NameObject("/Annots")]
            writer.add_page(page)
        if "/AcroForm" in writer._root_object:
            del writer._root_object[NameObject("/AcroForm")]
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
