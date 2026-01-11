from decimal import Decimal
from django.db import models


class Batch(models.Model):
    title = models.CharField("اسم الدفعة", max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class Opportunity(models.Model):
    name = models.CharField("اسم الفرصة/المدرسة", max_length=255)
    sector = models.CharField("القطاع", max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Candidate(models.Model):
    full_name = models.CharField("اسم المتقدم", max_length=255)
    national_id = models.CharField("السجل المدني", max_length=20, unique=True, db_index=True)
    phone = models.CharField("رقم الجوال", max_length=30, blank=True, default="")

    current_job = models.CharField("العمل الحالي", max_length=50, blank=True, default="")
    years_deputy = models.DecimalField("سنوات عمل وكيل", max_digits=5, decimal_places=2, default=0)
    years_director = models.DecimalField("سنوات عمل مدير", max_digits=5, decimal_places=2, default=0)

    applicant_school = models.CharField("مدرسة المتقدم", max_length=255, blank=True, default="")
    applicant_sector = models.CharField("قطاع المتقدم", max_length=255, blank=True, default="")

    def __str__(self):
        return f"{self.full_name} ({self.national_id})"


class Application(models.Model):
    ROLE_CHOICES = [
        ("مدير", "مدير"),
        ("وكيل", "وكيل"),
        ("أخرى", "أخرى"),
    ]

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name="applications")
    opportunity = models.ForeignKey(Opportunity, on_delete=models.CASCADE, related_name="applications")
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="applications")

    applied_role = models.CharField("الوظيفة المتقدم عليها", max_length=50, choices=ROLE_CHOICES, default="مدير")

    file_score = models.DecimalField("درجة الملف", max_digits=6, decimal_places=2, default=0)
    interview_score = models.DecimalField("درجة المقابلة", max_digits=6, decimal_places=2, default=0)
    total_score = models.DecimalField("المجموع الكلي", max_digits=6, decimal_places=2, default=0, editable=False)

    is_eligible = models.BooleanField("مستوفي الشرط", default=False, editable=False)
    ineligible_reason = models.CharField("سبب الاستبعاد", max_length=255, blank=True, default="", editable=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def compute_total(self) -> Decimal:
        return (self.file_score or Decimal("0")) + (self.interview_score or Decimal("0"))

    def compute_eligibility(self):
        y_dep = self.candidate.years_deputy or 0
        y_dir = self.candidate.years_director or 0
        job = (self.candidate.current_job or "").strip()

        deputy_ok = y_dep >= 3
        is_director = (job == "مدير") or (y_dir > 0)

        ok = deputy_ok or is_director
        reason = "" if ok else "غير مستوفي: ليس مديرًا وسنوات الوكيل أقل من 3"
        return ok, reason

    def save(self, *args, **kwargs):
        self.total_score = self.compute_total()
        ok, reason = self.compute_eligibility()
        self.is_eligible = ok
        self.ineligible_reason = reason
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=["batch", "opportunity"]),
            models.Index(fields=["is_eligible", "-total_score"]),
        ]

    def __str__(self):
        return f"{self.candidate} -> {self.opportunity}"
