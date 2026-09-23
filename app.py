import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import re

# ============================================================
# إعداد الصفحة
# ============================================================

st.set_page_config(
    page_title="تحليل بيانات الترقيات",
    page_icon="📈",
    layout="wide"
)

st.title("📈 تحليل بيانات الترقيات")
st.caption(
    "تحليل المدة الزمنية للبقاء قبل الترقية حسب الجهات الحكومية "
    "وأنواع الترقيات، مع تحليل الاتجاهات الزمنية."
)

# ============================================================
# أسماء الأعمدة
# ============================================================

COL_ENTITY = "الدائرة"
COL_EMP_ID = "الرقم الوظيفي"
COL_EMP_NAME = "اسم الموظف"
COL_HIRE_DATE = "تاريخ التعيين"
COL_PROMO_DATE = "تاريخ الترقية"
COL_PROMO_TYPE = "نوع الترقية"

# ============================================================
# تنظيف أسماء الأعمدة
# ============================================================

def clean_text(value):
    if pd.isna(value):
        return value

    value = str(value)

    # إزالة RTL / LTR / Unicode marks
    hidden_chars = [
        "\u200e", "\u200f",
        "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
        "\u2066", "\u2067", "\u2068", "\u2069",
        "\ufeff"
    ]

    for char in hidden_chars:
        value = value.replace(char, "")

    # NBSP
    value = value.replace("\xa0", " ")

    # توحيد المسافات
    value = re.sub(r"\s+", " ", value).strip()

    return value


def clean_column_names(df):
    df = df.copy()
    df.columns = [clean_text(col) for col in df.columns]
    return df


# ============================================================
# تحويل التاريخ
# يدعم:
# 03/07/2026
# 3/7/2026
# 03-07-2026
# Excel serial dates
# والتواريخ المحاطة برموز RTL
# ============================================================

def parse_date_value(value):

    if pd.isna(value):
        return pd.NaT

    # لو أصلاً Timestamp
    if isinstance(value, pd.Timestamp):
        return value

    # Excel date serial
    if isinstance(value, (int, float, np.integer, np.floating)):
        try:
            if 20000 <= float(value) <= 80000:
                return pd.Timestamp("1899-12-30") + pd.to_timedelta(
                    float(value), unit="D"
                )
        except:
            pass

    text = clean_text(value)

    if text is None:
        return pd.NaT

    text = str(text).strip()

    if text == "" or text.lower() in ["nan", "nat", "none"]:
        return pd.NaT

    # توحيد الفواصل
    text = text.replace("-", "/")
    text = text.replace(".", "/")

    # إزالة أي شيء غريب حول التاريخ
    text = re.sub(r"[^\d/]", "", text)

    # DD/MM/YYYY
    match = re.fullmatch(
        r"(\d{1,2})/(\d{1,2})/(\d{4})",
        text
    )

    if match:
        day, month, year = map(int, match.groups())

        try:
            return pd.Timestamp(
                year=year,
                month=month,
                day=day
            )
        except:
            return pd.NaT

    # محاولة أخيرة
    try:
        return pd.to_datetime(
            text,
            dayfirst=True,
            errors="coerce"
        )
    except:
        return pd.NaT


# ============================================================
# قراءة الملف
# ============================================================

def read_uploaded_file(uploaded_file):

    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):
        try:
            return pd.read_csv(uploaded_file)
        except:
            uploaded_file.seek(0)
            return pd.read_csv(
                uploaded_file,
                encoding="utf-8-sig"
            )

    return pd.read_excel(uploaded_file)


# ============================================================
# تجهيز البيانات
# ============================================================

def prepare_data(df):

    df = clean_column_names(df)

    # تنظيف الحقول النصية المهمة
    text_columns = [
        COL_ENTITY,
        COL_EMP_ID,
        COL_EMP_NAME,
        COL_PROMO_TYPE,
        "الوحدة التنظيمية",
        "الجنسية",
        "فئة الجنسية",
        "الجنس",
        "الفئة الوظيفية",
        "المجموعة الوظيفية الرئيسية",
        "المجموعة الوظيفية الفرعية",
        "نوع الوظيفة ( أساسية / داعمة )"
    ]

    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].apply(clean_text)

    # حفظ التاريخ الأصلي
    if COL_HIRE_DATE in df.columns:
        df["تاريخ التعيين - الأصلي"] = df[COL_HIRE_DATE]

    if COL_PROMO_DATE in df.columns:
        df["تاريخ الترقية - الأصلي"] = df[COL_PROMO_DATE]

    # تحويل التاريخ
    df[COL_HIRE_DATE] = df[COL_HIRE_DATE].apply(parse_date_value)
    df[COL_PROMO_DATE] = df[COL_PROMO_DATE].apply(parse_date_value)

    # تحويل الرقم الوظيفي إلى نص
    df[COL_EMP_ID] = (
        df[COL_EMP_ID]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    # إزالة السجلات بدون رقم وظيفي أو تاريخ ترقية
    valid_df = df[
        df[COL_EMP_ID].notna()
        & df[COL_PROMO_DATE].notna()
    ].copy()

    # ترتيب كل موظف حسب تاريخ الترقية
    valid_df = valid_df.sort_values(
        by=[COL_EMP_ID, COL_PROMO_DATE]
    ).reset_index(drop=True)

    # ========================================================
    # تاريخ الترقية السابقة
    # ========================================================

    valid_df["تاريخ الترقية السابقة"] = (
        valid_df.groupby(COL_EMP_ID)[COL_PROMO_DATE]
        .shift(1)
    )

    # ========================================================
    # تاريخ بداية فترة الانتظار
    #
    # أول ترقية = تاريخ التعيين
    # الترقيات التالية = تاريخ الترقية السابقة
    # ========================================================

    valid_df["تاريخ بداية مدة البقاء"] = (
        valid_df["تاريخ الترقية السابقة"]
        .fillna(valid_df[COL_HIRE_DATE])
    )

    # رقم الترقية للموظف
    valid_df["رقم الترقية للموظف"] = (
        valid_df.groupby(COL_EMP_ID)
        .cumcount()
        + 1
    )

    valid_df["هل أول ترقية"] = np.where(
        valid_df["رقم الترقية للموظف"] == 1,
        "نعم",
        "لا"
    )

    # ========================================================
    # حساب المدة
    # ========================================================

    valid_df["مدة البقاء بالأيام"] = (
        valid_df[COL_PROMO_DATE]
        - valid_df["تاريخ بداية مدة البقاء"]
    ).dt.days

    valid_df["مدة البقاء بالأشهر"] = (
        valid_df["مدة البقاء بالأيام"] / 30.4375
    ).round(1)

    valid_df["مدة البقاء بالسنوات"] = (
        valid_df["مدة البقاء بالأيام"] / 365.25
    ).round(2)

    # ========================================================
    # السنة والشهر
    # ========================================================

    valid_df["سنة الترقية"] = (
        valid_df[COL_PROMO_DATE].dt.year
    )

    valid_df["شهر الترقية"] = (
        valid_df[COL_PROMO_DATE].dt.month
    )

    month_names = {
        1: "يناير",
        2: "فبراير",
        3: "مارس",
        4: "أبريل",
        5: "مايو",
        6: "يونيو",
        7: "يوليو",
        8: "أغسطس",
        9: "سبتمبر",
        10: "أكتوبر",
        11: "نوفمبر",
        12: "ديسمبر"
    }

    valid_df["اسم الشهر"] = (
        valid_df["شهر الترقية"]
        .map(month_names)
    )

    # ========================================================
    # جودة البيانات
    # ========================================================

    valid_df["حالة المدة"] = "سليمة"

    valid_df.loc[
        valid_df["تاريخ بداية مدة البقاء"].isna(),
        "حالة المدة"
    ] = "لا يوجد تاريخ بداية"

    valid_df.loc[
        valid_df["مدة البقاء بالأيام"] < 0,
        "حالة المدة"
    ] = "تاريخ غير منطقي"

    return df, valid_df


# ============================================================
# Excel Export
# ============================================================

def create_excel_export(
    filtered_df,
    summary_entity,
    summary_type,
    summary_entity_type,
    yearly_trend,
    data_quality
):

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
        datetime_format="DD/MM/YYYY"
    ) as writer:

        filtered_df.to_excel(
            writer,
            sheet_name="تفاصيل الترقيات",
            index=False
        )

        summary_entity.to_excel(
            writer,
            sheet_name="حسب الجهات",
            index=False
        )

        summary_type.to_excel(
            writer,
            sheet_name="حسب نوع الترقية",
            index=False
        )

        summary_entity_type.to_excel(
            writer,
            sheet_name="الجهة ونوع الترقية",
            index=False
        )

        yearly_trend.to_excel(
            writer,
            sheet_name="الاتجاهات السنوية",
            index=False
        )

        data_quality.to_excel(
            writer,
            sheet_name="جودة البيانات",
            index=False
        )

        # تنسيق بسيط
        workbook = writer.book

        for sheet_name in workbook.sheetnames:

            ws = workbook[sheet_name]

            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions

            for column_cells in ws.columns:

                max_length = 0
                column_letter = column_cells[0].column_letter

                for cell in column_cells:

                    try:
                        value = str(cell.value) if cell.value is not None else ""
                        max_length = max(
                            max_length,
                            len(value)
                        )
                    except:
                        pass

                ws.column_dimensions[column_letter].width = min(
                    max(max_length + 2, 12),
                    40
                )

    output.seek(0)

    return output


# ============================================================
# رفع الملف
# ============================================================

uploaded_file = st.file_uploader(
    "ارفع ملف الترقيات",
    type=["xlsx", "xls", "csv"]
)

if uploaded_file is None:

    st.info("ارفع ملف الترقيات للبدء في التحليل.")
    st.stop()


# ============================================================
# قراءة الملف
# ============================================================

try:

    raw_df = read_uploaded_file(uploaded_file)
    raw_df = clean_column_names(raw_df)

except Exception as e:

    st.error(f"حدث خطأ أثناء قراءة الملف: {e}")
    st.stop()


# ============================================================
# التأكد من الأعمدة
# ============================================================

required_columns = [
    COL_ENTITY,
    COL_EMP_ID,
    COL_EMP_NAME,
    COL_HIRE_DATE,
    COL_PROMO_DATE,
    COL_PROMO_TYPE
]

missing_columns = [
    col
    for col in required_columns
    if col not in raw_df.columns
]

if missing_columns:

    st.error(
        "الأعمدة التالية غير موجودة في الملف:\n\n"
        + "\n".join(missing_columns)
    )

    with st.expander("عرض أسماء الأعمدة الموجودة في الملف"):
        st.write(raw_df.columns.tolist())

    st.stop()


# ============================================================
# تجهيز البيانات
# ============================================================

try:

    original_df, df = prepare_data(raw_df)

except Exception as e:

    st.error(
        f"حدث خطأ أثناء تجهيز البيانات: {e}"
    )

    st.stop()


# ============================================================
# جودة تحويل التواريخ
# ============================================================

st.divider()

st.subheader("🧹 فحص وتحويل التواريخ")

total_rows = len(original_df)

valid_hire = original_df[COL_HIRE_DATE].notna().sum()
valid_promo = original_df[COL_PROMO_DATE].notna().sum()

c1, c2, c3 = st.columns(3)

c1.metric(
    "إجمالي السجلات",
    f"{total_rows:,}"
)

c2.metric(
    "تواريخ التعيين المحولة",
    f"{valid_hire:,}"
)

c3.metric(
    "تواريخ الترقية المحولة",
    f"{valid_promo:,}"
)

invalid_dates = original_df[
    original_df[COL_PROMO_DATE].isna()
    | original_df[COL_HIRE_DATE].isna()
].copy()

if len(invalid_dates) > 0:

    with st.expander(
        f"⚠️ يوجد {len(invalid_dates):,} سجل يحتاج مراجعة"
    ):

        display_cols = [
            c for c in [
                COL_ENTITY,
                COL_EMP_ID,
                COL_EMP_NAME,
                "تاريخ التعيين - الأصلي",
                "تاريخ الترقية - الأصلي"
            ]
            if c in invalid_dates.columns
        ]

        st.dataframe(
            invalid_dates[display_cols],
            use_container_width=True
        )


# ============================================================
# Sidebar Filters
# ============================================================

st.sidebar.header("🔎 الفلاتر")

filtered_df = df.copy()


# الدائرة
entities = sorted(
    filtered_df[COL_ENTITY]
    .dropna()
    .astype(str)
    .unique()
)

selected_entities = st.sidebar.multiselect(
    "الدائرة",
    entities,
    default=entities
)

if selected_entities:
    filtered_df = filtered_df[
        filtered_df[COL_ENTITY].isin(selected_entities)
    ]


# نوع الترقية
promotion_types = sorted(
    filtered_df[COL_PROMO_TYPE]
    .dropna()
    .astype(str)
    .unique()
)

selected_types = st.sidebar.multiselect(
    "نوع الترقية",
    promotion_types,
    default=promotion_types
)

if selected_types:
    filtered_df = filtered_df[
        filtered_df[COL_PROMO_TYPE].isin(selected_types)
    ]


# السنوات
years = sorted(
    filtered_df["سنة الترقية"]
    .dropna()
    .astype(int)
    .unique()
)

selected_years = st.sidebar.multiselect(
    "سنة الترقية",
    years,
    default=years
)

if selected_years:
    filtered_df = filtered_df[
        filtered_df["سنة الترقية"].isin(selected_years)
    ]


# الجنس
if "الجنس" in filtered_df.columns:

    gender_options = sorted(
        filtered_df["الجنس"]
        .dropna()
        .astype(str)
        .unique()
    )

    selected_gender = st.sidebar.multiselect(
        "الجنس",
        gender_options,
        default=gender_options
    )

    if selected_gender:
        filtered_df = filtered_df[
            filtered_df["الجنس"].isin(selected_gender)
        ]


# الفئة الوظيفية
if "الفئة الوظيفية" in filtered_df.columns:

    category_options = sorted(
        filtered_df["الفئة الوظيفية"]
        .dropna()
        .astype(str)
        .unique()
    )

    selected_category = st.sidebar.multiselect(
        "الفئة الوظيفية",
        category_options,
        default=category_options
    )

    if selected_category:
        filtered_df = filtered_df[
            filtered_df["الفئة الوظيفية"].isin(
                selected_category
            )
        ]


# ============================================================
# استبعاد المدد غير المنطقية من التحليل
# ============================================================

analysis_df = filtered_df[
    (filtered_df["مدة البقاء بالأيام"].notna())
    & (filtered_df["مدة البقاء بالأيام"] >= 0)
].copy()


# ============================================================
# KPIs
# ============================================================

st.divider()
st.subheader("📊 المؤشرات الرئيسية")

total_promotions = len(analysis_df)

unique_employees = (
    analysis_df[COL_EMP_ID].nunique()
)

avg_years = (
    analysis_df["مدة البقاء بالسنوات"].mean()
)

median_years = (
    analysis_df["مدة البقاء بالسنوات"].median()
)

unique_entities = (
    analysis_df[COL_ENTITY].nunique()
)

k1, k2, k3, k4, k5 = st.columns(5)

k1.metric(
    "إجمالي الترقيات",
    f"{total_promotions:,}"
)

k2.metric(
    "الموظفون المترقون",
    f"{unique_employees:,}"
)

k3.metric(
    "متوسط مدة البقاء",
    f"{avg_years:.2f} سنة"
    if pd.notna(avg_years)
    else "-"
)

k4.metric(
    "وسيط مدة البقاء",
    f"{median_years:.2f} سنة"
    if pd.notna(median_years)
    else "-"
)

k5.metric(
    "عدد الجهات",
    f"{unique_entities:,}"
)


# ============================================================
# Tabs
# ============================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 الاتجاهات",
    "🏢 الجهات الحكومية",
    "🔄 أنواع الترقيات",
    "👤 تفاصيل الموظفين",
    "⚠️ جودة البيانات"
])


# ============================================================
# TAB 1 - Trends
# ============================================================

with tab1:

    st.subheader("الاتجاه العام للترقيات عبر السنوات")

    yearly_trend = (
        analysis_df
        .groupby("سنة الترقية")
        .agg(
            عدد_الترقيات=(COL_EMP_ID, "size"),
            عدد_الموظفين=(COL_EMP_ID, "nunique"),
            متوسط_مدة_البقاء=(
                "مدة البقاء بالسنوات",
                "mean"
            ),
            وسيط_مدة_البقاء=(
                "مدة البقاء بالسنوات",
                "median"
            )
        )
        .reset_index()
        .sort_values("سنة الترقية")
    )

    yearly_trend["متوسط_مدة_البقاء"] = (
        yearly_trend["متوسط_مدة_البقاء"]
        .round(2)
    )

    yearly_trend["وسيط_مدة_البقاء"] = (
        yearly_trend["وسيط_مدة_البقاء"]
        .round(2)
    )

    # --------------------------------------------------------
    # عدد الترقيات سنوياً
    # --------------------------------------------------------

    fig_year = px.line(
        yearly_trend,
        x="سنة الترقية",
        y="عدد_الترقيات",
        markers=True,
        title="اتجاه عدد الترقيات عبر السنوات"
    )

    fig_year.update_layout(
        xaxis_title="السنة",
        yaxis_title="عدد الترقيات"
    )

    st.plotly_chart(
        fig_year,
        use_container_width=True,
        key="yearly_promotion_trend"
    )

    # --------------------------------------------------------
    # متوسط مدة البقاء
    # --------------------------------------------------------

    fig_wait = px.line(
        yearly_trend,
        x="سنة الترقية",
        y="متوسط_مدة_البقاء",
        markers=True,
        title="اتجاه متوسط مدة البقاء قبل الترقية"
    )

    fig_wait.update_layout(
        xaxis_title="السنة",
        yaxis_title="متوسط مدة البقاء - سنة"
    )

    st.plotly_chart(
        fig_wait,
        use_container_width=True,
        key="yearly_wait_trend"
    )

    # --------------------------------------------------------
    # YoY
    # --------------------------------------------------------

    st.subheader("التغير السنوي في عدد الترقيات")

    yoy_df = yearly_trend.copy()

    yoy_df["التغير السنوي %"] = (
        yoy_df["عدد_الترقيات"]
        .pct_change()
        .mul(100)
        .round(1)
    )

    st.dataframe(
        yoy_df,
        use_container_width=True,
        hide_index=True
    )

    # --------------------------------------------------------
    # Trend حسب نوع الترقية
    # --------------------------------------------------------

    st.subheader(
        "اتجاه عدد الترقيات حسب نوع الترقية"
    )

    type_year = (
        analysis_df
        .groupby([
            "سنة الترقية",
            COL_PROMO_TYPE
        ])
        .size()
        .reset_index(name="عدد الترقيات")
    )

    fig_type_year = px.line(
        type_year,
        x="سنة الترقية",
        y="عدد الترقيات",
        color=COL_PROMO_TYPE,
        markers=True
    )

    st.plotly_chart(
        fig_type_year,
        use_container_width=True,
        key="promotion_type_year_trend"
    )

    # --------------------------------------------------------
    # متوسط الانتظار حسب نوع الترقية والسنة
    # --------------------------------------------------------

    st.subheader(
        "متوسط مدة البقاء حسب نوع الترقية عبر السنوات"
    )

    type_wait_year = (
        analysis_df
        .groupby([
            "سنة الترقية",
            COL_PROMO_TYPE
        ])["مدة البقاء بالسنوات"]
        .mean()
        .round(2)
        .reset_index()
    )

    fig_type_wait = px.line(
        type_wait_year,
        x="سنة الترقية",
        y="مدة البقاء بالسنوات",
        color=COL_PROMO_TYPE,
        markers=True
    )

    st.plotly_chart(
        fig_type_wait,
        use_container_width=True,
        key="promotion_type_wait_year"
    )

    # --------------------------------------------------------
    # التوزيع الشهري
    # --------------------------------------------------------

    st.subheader("التوزيع الشهري للترقيات")

    monthly = (
        analysis_df
        .groupby([
            "شهر الترقية",
            "اسم الشهر"
        ])
        .size()
        .reset_index(name="عدد الترقيات")
        .sort_values("شهر الترقية")
    )

    fig_month = px.bar(
        monthly,
        x="اسم الشهر",
        y="عدد الترقيات",
        text_auto=True
    )

    st.plotly_chart(
        fig_month,
        use_container_width=True,
        key="monthly_promotions"
    )


# ============================================================
# TAB 2 - الجهات
# ============================================================

with tab2:

    st.subheader(
        "المدة الزمنية للبقاء حسب الجهات الحكومية"
    )

    summary_entity = (
        analysis_df
        .groupby(COL_ENTITY)
        .agg(
            عدد_الترقيات=(COL_EMP_ID, "size"),
            عدد_الموظفين=(COL_EMP_ID, "nunique"),
            متوسط_مدة_البقاء=(
                "مدة البقاء بالسنوات",
                "mean"
            ),
            وسيط_مدة_البقاء=(
                "مدة البقاء بالسنوات",
                "median"
            ),
            أقل_مدة=(
                "مدة البقاء بالسنوات",
                "min"
            ),
            أعلى_مدة=(
                "مدة البقاء بالسنوات",
                "max"
            )
        )
        .reset_index()
    )

    numeric_cols = [
        "متوسط_مدة_البقاء",
        "وسيط_مدة_البقاء",
        "أقل_مدة",
        "أعلى_مدة"
    ]

    summary_entity[numeric_cols] = (
        summary_entity[numeric_cols]
        .round(2)
    )

    st.dataframe(
        summary_entity,
        use_container_width=True,
        hide_index=True
    )

    fig_entity = px.bar(
        summary_entity.sort_values(
            "متوسط_مدة_البقاء",
            ascending=False
        ),
        x=COL_ENTITY,
        y="متوسط_مدة_البقاء",
        text_auto=".2f",
        title="متوسط مدة البقاء قبل الترقية حسب الجهة"
    )

    st.plotly_chart(
        fig_entity,
        use_container_width=True,
        key="entity_wait_bar"
    )

    # --------------------------------------------------------
    # Trend الجهات
    # --------------------------------------------------------

    st.subheader(
        "اتجاه متوسط مدة البقاء حسب الجهة"
    )

    entity_year = (
        analysis_df
        .groupby([
            "سنة الترقية",
            COL_ENTITY
        ])["مدة البقاء بالسنوات"]
        .mean()
        .round(2)
        .reset_index()
    )

    fig_entity_year = px.line(
        entity_year,
        x="سنة الترقية",
        y="مدة البقاء بالسنوات",
        color=COL_ENTITY,
        markers=True
    )

    st.plotly_chart(
        fig_entity_year,
        use_container_width=True,
        key="entity_year_trend"
    )


# ============================================================
# TAB 3 - أنواع الترقيات
# ============================================================

with tab3:

    st.subheader(
        "تحليل المدة الزمنية حسب نوع الترقية"
    )

    summary_type = (
        analysis_df
        .groupby(COL_PROMO_TYPE)
        .agg(
            عدد_الترقيات=(COL_EMP_ID, "size"),
            عدد_الموظفين=(COL_EMP_ID, "nunique"),
            متوسط_مدة_البقاء=(
                "مدة البقاء بالسنوات",
                "mean"
            ),
            وسيط_مدة_البقاء=(
                "مدة البقاء بالسنوات",
                "median"
            ),
            أقل_مدة=(
                "مدة البقاء بالسنوات",
                "min"
            ),
            أعلى_مدة=(
                "مدة البقاء بالسنوات",
                "max"
            )
        )
        .reset_index()
    )

    type_numeric = [
        "متوسط_مدة_البقاء",
        "وسيط_مدة_البقاء",
        "أقل_مدة",
        "أعلى_مدة"
    ]

    summary_type[type_numeric] = (
        summary_type[type_numeric]
        .round(2)
    )

    st.dataframe(
        summary_type,
        use_container_width=True,
        hide_index=True
    )

    fig_type = px.bar(
        summary_type.sort_values(
            "متوسط_مدة_البقاء",
            ascending=False
        ),
        x=COL_PROMO_TYPE,
        y="متوسط_مدة_البقاء",
        text_auto=".2f",
        title="متوسط مدة البقاء حسب نوع الترقية"
    )

    st.plotly_chart(
        fig_type,
        use_container_width=True,
        key="promotion_type_wait_bar"
    )

    # --------------------------------------------------------
    # الجهة × نوع الترقية
    # --------------------------------------------------------

    st.subheader(
        "المدة الزمنية لكل نوع ترقية حسب الجهة الحكومية"
    )

    summary_entity_type = (
        analysis_df
        .groupby([
            COL_ENTITY,
            COL_PROMO_TYPE
        ])
        .agg(
            عدد_الترقيات=(COL_EMP_ID, "size"),
            عدد_الموظفين=(COL_EMP_ID, "nunique"),
            متوسط_مدة_البقاء=(
                "مدة البقاء بالسنوات",
                "mean"
            ),
            وسيط_مدة_البقاء=(
                "مدة البقاء بالسنوات",
                "median"
            ),
            أقل_مدة=(
                "مدة البقاء بالسنوات",
                "min"
            ),
            أعلى_مدة=(
                "مدة البقاء بالسنوات",
                "max"
            )
        )
        .reset_index()
    )

    summary_entity_type[
        [
            "متوسط_مدة_البقاء",
            "وسيط_مدة_البقاء",
            "أقل_مدة",
            "أعلى_مدة"
        ]
    ] = (
        summary_entity_type[
            [
                "متوسط_مدة_البقاء",
                "وسيط_مدة_البقاء",
                "أقل_مدة",
                "أعلى_مدة"
            ]
        ]
        .round(2)
    )

    st.dataframe(
        summary_entity_type,
        use_container_width=True,
        hide_index=True
    )

    # Heatmap
    pivot = summary_entity_type.pivot(
        index=COL_ENTITY,
        columns=COL_PROMO_TYPE,
        values="متوسط_مدة_البقاء"
    )

    if not pivot.empty:

        fig_heat = px.imshow(
            pivot,
            text_auto=".2f",
            aspect="auto",
            title=(
                "متوسط مدة البقاء: "
                "الجهة × نوع الترقية"
            )
        )

        st.plotly_chart(
            fig_heat,
            use_container_width=True,
            key="entity_type_heatmap"
        )


# ============================================================
# TAB 4 - تفاصيل الموظفين
# ============================================================

with tab4:

    st.subheader(
        "تفاصيل تسلسل الترقيات لكل موظف"
    )

    employee_columns = [
        COL_ENTITY,
        COL_EMP_ID,
        COL_EMP_NAME,
        COL_HIRE_DATE,
        "رقم الترقية للموظف",
        "تاريخ الترقية السابقة",
        COL_PROMO_DATE,
        COL_PROMO_TYPE,
        "تاريخ بداية مدة البقاء",
        "مدة البقاء بالأيام",
        "مدة البقاء بالأشهر",
        "مدة البقاء بالسنوات",
        "هل أول ترقية",
        "حالة المدة"
    ]

    employee_columns = [
        col for col in employee_columns
        if col in filtered_df.columns
    ]

    employee_details = filtered_df[
        employee_columns
    ].copy()

    st.dataframe(
        employee_details,
        use_container_width=True,
        hide_index=True
    )

    st.info(
        "أول ترقية للموظف تُحسب من تاريخ التعيين، "
        "أما الترقيات التالية فتُحسب من تاريخ الترقية السابقة."
    )


# ============================================================
# TAB 5 - جودة البيانات
# ============================================================

with tab5:

    st.subheader("فحص جودة بيانات الترقيات")

    no_start = filtered_df[
        filtered_df["تاريخ بداية مدة البقاء"].isna()
    ]

    negative_duration = filtered_df[
        filtered_df["مدة البقاء بالأيام"] < 0
    ]

    q1, q2, q3 = st.columns(3)

    q1.metric(
        "تواريخ غير قابلة للتحويل",
        f"{len(invalid_dates):,}"
    )

    q2.metric(
        "لا يوجد تاريخ بداية",
        f"{len(no_start):,}"
    )

    q3.metric(
        "مدد سالبة / غير منطقية",
        f"{len(negative_duration):,}"
    )

    data_quality = pd.concat(
        [
            no_start,
            negative_duration
        ],
        ignore_index=True
    ).drop_duplicates()

    if data_quality.empty:

        st.success(
            "لا توجد مشاكل واضحة في مدد الترقيات."
        )

    else:

        quality_cols = [
            col for col in [
                COL_ENTITY,
                COL_EMP_ID,
                COL_EMP_NAME,
                COL_HIRE_DATE,
                "تاريخ الترقية السابقة",
                COL_PROMO_DATE,
                COL_PROMO_TYPE,
                "مدة البقاء بالسنوات",
                "حالة المدة"
            ]
            if col in data_quality.columns
        ]

        st.dataframe(
            data_quality[quality_cols],
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# إنشاء الملخصات للتصدير
# ============================================================

summary_entity = (
    analysis_df
    .groupby(COL_ENTITY)
    .agg(
        عدد_الترقيات=(COL_EMP_ID, "size"),
        عدد_الموظفين=(COL_EMP_ID, "nunique"),
        متوسط_مدة_البقاء=(
            "مدة البقاء بالسنوات",
            "mean"
        ),
        وسيط_مدة_البقاء=(
            "مدة البقاء بالسنوات",
            "median"
        ),
        أقل_مدة=("مدة البقاء بالسنوات", "min"),
        أعلى_مدة=("مدة البقاء بالسنوات", "max")
    )
    .reset_index()
)

summary_type = (
    analysis_df
    .groupby(COL_PROMO_TYPE)
    .agg(
        عدد_الترقيات=(COL_EMP_ID, "size"),
        عدد_الموظفين=(COL_EMP_ID, "nunique"),
        متوسط_مدة_البقاء=(
            "مدة البقاء بالسنوات",
            "mean"
        ),
        وسيط_مدة_البقاء=(
            "مدة البقاء بالسنوات",
            "median"
        ),
        أقل_مدة=("مدة البقاء بالسنوات", "min"),
        أعلى_مدة=("مدة البقاء بالسنوات", "max")
    )
    .reset_index()
)

summary_entity_type = (
    analysis_df
    .groupby([
        COL_ENTITY,
        COL_PROMO_TYPE
    ])
    .agg(
        عدد_الترقيات=(COL_EMP_ID, "size"),
        عدد_الموظفين=(COL_EMP_ID, "nunique"),
        متوسط_مدة_البقاء=(
            "مدة البقاء بالسنوات",
            "mean"
        ),
        وسيط_مدة_البقاء=(
            "مدة البقاء بالسنوات",
            "median"
        ),
        أقل_مدة=("مدة البقاء بالسنوات", "min"),
        أعلى_مدة=("مدة البقاء بالسنوات", "max")
    )
    .reset_index()
)

yearly_trend = (
    analysis_df
    .groupby("سنة الترقية")
    .agg(
        عدد_الترقيات=(COL_EMP_ID, "size"),
        عدد_الموظفين=(COL_EMP_ID, "nunique"),
        متوسط_مدة_البقاء=(
            "مدة البقاء بالسنوات",
            "mean"
        ),
        وسيط_مدة_البقاء=(
            "مدة البقاء بالسنوات",
            "median"
        )
    )
    .reset_index()
)

for temp_df in [
    summary_entity,
    summary_type,
    summary_entity_type,
    yearly_trend
]:
    numeric = temp_df.select_dtypes(
        include=[np.number]
    ).columns

    temp_df[numeric] = temp_df[numeric].round(2)


data_quality_export = pd.concat(
    [
        filtered_df[
            filtered_df["تاريخ بداية مدة البقاء"].isna()
        ],
        filtered_df[
            filtered_df["مدة البقاء بالأيام"] < 0
        ]
    ],
    ignore_index=True
).drop_duplicates()


# ============================================================
# Download Excel
# ============================================================

st.divider()
st.subheader("📥 تصدير التقرير")

excel_file = create_excel_export(
    filtered_df,
    summary_entity,
    summary_type,
    summary_entity_type,
    yearly_trend,
    data_quality_export
)

st.download_button(
    label="📥 تحميل تقرير الترقيات Excel",
    data=excel_file,
    file_name="promotion_analysis.xlsx",
    mime=(
        "application/vnd.openxmlformats-officedocument."
        "spreadsheetml.sheet"
    )
)
