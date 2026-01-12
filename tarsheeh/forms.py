from __future__ import annotations

from django import forms

from .models import Batch, Opportunity, Candidate, Application


# ======================================================
# Simple Forms
# ======================================================

class BatchForm(forms.ModelForm):
    class Meta:
        model = Batch
        fields = ["title"]


class OpportunityForm(forms.ModelForm):
    class Meta:
        model = Opportunity
        fields = ["name", "sector"]


class CandidateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = [
            "full_name",
            "national_id",
            "phone",
            "current_job",
            "years_deputy",
            "years_director",
            "applicant_school",
            "applicant_sector",
        ]


class ApplicationCreateForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["batch", "opportunity", "applied_role"]


# ======================================================
# Paste Import (Excel Copy/Paste)
# - opportunity OPTIONAL to allow multi-school paste
# - applied_role OPTIONAL to read per-row role (column 10)
# ======================================================

class PasteImportForm(forms.Form):
    batch = forms.ModelChoiceField(
        label="الدفعة",
        queryset=Batch.objects.order_by("-created_at"),
        required=True,
        empty_label=None,
    )

    opportunity = forms.ModelChoiceField(
        label="الفرصة/المدرسة (اختياري)",
        queryset=Opportunity.objects.order_by("-created_at"),
        required=False,
        help_text="اتركها فارغة إذا كانت بيانات اللصق تحتوي على (الفرصة + قطاع الفرصة) لكل صف.",
    )

    applied_role = forms.ChoiceField(
        label="الوظيفة (اختياري)",
        choices=[("", "حسب العمود داخل البيانات")]
        + list(
            getattr(
                Application,
                "ROLE_CHOICES",
                [("مدير", "مدير"), ("وكيل", "وكيل"), ("أخرى", "أخرى")],
            )
        ),
        required=False,
        initial="",
        help_text="إذا تركتها فارغة سيُؤخذ الدور من عمود (الوظيفة المتقدم عليها).",
    )

    text = forms.CharField(
        label="الصق البيانات هنا",
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 12,
                "placeholder": (
                    "الصق الصفوف هنا (Tab بين الأعمدة) بنفس الترتيب:\n"
                    "اسم المتقدم\tالسجل المدني\tرقم الجوال\tالتخصص\tالرتبة\tالعمل الحالي\tتاريخ المباشرة (هجري)\t"
                    "مدرسة المتقدم\tقطاع المتقدم\tالوظيفة المتقدم عليها\tالفرصة\tقطاع الفرصة\t"
                    "سبق العمل في الإدارة المدرسية\tسنوات عمل مدير\tسنوات عمل وكيل\tدرجة الملف\tدرجة المقابلة\tالمجموع الكلي"
                ),
            }
        ),
    )


# ======================================================
# Upload Excel (.xlsx) Import
# ======================================================

class UploadExcelForm(forms.Form):
    batch = forms.ModelChoiceField(
        label="الدفعة",
        queryset=Batch.objects.order_by("-created_at"),
        required=True,
        empty_label=None,
    )

    file = forms.FileField(
        label="ملف Excel (.xlsx)",
        required=True,
        help_text="ارفع ملف .xlsx (يفضل أن يحتوي صف العناوين).",
    )

    multi_school = forms.BooleanField(
        label="استيراد متعدد المدارس (من داخل الملف)",
        required=False,
        initial=False,
        help_text="إذا مفعل: سيتم قراءة (الفرصة + قطاع الفرصة) من كل صف.",
    )

    read_role_from_data = forms.BooleanField(
        label="قراءة الوظيفة من داخل البيانات (الوظيفة المتقدم عليها)",
        required=False,
        initial=True,
    )

    applied_role = forms.ChoiceField(
        label="الوظيفة الافتراضية (إذا لم توجد بالملف)",
        choices=list(
            getattr(
                Application,
                "ROLE_CHOICES",
                [("مدير", "مدير"), ("وكيل", "وكيل"), ("أخرى", "أخرى")],
            )
        ),
        initial="مدير",
        required=False,
    )

    opportunity = forms.ModelChoiceField(
        label="المدرسة/الفرصة (إذا لم تفعل متعدد المدارس)",
        queryset=Opportunity.objects.order_by("-created_at"),
        required=False,
    )
