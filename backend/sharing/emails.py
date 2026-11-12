from django.conf import settings
from django.core.mail import send_mail


def send_invite_email(*, to_email: str, plan_name: str, inviter_name: str, invite_link: str) -> None:
    first = (inviter_name or "").strip().split(" ")[0] or inviter_name
    subject = f"{first} invited you to {plan_name} on Ongsho"
    body = (
        f"Hi,\n\n"
        f"{inviter_name} invited you to share {plan_name} on Ongsho.\n\n"
        f"Open this link to accept or sign up:\n{invite_link}\n\n"
        f"If you did not expect this email, you can ignore it."
    )
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)
