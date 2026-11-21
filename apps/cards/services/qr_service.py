import io
import csv
import zipfile
import qrcode
import qrcode.image.svg
from django.conf import settings
from apps.cards.services.card_generator import sanitize_csv_cell

CANONICAL_PRODUCTION_DOMAIN = "https://strideid.com"


def get_canonical_card_url(card_code: str, force_production: bool = True) -> str:
    """
    Returns the permanent redirect URL for physical card encoding.
    Default enforces canonical production domain (https://strideid.com/c/<card_code>/)
    so hardware printed cards always point to production.
    """
    clean_code = str(card_code).strip()
    if force_production:
        return f"{CANONICAL_PRODUCTION_DOMAIN}/c/{clean_code}/"
    base = getattr(settings, "SITE_URL", CANONICAL_PRODUCTION_DOMAIN).rstrip("/")
    return f"{base}/c/{clean_code}/"


def generate_qr_png_bytes(card_code: str, force_production: bool = True) -> bytes:
    """Generates print-ready high-contrast PNG bytes for a card."""
    target_url = get_canonical_card_url(card_code, force_production=force_production)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,  # ~480px at 40 modules
        border=3,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0A0A0A", back_color="#FFFFFF")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_qr_svg_bytes(card_code: str, force_production: bool = True) -> bytes:
    """Generates resolution-independent SVG vector bytes for laser engraving."""
    target_url = get_canonical_card_url(card_code, force_production=force_production)
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
        image_factory=qrcode.image.svg.SvgPathImage,
    )
    qr.add_data(target_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0A0A0A", back_color="#FFFFFF")

    buffer = io.BytesIO()
    img.save(buffer)
    return buffer.getvalue()


def generate_batch_manufacturing_zip(cards, batch_reference: str) -> io.BytesIO:
    """
    Compiles an in-memory ZIP archive for production / manufacturing.
    Contains:
    - svg/<card_code>.svg  (vector paths for laser engraver)
    - png/<card_code>.png  (high-res raster previews)
    - nfc_encoding_manifest.csv (factory NFC chip writing manifest)

    NOTE: Plaintext activation PINs are strictly excluded from this archive.
    """
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        manifest_rows = []
        manifest_rows.append([
            "Batch_Reference",
            "Card_Code",
            "NFC_Target_URL",
            "Material_Finish",
            "Provisioning_Stage",
            "Created_At",
        ])

        for card in cards:
            code = card.card_code
            nfc_url = get_canonical_card_url(code, force_production=True)

            # Generate SVG and PNG in-memory
            svg_data = generate_qr_svg_bytes(code, force_production=True)
            png_data = generate_qr_png_bytes(code, force_production=True)

            # Write into subfolders
            zip_file.writestr(f"svg/{code}.svg", svg_data)
            zip_file.writestr(f"png/{code}.png", png_data)

            # Append sanitized CSV row
            manifest_rows.append([
                sanitize_csv_cell(card.batch_reference or batch_reference),
                sanitize_csv_cell(code),
                sanitize_csv_cell(nfc_url),
                sanitize_csv_cell(card.get_material_display()),
                sanitize_csv_cell(card.get_provisioning_stage_display()),
                sanitize_csv_cell(card.created_at.strftime("%Y-%m-%d %H:%M UTC") if card.created_at else ""),
            ])

        # Write manifest CSV
        csv_buffer = io.StringIO()
        writer = csv.writer(csv_buffer)
        for row in manifest_rows:
            writer.writerow(row)

        zip_file.writestr("nfc_encoding_manifest.csv", csv_buffer.getvalue().encode("utf-8"))

    zip_buffer.seek(0)
    return zip_buffer
