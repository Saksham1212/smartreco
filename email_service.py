"""Email sending via SMTP (aiosmtplib) for the daily recommendation digest."""
import logging

import aiosmtplib
from email.message import EmailMessage

from config import settings

logger = logging.getLogger("smartreco.email")


def render_digest_html(full_name: str, narrative: str, products: list[dict], base_url: str = "") -> str:
    first_name = full_name.split(" ")[0] if full_name else "there"

    product_rows = ""
    for p in products:
        link = f"{base_url}/products/{p['id']}"
        product_rows += f"""
        <tr>
          <td style="padding:12px 0;border-bottom:1px solid #2a3441;">
            <a href="{link}" style="color:#4ade80;text-decoration:none;font-weight:600;font-size:15px;">{p['title']}</a>
            <div style="color:#94a3b8;font-size:13px;margin-top:4px;">{p['category']} &middot; {p['difficulty_level'].title()} &middot; ${p['price']:.2f}</div>
          </td>
        </tr>
        """

    return f"""
    <html>
      <body style="margin:0;padding:0;background-color:#0f172a;font-family:Arial,Helvetica,sans-serif;">
        <div style="max-width:560px;margin:0 auto;padding:32px 24px;">
          <h1 style="color:#f8fafc;font-size:22px;margin-bottom:4px;">SmartReco</h1>
          <p style="color:#94a3b8;font-size:13px;margin-top:0;">Your daily personalized recommendations</p>
          <p style="color:#e2e8f0;font-size:16px;">Hi {first_name},</p>
          <div style="background-color:#1e293b;border-left:4px solid #4ade80;padding:16px 20px;border-radius:6px;margin:16px 0;">
            <p style="color:#e2e8f0;font-size:15px;line-height:1.6;margin:0;">{narrative}</p>
          </div>
          <h2 style="color:#f8fafc;font-size:16px;margin-top:28px;">Recommended for you</h2>
          <table style="width:100%;border-collapse:collapse;">
            {product_rows}
          </table>
          <p style="color:#64748b;font-size:12px;margin-top:32px;border-top:1px solid #2a3441;padding-top:16px;">
            You're receiving this because you have an account on SmartReco. Log in any time to update your
            preferences by browsing courses that interest you.
          </p>
        </div>
      </body>
    </html>
    """


async def send_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str | None]:
    """Send a single HTML email. Returns (success, error_message)."""
    if not settings.EMAIL_ENABLED:
        return False, "EMAIL_ENABLED is false"

    message = EmailMessage()
    message["From"] = settings.EMAIL_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content("This email requires an HTML-capable client to view.")
    message.add_alternative(html_body, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            start_tls=settings.SMTP_PORT != 465,
        )
        return True, None
    except Exception as exc:
        logger.exception("Failed to send email to %s", to_email)
        return False, str(exc)
