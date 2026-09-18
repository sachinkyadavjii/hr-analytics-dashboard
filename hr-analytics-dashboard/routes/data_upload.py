import os
import io
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, send_file, session
import pandas as pd

from extensions import db
from auth_utils import permission_required
from models import UploadedDataset
from file_upload_utils import (is_allowed_dataset, file_size_ok, MAX_DATASET_SIZE_BYTES,
                                safe_unique_filename, ensure_dir, delete_file_if_exists)
import dataset_analytics as da
import analytics_engine as ae

data_upload_bp = Blueprint("data_upload", __name__, url_prefix="/data-analytics")

# Datasets are stored OUTSIDE the public static/ folder (under instance/)
# since they may contain sensitive HR data and should never be directly
# downloadable via a guessable URL.
DATASETS_DIR_NAME = "uploads/datasets"


def _datasets_dir():
    instance_path = current_app.instance_path
    path = os.path.join(instance_path, DATASETS_DIR_NAME)
    ensure_dir(path)
    return path


def _full_path(dataset):
    return os.path.join(current_app.instance_path, dataset.stored_path)


def _load_clean(dataset):
    """Loads + cleans a dataset using its confirmed column mapping.
    Returns (raw_df, clean_df) or raises DatasetLoadError."""
    raw_df = da.load_dataframe(_full_path(dataset), dataset.file_type)
    clean_df, _log = da.clean_dataset(raw_df, dataset.column_mapping)
    return raw_df, clean_df


@data_upload_bp.route("/")
@permission_required("view_analytics")
def index():
    datasets = UploadedDataset.query.order_by(UploadedDataset.uploaded_at.desc()).all()
    return render_template("data_upload/index.html", datasets=datasets)


@data_upload_bp.route("/upload", methods=["GET", "POST"])
@permission_required("view_analytics")
def upload():
    if request.method == "GET":
        return render_template("data_upload/upload.html")

    file = request.files.get("dataset_file")
    if not file or file.filename == "":
        flash("Please choose a CSV or Excel file to upload.", "danger")
        return redirect(url_for("data_upload.upload"))

    if not is_allowed_dataset(file.filename):
        flash("Only CSV, XLS, and XLSX files are supported.", "danger")
        return redirect(url_for("data_upload.upload"))

    ok, size = file_size_ok(file, MAX_DATASET_SIZE_BYTES)
    if not ok:
        flash(f"File is too large ({size // (1024*1024)} MB). Maximum allowed is "
              f"{MAX_DATASET_SIZE_BYTES // (1024*1024)} MB.", "danger")
        return redirect(url_for("data_upload.upload"))

    ext = file.filename.rsplit(".", 1)[-1].lower()
    filename = safe_unique_filename(file.filename, prefix="dataset")
    dest_dir = _datasets_dir()
    dest_path = os.path.join(dest_dir, filename)
    file.save(dest_path)

    # Try to parse immediately so we can fail fast with a friendly message
    # for empty/corrupt files, per the "must not crash on messy data" rule.
    try:
        raw_df = da.load_dataframe(dest_path, "csv" if ext == "csv" else "xlsx")
    except da.DatasetLoadError as e:
        os.remove(dest_path)
        flash(f"Could not process this file: {e}", "danger")
        return redirect(url_for("data_upload.upload"))
    except Exception as e:
        os.remove(dest_path)
        flash(f"Unexpected error reading file: {e}", "danger")
        return redirect(url_for("data_upload.upload"))

    mapping, uncertain = da.detect_columns(raw_df.columns)

    dataset = UploadedDataset(
        original_filename=file.filename,
        stored_path=os.path.join(DATASETS_DIR_NAME, filename),
        file_size_bytes=size,
        file_type="csv" if ext == "csv" else "xlsx",
        uploaded_by=session.get("name"),
        row_count=len(raw_df),
        column_count=len(raw_df.columns),
        status="pending_mapping" if uncertain or mapping.get("employee_id") is None else "ready",
    )
    dataset.column_mapping = mapping
    db.session.add(dataset)
    db.session.commit()

    flash(f"'{file.filename}' uploaded successfully ({len(raw_df)} rows, {len(raw_df.columns)} columns).",
          "success")

    if dataset.status == "pending_mapping":
        return redirect(url_for("data_upload.mapping", dataset_id=dataset.id))
    return redirect(url_for("data_upload.quality", dataset_id=dataset.id))


@data_upload_bp.route("/<int:dataset_id>/mapping", methods=["GET", "POST"])
@permission_required("view_analytics")
def mapping(dataset_id):
    dataset = UploadedDataset.query.get_or_404(dataset_id)
    try:
        raw_df = da.load_dataframe(_full_path(dataset), dataset.file_type)
    except da.DatasetLoadError as e:
        flash(str(e), "danger")
        return redirect(url_for("data_upload.index"))

    if request.method == "POST":
        new_mapping = {}
        for canonical in da.COLUMN_ALIASES.keys():
            chosen = request.form.get(f"map_{canonical}", "")
            new_mapping[canonical] = chosen if chosen else None
        dataset.column_mapping = new_mapping
        dataset.status = "ready" if new_mapping.get("employee_id") else "pending_mapping"
        db.session.commit()
        flash("Column mapping saved.", "success")
        if dataset.status == "ready":
            return redirect(url_for("data_upload.quality", dataset_id=dataset.id))
        flash("An Employee ID column is required before analytics can run.", "warning")
        return redirect(url_for("data_upload.mapping", dataset_id=dataset.id))

    current_mapping, uncertain = dataset.column_mapping, []
    if not current_mapping:
        current_mapping, uncertain = da.detect_columns(raw_df.columns)

    return render_template(
        "data_upload/mapping.html", dataset=dataset, columns=list(raw_df.columns),
        mapping=current_mapping, canonical_fields=list(da.COLUMN_ALIASES.keys()),
        uncertain=uncertain,
    )


@data_upload_bp.route("/<int:dataset_id>/quality")
@permission_required("view_analytics")
def quality(dataset_id):
    dataset = UploadedDataset.query.get_or_404(dataset_id)
    try:
        raw_df = da.load_dataframe(_full_path(dataset), dataset.file_type)
    except da.DatasetLoadError as e:
        flash(str(e), "danger")
        return redirect(url_for("data_upload.index"))

    report = da.validate_dataset(raw_df, dataset.column_mapping)
    preview_df = raw_df.head(10)
    dtypes = {c: str(t) for c, t in raw_df.dtypes.items()}

    return render_template(
        "data_upload/quality.html", dataset=dataset, report=report,
        preview_columns=list(preview_df.columns),
        preview_rows=preview_df.fillna("").astype(str).values.tolist(),
        dtypes=dtypes,
    )


@data_upload_bp.route("/<int:dataset_id>/insights")
@permission_required("view_analytics")
def insights(dataset_id):
    dataset = UploadedDataset.query.get_or_404(dataset_id)
    if dataset.status != "ready":
        flash("Please complete column mapping before viewing insights.", "warning")
        return redirect(url_for("data_upload.mapping", dataset_id=dataset.id))

    try:
        raw_df, clean_df = _load_clean(dataset)
    except da.DatasetLoadError as e:
        flash(str(e), "danger")
        return redirect(url_for("data_upload.index"))

    kpis = da.compute_kpis(clean_df)
    charts = {
        "workforce": da.workforce_breakdown(clean_df),
        "attrition": da.attrition_breakdown(clean_df),
        "salary": da.salary_breakdown(clean_df),
        "performance": da.performance_breakdown(clean_df),
        "attendance": da.attendance_breakdown(clean_df),
    }
    business_insights = da.generate_insights(clean_df)

    return render_template(
        "data_upload/insights.html", dataset=dataset, kpis=kpis, charts=charts,
        insights=business_insights, na_label=da.NA,
    )


@data_upload_bp.route("/<int:dataset_id>/compare")
@permission_required("view_analytics")
def compare(dataset_id):
    dataset = UploadedDataset.query.get_or_404(dataset_id)
    if dataset.status != "ready":
        flash("Please complete column mapping before comparing.", "warning")
        return redirect(url_for("data_upload.mapping", dataset_id=dataset.id))

    try:
        _raw_df, clean_df = _load_clean(dataset)
    except da.DatasetLoadError as e:
        flash(str(e), "danger")
        return redirect(url_for("data_upload.index"))

    uploaded_kpis = da.compute_kpis(clean_df)

    main_df = ae.employees_dataframe()
    main_kpis = ae.kpi_summary(main_df)

    rows = [
        ("Total Employees", uploaded_kpis.get("total_employees"), main_kpis.get("total_employees")),
        ("Attrition Rate (%)", uploaded_kpis.get("attrition_rate"), main_kpis.get("attrition_rate")),
        ("Average Salary", uploaded_kpis.get("average_salary"), main_kpis.get("average_salary")),
        ("Attendance Rate (%)", uploaded_kpis.get("attendance_rate"), main_kpis.get("attendance_rate")),
        ("Average Performance", uploaded_kpis.get("average_performance"), main_kpis.get("average_performance")),
    ]

    uploaded_dept = da.workforce_breakdown(clean_df).get("headcount_by_department")
    main_dept = ae.headcount_by_department(main_df)
    uploaded_gender = da.workforce_breakdown(clean_df).get("gender_distribution")
    main_gender = ae.gender_distribution(main_df)

    return render_template(
        "data_upload/compare.html", dataset=dataset, rows=rows,
        uploaded_dept=uploaded_dept, main_dept=main_dept,
        uploaded_gender=uploaded_gender, main_gender=main_gender, na_label=da.NA,
    )


@data_upload_bp.route("/<int:dataset_id>/export/<kind>/<fmt>")
@permission_required("view_reports")
def export(dataset_id, kind, fmt):
    dataset = UploadedDataset.query.get_or_404(dataset_id)
    try:
        raw_df, clean_df = _load_clean(dataset)
    except da.DatasetLoadError as e:
        flash(str(e), "danger")
        return redirect(url_for("data_upload.index"))

    if kind == "cleaned":
        export_df = clean_df
    elif kind == "quality":
        report = da.validate_dataset(raw_df, dataset.column_mapping)
        export_df = pd.DataFrame({"Issue": report["issues"]}) if report["issues"] else pd.DataFrame(
            {"Issue": ["No data quality issues detected."]})
    elif kind == "insights":
        business_insights = da.generate_insights(clean_df)
        export_df = pd.DataFrame({"Insight": business_insights})
    elif kind == "kpis":
        kpis = da.compute_kpis(clean_df)
        export_df = pd.DataFrame(list(kpis.items()), columns=["Metric", "Value"])
    else:
        return "Unknown export type", 404

    filename_base = f"{kind}_{dataset.id}_{datetime.utcnow().strftime('%Y%m%d')}"

    if fmt == "csv":
        buffer = io.StringIO()
        export_df.to_csv(buffer, index=False)
        mem = io.BytesIO(buffer.getvalue().encode("utf-8"))
        return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=f"{filename_base}.csv")

    if fmt == "excel":
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            export_df.to_excel(writer, index=False, sheet_name=kind[:30])
        buffer.seek(0)
        return send_file(buffer, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                          as_attachment=True, download_name=f"{filename_base}.xlsx")

    return "Unsupported format", 400


@data_upload_bp.route("/<int:dataset_id>/delete", methods=["POST"])
@permission_required("view_analytics")
def delete(dataset_id):
    dataset = UploadedDataset.query.get_or_404(dataset_id)
    full_path = _full_path(dataset)
    if os.path.isfile(full_path):
        try:
            os.remove(full_path)
        except OSError:
            pass
    db.session.delete(dataset)
    db.session.commit()
    flash("Dataset removed.", "info")
    return redirect(url_for("data_upload.index"))
