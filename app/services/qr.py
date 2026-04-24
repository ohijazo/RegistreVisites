import io
import base64

import qrcode

from app.config import settings


def generate_qr_base64(data: str) -> str:
    """Genera un QR i el retorna com a string base64 per incrustar a l'HTML."""
    qr = qrcode.QRCode(version=1, box_size=8, border=4)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def exit_url(exit_token: str) -> str:
    """URL completa que codifica el QR de sortida."""
    return f"{settings.BASE_URL}/checkout/{exit_token}"
