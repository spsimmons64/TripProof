###################################################################################################
# Photographs become documents before they are filed.
#
# What arrives from a phone is a photograph: sideways because of how it was held, in whatever format
# that handset favours this year, and openable only by something that knows about images. What a
# driver's file needs is a document - one that prints, that a browser will draw without a plugin,
# that survives being handed to an auditor, and that is the same thing in five years as it is today.
#
# So every image filed against a driver is turned into a single-page PDF at the moment it is
# stored, at its own size, with the orientation the camera recorded folded in. The bytes that are
# kept are the bytes that will be read back - nothing is converted again later.
#
# Anything that is not an image is left exactly as it came: a PDF is already a document, and a file
# nobody can read is better kept whole than mangled into something that looks readable.
###################################################################################################
import io

from PIL import Image, ImageOps

# What a camera produces, plus the formats a scanner emails. HEIC is not read by Pillow without a
# plugin, so it is left alone rather than half-converted.
CONVERTS = ("image/jpeg", "image/jpg", "image/png", "image/gif", "image/bmp", "image/tiff",
            "image/webp")

# A page no larger than this on its longest side. A licence photographed at 12 megapixels is not a
# better record of a licence - it is the same record, eight times the size, on a sheet nobody can
# print.
MAX_EDGE = 2200


def is_image(mimetype: str | None) -> bool:
    return (mimetype or "").split(";")[0].strip().lower() in CONVERTS


def bind(parts: list[bytes]) -> bytes:
    """Several PDFs as one, in the order given - the front of a card and then its back.

    A licence is one document photographed twice; filing it as two leaves whoever reads the file
    opening them one after the other and holding them together in their head."""
    from pypdf import PdfReader, PdfWriter      # imported here: only binding needs it
    parts = [p for p in parts if p]
    if len(parts) == 1:
        return parts[0]
    writer = PdfWriter()
    for part in parts:
        for page in PdfReader(io.BytesIO(part)).pages:
            writer.add_page(page)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def to_pdf(data: bytes, mimetype: str | None, filename: str | None = None) -> tuple[bytes, str, str]:
    """An image as a one-page PDF, answering (bytes, mimetype, filename).

    Anything that is not an image, or that cannot be read as one, comes back untouched: a file that
    will not open is still the file that was sent, and pretending otherwise loses it."""
    name = filename or "document"
    if not is_image(mimetype):
        return data, (mimetype or "application/octet-stream"), name
    try:
        image = Image.open(io.BytesIO(data))
        # Phones record which way up the picture was taken rather than rotating the pixels; a page
        # has no such note, so the rotation is applied before it becomes one.
        image = ImageOps.exif_transpose(image)
        if max(image.size) > MAX_EDGE:
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        # A PDF page has no transparency, and an alpha channel left in place prints as black.
        if image.mode in ("RGBA", "LA", "P"):
            page = Image.new("RGB", image.size, "white")
            image = image.convert("RGBA")
            page.paste(image, mask=image.split()[-1])
            image = page
        elif image.mode != "RGB":
            image = image.convert("RGB")
        out = io.BytesIO()
        image.save(out, format="PDF", resolution=150.0)
    except Exception:
        return data, (mimetype or "application/octet-stream"), name
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return out.getvalue(), "application/pdf", f"{stem}.pdf"
