from django.core.management.base import BaseCommand

from apps.accounts.models import Role, User
from apps.service_requests.models import Category

CATEGORIES = [
    ("NID Request", "New, corrected or replacement national ID card"),
    ("Passport Request", "New passport or renewal"),
    ("Missing Report", "Report a missing person or item"),
    ("Police Verification", "Police clearance / verification certificate"),
    ("Birth Certificate", "Birth registration or copy"),
    ("Other", "Any other government service"),
]
USERS = [
    ("admin@example.com", "+8801700000001", "System Admin", Role.ADMIN),
    ("officer1@example.com", "+8801700000011", "Officer Karim", Role.OFFICER),
    ("officer2@example.com", "+8801700000012", "Officer Rahima", Role.OFFICER),
    ("officer3@example.com", "+8801700000013", "Officer Salam", Role.OFFICER),
    ("citizen@example.com", "+8801700000021", "Demo Citizen", Role.CITIZEN),
]


class Command(BaseCommand):
    help = "Create demo categories and users (idempotent). Do NOT use the demo password in production."

    def add_arguments(self, parser):
        parser.add_argument("--password", default="Demo@12345")

    def handle(self, *args, **opts):
        for name, desc in CATEGORIES:
            Category.objects.get_or_create(name=name, defaults={"description": desc})
        import os
        reset = os.environ.get("RESET_DEMO_PASSWORDS", "").lower() in {"1", "true", "yes"}
        for email, phone, name, role in USERS:
            existing = User.objects.filter(email=email).first()
            if existing:
                if reset:
                    existing.set_password(opts["password"])
                    existing.save()
                continue
            if role == Role.ADMIN:
                User.objects.create_superuser(email, opts["password"], phone=phone, full_name=name)
            else:
                User.objects.create_user(email, opts["password"], phone=phone, full_name=name, role=role)
        self.stdout.write(self.style.SUCCESS(f"Seeded. Login with any demo email and password '{opts['password']}'."))
        self.stdout.write("Emails: " + ", ".join(u[0] for u in USERS))
