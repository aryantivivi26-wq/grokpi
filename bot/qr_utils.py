"""Generate QR code PNG bytes from QRIS content string."""

import io
import qrcode


def generate_qr_png(data: str) -> bytes:
    """Generate a QR code PNG image from raw QRIS content string.

    Returns PNG bytes ready to send via Telegram.
    """
    qr = qrcode.QRCode(
        version=None,  # auto-size
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
