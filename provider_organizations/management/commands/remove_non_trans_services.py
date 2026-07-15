from django.core.management.base import BaseCommand
from django.db import transaction

from provider_organizations.models import Service


# Exact service names marked [DELETE] in Services.pdf.
SERVICES_TO_DELETE = {
    "Lab Monitoring",
    "Surgery Referral Support",
    "Pharmacy Coordination",
    "Pediatrics",
    "Speech Therapist",
    "Speech-Language Pathologist",
    "Birth Control and Emergency Contraception",
    "Adolescent Medicine",
    "Sexual Health",
    "Family & Parenting Support",
    "Substance Use and Recovery",
    "Autism",
    "Anesthesiologist",
    "Physical Medicine and Rehabilitation",
    "Pain Physician",
    "Geriatrics",
    "Dietitian",
    "Nutrition",
    "Nutrition and Wellness",
    "Psychiatric Nurse",
    "Colorectal Doctor",
    "Naturopathic and Integrated Medicine",
    "Menopause",
    "Yoga",
    "Midwife",
    "Dental Health",
    "Dentist",
    "Aging Services",
    "Podiatry",
    "Wellness Services",
    "Addiction Recovery",
    "Andrologist",
    "Physician Assistant",
    "Geneticist",
    "Addiction Medicine",
    "Rehabilitation Therapist",
    "Respiratory Therapist",
    "Naturopathic",
    "Reiki",
    "Chiropractor",
    "Radiologist",
    "Infectious Disease",
    "Pathologist",
    "Acupuncturist",
    "Massage Therapist",
    "Fertility",
    "Abortion",
    "Botox",
    "Allergist",
    "Registered Nurse",
    "Orthodontist",
    "Physical Therapist Assistant",
    "Neurologist",
    "Chinese Medicine Doctor",
    "Cancer Genetic Counseling",
    "Child Psychologist",
    "Medication Assisted Treatment",
    "Pharmacist",
    "Gynecologist",
    "Doula",
    "Pediatric Services",
    "Reconstructive Surgeon",
    "Pap Smear",
    "Safer Sex Information & Services",
    "Health Issues Counselor",
    "Dental Hygienist",
    "CPAP Testing Doctor",
    "Emergency Doctor",
    "Toxicologist",
    "Reproductive Endocrinologist",
    "Occupational Therapist",
    "Aesthetic Medicine",
    "Pharmacology",
    "High-Resolution Anoscopy",
    "Dermal Fillers",
    "Cardiologist",
    "Rheumatologist",
    "Hospitalist",
    "Breast Health",
    "Sports Medicine Doctor",
    "Neuropsychologist",
    "Sleep Doctor",
    "General Surgeon",
    "COVID-19 Services",
    "Urgent Care",
    "Hematologist",
    "Oncology",
    "Oncologist",
    "Gastroenterologist",
    "Orthopedic Surgeon",
    "Oral and Maxillofacial Surgeon",
    "Optometrist",
    "Alternative Insemination",
    "Periodontist",
    "Ophthalmologist",
    "Hepatologist",
    "Certified Ayurvedic Practitioner (CAP)",
    "Lactation Consultant",
    "Violence Recovery Program",
    "Spinal Cord Injury Medicine",
    "Generalist",
    "Osteopath",
    "Nephrologist",
    "Ayurvedic Doctor (AD)",
    "Referrals",
    "Radiation Oncologist",
    "Palliative Care",
    "Erectile Medication",
    "Smoking Cessation",
    "Certified Medical Assistant",
    "Audiologist",
    "Pediatric Surgeon",
    "Critical Care Surgeon",
    "Undersea and Hyperbaric Medicine",
    "Orthotist",
    "Prosthetist",
    "Pulmonologist",
    "Pediatric Cardiologist",
    "Laparoscopy",
    "Cardiovascular Prevention",
    "Athletic Trainer",
    "Critical Care Medicine Doctor",
    "Proctologist",
    "Immunologist",
    "Neurosurgeon",
    "Dyslexia Therapist",
    "Hospice Care",
    "Phlebotomy",
    "Aerospace Medicine Doctor",
    "Insurance Enrollment Assistance",
    "Immunizations & Flu Shots",
    "Radiologic Technologist",
    "Home Health",
    "Cardiothoracic Surgeon",
    "Pediatric Oncologist",
    "Vascular Surgeon",
}


class Command(BaseCommand):
    help = "Remove Service records that are not directly related to transgender care."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List services that would be deleted without deleting anything.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip the deletion confirmation prompt.",
        )

    def handle(self, *args, **options):
        services = list(Service.objects.order_by("id"))
        removable = [service for service in services if service.name in SERVICES_TO_DELETE]

        self.stdout.write("Services currently stored:")
        for service in services:
            classification = "KEEP" if service not in removable else "DELETE"
            self.stdout.write(f"  [{classification}] {service.id}: {service.name}")

        self.stdout.write(
            self.style.WARNING(
                f"Services to delete: {len(removable)} of {len(services)}"
            )
        )

        if options["dry_run"] or not removable:
            return

        if not options["yes"]:
            answer = input("Delete these services and their related records? [y/N] ")
            if answer.strip().lower() not in {"y", "yes"}:
                self.stdout.write("Deletion cancelled.")
                return

        with transaction.atomic():
            deleted_count, _ = Service.objects.filter(
                id__in=[service.id for service in removable]
            ).delete()

        self.stdout.write(self.style.SUCCESS(f"Deleted {deleted_count} database records."))
