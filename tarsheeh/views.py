from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.forms import modelformset_factory
from django.shortcuts import render, redirect
from django.urls import reverse

from .models import Batch, Opportunity, Candidate, Application
from .forms import BatchForm, OpportunityForm, CandidateForm, ApplicationCreateForm, PasteImportForm


# ======================================================
# Helpers
# ======================================================

ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _to_dec(v: Any) -> Decimal:
    """Parse Decimal from string, supports Arabic digits and comma."""
    try:
        s = str(v).strip().translate(ARABIC_DIGITS)
        s = s.replace(",", ".")
        return Decimal(s) if s else Decimal("0")
    except Exception:
        return Decimal("0")


def _set_if_has(obj: Any, field: str, value: Any) -> None:
    """Set attribute only if model has that field/attr."""
    if hasattr(obj, field):
        setattr(obj, field, value)


def _is_header_row(parts: list[str]) -> bool:
    """Detect Excel header row to skip it."""
    if not parts:
        return False
    first = (parts[0] or "").strip()
    second = (parts[1] or "").strip() if len(parts) > 1 else ""
    # common header markers
    return (
        "اسم" in first and "المتقدم" in first
    ) or (
        "السجل" in second and "المدني" in second
    )


def _split_line(line: str) -> list[str]:
    """
    Split a pasted Excel line.
    Excel usually uses TAB, but support comma as fallback.
    """
    line = line.strip()
    if not line:
        return []
    if "\t" in line:
        parts = [p.strip() for p in line.split("\t")]
    else:
        parts = [p.strip() for p in line.split(",")]
    return parts


# ======================================================
# Dashboard
# ======================================================

def dashboard(request):
    stats = {
        "batches": Batch.objects.count(),
        "opps": Opportunity.objects.count(),
        "candidates": Candidate.objects.count(),
        "apps": Application.objects.count(),
        "eligible": Application.objects.filter(is_eligible=True).count(),
        "pending_scores": Application.objects.filter(Q(file_score=0) | Q(interview_score=0)).count(),
    }
    batches = Batch.objects.order_by("-created_at")[:10]
    opps = Opportunity.objects.order_by("-created_at")[:12]
    return render(request, "tarsheeh/dashboard.html", {"stats": stats, "batches": batches, "opps": opps})


# ======================================================
# Create Batch / Opportunity
# ======================================================

def create_batch(request):
    form = BatchForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إنشاء الدفعة ✅")
        return redirect("tarsheeh:dashboard")
    return render(request, "tarsheeh/form.html", {"title": "إنشاء دفعة", "form": form})


def create_opportunity(request):
    form = OpportunityForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إنشاء الفرصة ✅")
        return redirect("tarsheeh:dashboard")
    return render(request, "tarsheeh/form.html", {"title": "إنشاء فرصة/مدرسة", "form": form})


# ======================================================
# Add Manual
# ======================================================

@transaction.atomic
def add_manual(request):
    cand_form = CandidateForm(request.POST or None, prefix="c")
    app_form = ApplicationCreateForm(request.POST or None, prefix="a")

    if request.method == "POST" and cand_form.is_valid() and app_form.is_valid():
        national_id = cand_form.cleaned_data["national_id"]

        cand, _ = Candidate.objects.get_or_create(
            national_id=national_id,
            defaults={"full_name": cand_form.cleaned_data["full_name"]},
        )

        for f, v in cand_form.cleaned_data.items():
            setattr(cand, f, v)
        cand.save()

        app = app_form.save(commit=False)
        app.candidate = cand
        app.save()

        messages.success(request, "تمت إضافة المرشح ✅")
        return redirect(reverse("tarsheeh:applications") + f"?batch={app.batch_id}&opp={app.opportunity_id}")

    return render(request, "tarsheeh/add_manual.html", {"cand_form": cand_form, "app_form": app_form})


# ======================================================
# Paste Import (Excel)
# 18 Columns supported (in this exact order):
# 1  اسم المتقدم
# 2  السجل المدني
# 3  رقم الجوال
# 4  التخصص
# 5  الرتبة
# 6  العمل الحالي
# 7  تاريخ المباشرة (هجري)
# 8  مدرسة المتقدم
# 9  قطاع المتقدم
# 10 الوظيفة المتقدم عليها
# 11 الفرصة
# 12 قطاع الفرصة
# 13 سبق العمل في الإدارة المدرسية
# 14 سنوات عمل مدير
# 15 سنوات عمل وكيل
# 16 درجة الملف
# 17 درجة المقابلة
# 18 المجموع الكلي (اختياري - الموقع يحسبه)
# ======================================================

@transaction.atomic
def paste_import(request):
    """
    Supports two modes:
    - Single Opportunity: form provides opportunity => applies to all rows
    - Multi Opportunity: if opportunity not provided (or template sends empty),
      use columns (11 الفرصة, 12 قطاع الفرصة) to create/get opportunity per row.
    """
    form = PasteImportForm(request.POST or None)

    # For templates that don't use {{ form }} (manual selects)
    batches = Batch.objects.order_by("-created_at")
    opps = Opportunity.objects.order_by("-created_at")

    if request.method == "POST":
        # If using the Django form
        if form.is_valid():
            batch = form.cleaned_data["batch"]
            fixed_opp = form.cleaned_data.get("opportunity")
            fixed_role = (form.cleaned_data.get("applied_role") or "").strip()
            text = (form.cleaned_data.get("text") or "").strip()
        else:
            # Fallback: support manual template fields names
            batch_id = request.POST.get("batch", "").strip()
            opp_id = request.POST.get("opp", "").strip()
            fixed_role = (request.POST.get("role", "") or "").strip()
            text = (request.POST.get("paste", "") or "").strip()

            if not batch_id or not text:
                messages.error(request, "اختر الدفعة والصق البيانات ثم أعد المحاولة.")
                return render(request, "tarsheeh/paste_import.html", {"form": form, "batches": batches, "opps": opps})

            batch = Batch.objects.filter(id=batch_id).first()
            fixed_opp = Opportunity.objects.filter(id=opp_id).first() if opp_id else None

            if not batch:
                messages.error(request, "الدفعة غير موجودة.")
                return render(request, "tarsheeh/paste_import.html", {"form": form, "batches": batches, "opps": opps})

        if not text:
            messages.error(request, "الصق البيانات ثم أعد المحاولة.")
            return render(request, "tarsheeh/paste_import.html", {"form": form, "batches": batches, "opps": opps})

        created_apps = 0
        created_cands = 0
        skipped = 0

        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue

            parts = _split_line(line)
            if not parts:
                continue

            # Skip header row if pasted
            if _is_header_row(parts):
                continue

            # Ensure length 18
            parts += [""] * (18 - len(parts))

            (
                full_name, national_id, phone,
                specialization, rank, current_work, start_hijri,
                applicant_school, applicant_sector,
                applied_role,
                opportunity_name, opportunity_sector,
                worked_admin,
                y_dir, y_dep,
                file_score, interview_score, total_ignored
            ) = parts[:18]

            full_name = (full_name or "").strip()
            national_id = (national_id or "").strip().translate(ARABIC_DIGITS)
            phone = (phone or "").strip().translate(ARABIC_DIGITS)

            if not full_name or not national_id:
                skipped += 1
                continue

            # Determine opportunity
            opp = fixed_opp
            if opp is None:
                opportunity_name = (opportunity_name or "").strip()
                if not opportunity_name:
                    skipped += 1
                    continue
                opp, _ = Opportunity.objects.get_or_create(
                    name=opportunity_name,
                    defaults={"sector": (opportunity_sector or "").strip()},
                )
                # Update sector if empty
                if hasattr(opp, "sector") and not (opp.sector or "").strip() and (opportunity_sector or "").strip():
                    opp.sector = (opportunity_sector or "").strip()
                    opp.save(update_fields=["sector"])

            # Determine role
            role = (fixed_role or applied_role or "").strip()
            if not role:
                role = "أخرى"

            # Candidate
            cand, was_created = Candidate.objects.get_or_create(
                national_id=national_id,
                defaults={"full_name": full_name},
            )
            if was_created:
                created_cands += 1

            _set_if_has(cand, "full_name", full_name)
            _set_if_has(cand, "phone", phone)
            _set_if_has(cand, "specialization", (specialization or "").strip())
            _set_if_has(cand, "rank", (rank or "").strip())
            _set_if_has(cand, "current_work", (current_work or "").strip())
            _set_if_has(cand, "start_date_hijri", (start_hijri or "").strip())
            _set_if_has(cand, "applicant_school", (applicant_school or "").strip())
            _set_if_has(cand, "applicant_sector", (applicant_sector or "").strip())

            # Boolean-ish fields
            worked = (worked_admin or "").strip()
            if worked:
                yes = worked in ("نعم", "نعم ", "Yes", "yes", "1", "صح", "true", "True")
                _set_if_has(cand, "worked_in_school_admin", yes)

            # Years
            _set_if_has(cand, "years_director", _to_dec(y_dir))
            _set_if_has(cand, "years_deputy", _to_dec(y_dep))

            cand.save()

            # Application (avoid duplicates for same batch/opp/candidate/role)
            app, app_created = Application.objects.get_or_create(
                batch=batch,
                opportunity=opp,
                candidate=cand,
                applied_role=role,
                defaults={},
            )

            # Scores (if fields exist on model)
            fs = _to_dec(file_score)
            ins = _to_dec(interview_score)
            if hasattr(app, "file_score"):
                app.file_score = fs
            if hasattr(app, "interview_score"):
                app.interview_score = ins

            app.save()
            if app_created:
                created_apps += 1

        if created_apps == 0 and created_cands == 0:
            messages.warning(request, "لم يتم إضافة أي صف (تحقق من الترتيب/البيانات).")
        else:
            messages.success(
                request,
                f"تم الاستيراد ✅ | المرشحين الجدد: {created_cands} | الطلبات المضافة: {created_apps} | المتجاهل: {skipped}"
            )

        # Redirect to operations with filters
        red = reverse("tarsheeh:applications") + f"?batch={batch.id}"
        if fixed_opp:
            red += f"&opp={fixed_opp.id}"
        if fixed_role:
            red += f"&role={fixed_role}"
        return redirect(red)

    # GET
    return render(request, "tarsheeh/paste_import.html", {"form": form, "batches": batches, "opps": opps})


# ======================================================
# Operations Screen
# ======================================================

def applications(request):
    batch_id = request.GET.get("batch", "")
    opp_id = request.GET.get("opp", "")
    role = request.GET.get("role", "")
    eligible = request.GET.get("eligible", "")
    q = (request.GET.get("q", "")).strip()

    qs = Application.objects.select_related("candidate", "batch", "opportunity").all()

    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    if opp_id:
        qs = qs.filter(opportunity_id=opp_id)
    if role:
        qs = qs.filter(applied_role=role)
    if eligible in ("1", "0"):
        qs = qs.filter(is_eligible=(eligible == "1"))
    if q:
        qs = qs.filter(
            Q(candidate__full_name__icontains=q)
            | Q(candidate__national_id__icontains=q)
            | Q(candidate__applicant_school__icontains=q)
            | Q(opportunity__name__icontains=q)
        )

    qs = qs.order_by("-is_eligible", "-total_score", "id")

    kpi = {
        "count": qs.count(),
        "eligible": qs.filter(is_eligible=True).count(),
        "pending": qs.filter(Q(file_score=0) | Q(interview_score=0)).count(),
    }

    return render(
        request,
        "tarsheeh/applications.html",
        {
            "rows": qs[:500],
            "batches": Batch.objects.order_by("-created_at"),
            "opps": Opportunity.objects.order_by("-created_at"),
            "kpi": kpi,
            "filters": {"batch": batch_id, "opp": opp_id, "role": role, "eligible": eligible, "q": q},
        },
    )


# ======================================================
# Scores Screen
# ======================================================

def scores(request):
    batch_id = request.GET.get("batch", "")
    opp_id = request.GET.get("opp", "")
    role = request.GET.get("role", "")
    pending = request.GET.get("pending", "")

    qs = Application.objects.select_related("candidate", "batch", "opportunity").all()

    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    if opp_id:
        qs = qs.filter(opportunity_id=opp_id)
    if role:
        qs = qs.filter(applied_role=role)
    if pending == "1":
        qs = qs.filter(Q(file_score=0) | Q(interview_score=0))

    qs = qs.order_by("-is_eligible", "-total_score", "id")[:300]

    Formset = modelformset_factory(Application, fields=("file_score", "interview_score"), extra=0)

    if request.method == "POST":
        formset = Formset(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            messages.success(request, "تم حفظ الدرجات ✅")
            return redirect(request.get_full_path())
    else:
        formset = Formset(queryset=qs)

    return render(
        request,
        "tarsheeh/scores.html",
        {
            "formset": formset,
            "batches": Batch.objects.order_by("-created_at"),
            "opps": Opportunity.objects.order_by("-created_at"),
            "filters": {"batch": batch_id, "opp": opp_id, "role": role, "pending": pending},
        },
    )
