"""
Odoo MCP Server — CEO Decision Support Agent.

Exposes Odoo business data (sales, inventory, finance, HR, CRM)
as MCP tools via JSON-RPC for AI-powered executive insights.
"""

import json
import os
import logging
from datetime import date, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP
from odoo_client import OdooClient

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Odoo MCP",
    instructions=(
        "MCP server kết nối Odoo ERP qua JSON-RPC. "
        "Cung cấp dữ liệu kinh doanh real-time: doanh thu, tồn kho, chi phí, nhân sự, CRM. "
        "Tất cả dữ liệu đều READ-ONLY. Tiền tệ mặc định là VND."
    ),
)

odoo = OdooClient()

# Cache of installed module names (populated on first check)
_installed_modules: set[str] | None = None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HELPERS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def _check_modules(*module_names: str) -> list[str]:
    """Return list of module_names that are NOT installed. Empty = all OK."""
    global _installed_modules
    if _installed_modules is None:
        rows = await odoo.search_read(
            "ir.module.module",
            [("state", "=", "installed")],
            fields=["name"],
            limit=0,
        )
        _installed_modules = {r["name"] for r in rows}
    return [m for m in module_names if m not in _installed_modules]


def _module_missing_response(tool_name: str, missing: list[str]) -> str:
    """Return a user-friendly JSON error when required Odoo modules are not installed."""
    return _fmt({
        "error": f"Tool '{tool_name}' yêu cầu Odoo module chưa được cài đặt.",
        "missing_modules": missing,
        "action": "Vui lòng cài đặt các module trên trong Odoo (Settings → Apps) rồi thử lại.",
    })


# Allowlist of models accessible via generic search_records
_ALLOWED_MODELS = {
    "sale.order", "sale.order.line",
    "product.template", "product.product",
    "res.partner",
    "account.move", "account.move.line",
    "stock.quant", "stock.warehouse.orderpoint", "stock.picking",
    "stock.move", "stock.move.line",
    "mrp.production", "mrp.bom", "mrp.bom.line",
    "hr.employee", "hr.department",
    "hr.payslip", "hr.leave",
    "crm.lead", "crm.stage",
    "ir.module.module",
}


def _period_domain(
    field: str, period: str
) -> list:
    """Convert a period keyword to an Odoo domain filter."""
    today = date.today()
    if period == "today":
        return [(field, ">=", today.isoformat()), (field, "<=", today.isoformat())]
    if period == "this_week":
        start = today - timedelta(days=today.weekday())
        return [(field, ">=", start.isoformat()), (field, "<=", today.isoformat())]
    if period == "this_month":
        start = today.replace(day=1)
        return [(field, ">=", start.isoformat()), (field, "<=", today.isoformat())]
    if period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        first_prev = last_prev.replace(day=1)
        return [(field, ">=", first_prev.isoformat()), (field, "<=", last_prev.isoformat())]
    if period == "this_quarter":
        q_start_month = ((today.month - 1) // 3) * 3 + 1
        start = today.replace(month=q_start_month, day=1)
        return [(field, ">=", start.isoformat()), (field, "<=", today.isoformat())]
    if period == "this_year":
        start = today.replace(month=1, day=1)
        return [(field, ">=", start.isoformat()), (field, "<=", today.isoformat())]
    # fallback: try as ISO date range "2025-01-01,2025-03-31"
    if "," in period:
        parts = period.split(",", 1)
        return [(field, ">=", parts[0].strip()), (field, "<=", parts[1].strip())]
    return []


def _fmt(data: Any) -> str:
    """Format data as readable JSON string."""
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  SALES & REVENUE TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_revenue_summary(
    period: str = "this_month",
    group_by: str = "warehouse",
) -> str:
    """
    Báo cáo doanh thu theo thời gian.

    Args:
        period: Khoảng thời gian — today, this_week, this_month, last_month,
                this_quarter, this_year, hoặc "YYYY-MM-DD,YYYY-MM-DD"
        group_by: Nhóm theo — warehouse (kho/chi nhánh), category (loại SP),
                  salesperson (nhân viên bán), month (theo tháng), none

    Returns:
        Doanh thu gộp theo nhóm, bao gồm số đơn hàng và doanh thu trung bình.
    """
    domain = [("state", "in", ["sale", "done"])] + _period_domain("date_order", period)

    # warehouse_id only exists on sale.order when 'stock' module is installed
    missing = await _check_modules("stock") if group_by == "warehouse" else []
    groupby_map = {
        "warehouse": ["warehouse_id"] if not missing else ["company_id"],
        "category": ["categ_id"],
        "salesperson": ["user_id"],
        "month": ["date_order:month"],
        "none": [],
    }
    groupby_fields = groupby_map.get(group_by, ["user_id"])

    if not groupby_fields:
        # Tổng doanh thu không group
        orders = await odoo.search_read(
            "sale.order", domain,
            fields=["amount_total", "currency_id"],
            limit=0,
        )
        total = sum(o["amount_total"] for o in orders)
        return _fmt({
            "period": period,
            "total_orders": len(orders),
            "total_revenue": total,
            "avg_order_value": round(total / len(orders), 0) if orders else 0,
            "currency": "VND",
        })

    result = await odoo.read_group(
        "sale.order", domain,
        fields=["amount_total", "order_line"],
        groupby=groupby_fields,
    )
    return _fmt({"period": period, "group_by": group_by, "data": result})


@mcp.tool()
async def get_top_products(
    period: str = "this_month",
    limit: int = 10,
    sort_by: str = "revenue",
) -> str:
    """
    Top sản phẩm bán chạy nhất.

    Args:
        period: Khoảng thời gian
        limit: Số sản phẩm trả về (mặc định 10)
        sort_by: Sắp xếp theo — revenue (doanh thu) hoặc quantity (số lượng)

    Returns:
        Danh sách sản phẩm với doanh thu & số lượng bán.
    """
    order_domain = [("state", "in", ["sale", "done"])] + _period_domain("date_order", period)
    # Lấy order IDs
    orders = await odoo.search_read(
        "sale.order", order_domain, fields=["id"], limit=0
    )
    order_ids = [o["id"] for o in orders]
    if not order_ids:
        return _fmt({"period": period, "message": "Không có đơn hàng trong khoảng thời gian này", "data": []})

    orderby = "price_subtotal desc" if sort_by == "revenue" else "product_uom_qty desc"
    result = await odoo.read_group(
        "sale.order.line",
        [("order_id", "in", order_ids)],
        fields=["product_id", "price_subtotal", "product_uom_qty"],
        groupby=["product_id"],
        limit=limit,
        orderby=orderby,
    )
    return _fmt({"period": period, "sort_by": sort_by, "top_products": result})


@mcp.tool()
async def get_sales_orders(
    period: str = "this_month",
    state: str = "all",
    limit: int = 20,
) -> str:
    """
    Danh sách đơn hàng với chi tiết.

    Args:
        period: Khoảng thời gian
        state: Trạng thái — all, draft (nháp), sale (đã xác nhận), done (hoàn thành), cancel (huỷ)
        limit: Số đơn trả về

    Returns:
        Danh sách đơn hàng: mã đơn, khách hàng, tổng tiền, trạng thái.
    """
    domain = _period_domain("date_order", period)
    if state != "all":
        domain.append(("state", "=", state))

    # warehouse_id only available when stock module is installed
    missing = await _check_modules("stock")
    base_fields = ["name", "partner_id", "date_order", "amount_total",
                   "state", "user_id", "invoice_status"]
    if not missing:
        base_fields.append("warehouse_id")

    orders = await odoo.search_read(
        "sale.order", domain,
        fields=base_fields,
        limit=limit,
        order="date_order desc",
    )
    return _fmt({"period": period, "state": state, "count": len(orders), "orders": orders})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  INVENTORY TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_inventory_summary(
    warehouse: str = "all",
) -> str:
    """
    Tồn kho hiện tại theo kho/chi nhánh.

    Args:
        warehouse: Tên kho hoặc "all" để xem tất cả.

    Returns:
        Tồn kho gộp: tổng số lượng, giá trị tồn kho theo từng kho.
    """
    missing = await _check_modules("stock")
    if missing:
        return _module_missing_response("get_inventory_summary", missing)

    domain: list = [("quantity", ">", 0)]
    if warehouse != "all":
        domain.append(("warehouse_id.name", "ilike", warehouse))

    result = await odoo.read_group(
        "stock.quant", domain,
        fields=["warehouse_id", "quantity", "value"],
        groupby=["warehouse_id"],
    )
    return _fmt({"warehouse_filter": warehouse, "inventory": result})


@mcp.tool()
async def get_low_stock_alerts(limit: int = 20) -> str:
    """
    Cảnh báo sản phẩm sắp hết hàng (tồn kho dưới mức tối thiểu).

    Args:
        limit: Số sản phẩm trả về

    Returns:
        Danh sách sản phẩm cần bổ sung tồn kho khẩn cấp.
    """
    missing = await _check_modules("stock")
    if missing:
        return _module_missing_response("get_low_stock_alerts", missing)

    # Products below reorder point
    orderpoints = await odoo.search_read(
        "stock.warehouse.orderpoint",
        [("qty_to_order", ">", 0)],
        fields=["product_id", "warehouse_id", "product_min_qty",
                "product_max_qty", "qty_on_hand", "qty_to_order"],
        limit=limit,
        order="qty_to_order desc",
    )
    return _fmt({"alert_count": len(orderpoints), "low_stock_items": orderpoints})


@mcp.tool()
async def get_stock_valuation(warehouse: str = "all") -> str:
    """
    Giá trị tồn kho hiện tại.

    Args:
        warehouse: Tên kho hoặc "all"

    Returns:
        Tổng giá trị tồn kho theo sản phẩm và kho.
    """
    missing = await _check_modules("stock")
    if missing:
        return _module_missing_response("get_stock_valuation", missing)

    domain: list = [("quantity", ">", 0)]
    if warehouse != "all":
        domain.append(("warehouse_id.name", "ilike", warehouse))

    result = await odoo.read_group(
        "stock.quant", domain,
        fields=["product_categ_id", "quantity", "value"],
        groupby=["product_categ_id"],
        orderby="value desc",
    )
    total_value = sum(r.get("value", 0) for r in result)
    return _fmt({
        "warehouse_filter": warehouse,
        "total_value": total_value,
        "currency": "VND",
        "by_category": result,
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  FINANCE / ACCOUNTING TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_profit_loss(period: str = "this_month") -> str:
    """
    Báo cáo lãi lỗ chi tiết: doanh thu, giá vốn, chi phí vận hành, thuế, lợi nhuận.

    Args:
        period: Khoảng thời gian

    Returns:
        Doanh thu, giá vốn, lợi nhuận gộp, chi phí vận hành,
        lợi nhuận trước thuế, chi phí thuế TNDN, lợi nhuận sau thuế.
        Tương thích Odoo 15 (account_internal_group) + kế toán Việt Nam.
    """
    date_domain = _period_domain("date", period)
    base = date_domain + [("parent_state", "=", "posted")]

    # ── 1. Doanh thu (TK 5xxx — income group) ──────────────────────────────
    revenue_rows = await odoo.read_group(
        "account.move.line",
        base + [("account_internal_group", "in", ["income", "income_other"])],
        fields=["account_id", "balance"],
        groupby=["account_id"],
    )
    total_revenue = abs(sum(r.get("balance", 0) for r in revenue_rows))

    # ── 2. Giá vốn hàng bán — COGS (TK 632 — kế toán Việt Nam) ───────────
    cogs_rows = await odoo.read_group(
        "account.move.line",
        base + [("account_id.code", "=like", "632%")],
        fields=["account_id", "balance"],
        groupby=["account_id"],
    )
    total_cogs = sum(r.get("balance", 0) for r in cogs_rows)

    # ── 3. Chi phí vận hành (expense group — lọc Python để loại trừ 632 và 821)
    all_expense_rows = await odoo.read_group(
        "account.move.line",
        base + [("account_internal_group", "=", "expense")],
        fields=["account_id", "balance"],
        groupby=["account_id"],
    )
    opex_rows = [
        r for r in all_expense_rows
        if not str((r.get("account_id") or [0, ""])[1]).startswith(("632", "821"))
    ]
    total_opex = sum(r.get("balance", 0) for r in opex_rows)

    # ── 4. Chi phí thuế TNDN (TK 821) ─────────────────────────────────────
    tax_rows = await odoo.read_group(
        "account.move.line",
        base + [("account_id.code", "=like", "821%")],
        fields=["account_id", "balance"],
        groupby=["account_id"],
    )
    total_income_tax = sum(r.get("balance", 0) for r in tax_rows)

    # ── 5. Tính lợi nhuận ──────────────────────────────────────────────────
    gross_profit       = total_revenue - total_cogs
    profit_before_tax  = gross_profit - total_opex
    profit_after_tax   = profit_before_tax - total_income_tax

    def pct(val: float) -> float:
        return round(val / total_revenue * 100, 1) if total_revenue else 0

    return _fmt({
        "period": period,
        "currency": "VND",
        "revenue": total_revenue,
        "revenue_breakdown": [{"account": r.get("account_id"), "amount": abs(r.get("balance", 0))} for r in revenue_rows],
        "cogs": total_cogs,
        "gross_profit": gross_profit,
        "gross_margin_pct": pct(gross_profit),
        "operating_expenses": total_opex,
        "opex_breakdown": [{"account": r.get("account_id"), "amount": r.get("balance", 0)} for r in opex_rows],
        "profit_before_tax": profit_before_tax,
        "profit_before_tax_pct": pct(profit_before_tax),
        "income_tax_expense": total_income_tax,
        "profit_after_tax": profit_after_tax,
        "net_margin_pct": pct(profit_after_tax),
        "note": "COGS = TK 632 | Chi phí vận hành = TK 6xx/7xx (trừ 632) | Thuế = TK 821",
    })


@mcp.tool()
async def get_accounts_receivable(
    period: str = "this_month",
    limit: int = 20,
) -> str:
    """
    Công nợ phải thu — hoá đơn khách chưa thanh toán.

    Args:
        period: Khoảng thời gian tạo hoá đơn
        limit: Số bản ghi trả về (chỉ ảnh hưởng danh sách chi tiết, không ảnh hưởng tổng)

    Returns:
        Tổng công nợ (tính trên toàn bộ tập dữ liệu), phân loại theo hạn (aging),
        và danh sách hoá đơn chưa thu (giới hạn bởi limit).
    """
    domain = [
        ("move_type", "=", "out_invoice"),
        ("state", "=", "posted"),
        ("payment_state", "in", ["not_paid", "partial"]),
    ] + _period_domain("invoice_date", period)

    # True totals from full dataset (not truncated by limit)
    all_invoices = await odoo.search_read(
        "account.move", domain,
        fields=["amount_residual", "invoice_date_due"],
        limit=0,
    )
    total_receivable = sum(inv["amount_residual"] for inv in all_invoices)
    total_count = len(all_invoices)

    # Aging buckets
    today_iso = date.today().isoformat()
    today_date = date.today()
    aging = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "over_90": 0.0}
    overdue_count = 0
    overdue_amount = 0.0
    for inv in all_invoices:
        due = inv.get("invoice_date_due")
        if not due or due >= today_iso:
            aging["current"] += inv["amount_residual"]
        else:
            overdue_count += 1
            overdue_amount += inv["amount_residual"]
            days_overdue = (today_date - date.fromisoformat(due)).days
            if days_overdue <= 30:
                aging["1_30"] += inv["amount_residual"]
            elif days_overdue <= 60:
                aging["31_60"] += inv["amount_residual"]
            elif days_overdue <= 90:
                aging["61_90"] += inv["amount_residual"]
            else:
                aging["over_90"] += inv["amount_residual"]

    # Paginated detail list
    invoices = await odoo.search_read(
        "account.move", domain,
        fields=["name", "partner_id", "invoice_date", "invoice_date_due",
                "amount_total", "amount_residual", "payment_state"],
        limit=limit,
        order="amount_residual desc",
    )

    return _fmt({
        "period": period,
        "total_receivable": total_receivable,
        "total_invoice_count": total_count,
        "returned_count": len(invoices),
        "overdue_count": overdue_count,
        "overdue_amount": overdue_amount,
        "aging": aging,
        "currency": "VND",
        "invoices": invoices,
    })


@mcp.tool()
async def get_expense_breakdown(
    period: str = "this_month",
) -> str:
    """
    Chi tiết chi phí theo danh mục kế toán.

    Args:
        period: Khoảng thời gian

    Returns:
        Chi phí gộp theo loại tài khoản, sắp xếp theo giá trị giảm dần.
    """
    date_domain = _period_domain("date", period)
    result = await odoo.read_group(
        "account.move.line",
        date_domain + [
            ("account_internal_group", "=", "expense"),
            ("parent_state", "=", "posted"),
        ],
        fields=["account_id", "balance"],
        groupby=["account_id"],
        orderby="balance desc",
    )
    # Also include tax accounts (821) which may not be in 'expense' group
    tax_result = await odoo.read_group(
        "account.move.line",
        date_domain + [
            ("account_id.code", "=like", "821%"),
            ("parent_state", "=", "posted"),
        ],
        fields=["account_id", "balance"],
        groupby=["account_id"],
    )
    all_rows = result + [r for r in tax_result if r not in result]
    total = sum(r.get("balance", 0) for r in all_rows)
    return _fmt({"period": period, "total_expenses": total, "currency": "VND", "breakdown": all_rows})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HR / EMPLOYEE TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_employee_summary() -> str:
    """
    Tổng quan nhân sự: số lượng theo phòng ban, chi nhánh, loại hợp đồng.

    Returns:
        Headcount phân bổ theo department, work_location.
    """
    missing = await _check_modules("hr")
    if missing:
        return _module_missing_response("get_employee_summary", missing)

    by_dept = await odoo.read_group(
        "hr.employee",
        [("active", "=", True)],
        fields=["department_id"],
        groupby=["department_id"],
    )
    by_location = await odoo.read_group(
        "hr.employee",
        [("active", "=", True)],
        fields=["work_location_id"],
        groupby=["work_location_id"],
    )
    total = await odoo.search_count("hr.employee", [("active", "=", True)])

    return _fmt({
        "total_employees": total,
        "by_department": by_dept,
        "by_work_location": by_location,
    })


@mcp.tool()
async def get_payroll_summary(period: str = "this_month") -> str:
    """
    Tổng chi phí lương theo kỳ.

    Args:
        period: Khoảng thời gian

    Returns:
        Tổng lương, số phiếu lương, phân bổ theo phòng ban.
    """
    missing = await _check_modules("hr", "om_hr_payroll")
    if missing:
        return _module_missing_response("get_payroll_summary", missing)

    date_domain = _period_domain("date_from", period)
    by_dept = await odoo.read_group(
        "hr.payslip",
        date_domain + [("state", "=", "done")],
        fields=["department_id", "net_wage"],
        groupby=["department_id"],
    )
    total_payslips = await odoo.search_count(
        "hr.payslip", date_domain + [("state", "=", "done")]
    )
    total_wage = sum(r.get("net_wage", 0) for r in by_dept)

    return _fmt({
        "period": period,
        "total_payslips": total_payslips,
        "total_net_wage": total_wage,
        "currency": "VND",
        "by_department": by_dept,
    })


@mcp.tool()
async def get_attendance_summary(period: str = "this_month") -> str:
    """
    Thống kê chấm công và nghỉ phép.

    Args:
        period: Khoảng thời gian

    Returns:
        Tổng giờ làm, số ngày nghỉ phép, tỷ lệ đi làm.
    """
    missing = await _check_modules("hr_holidays")
    if missing:
        return _module_missing_response("get_attendance_summary", missing)

    # Leave requests
    leave_domain = _period_domain("date_from", period) + [("state", "=", "validate")]
    leaves = await odoo.read_group(
        "hr.leave",
        leave_domain,
        fields=["holiday_status_id", "number_of_days"],
        groupby=["holiday_status_id"],
    )
    total_leave_days = sum(r.get("number_of_days", 0) for r in leaves)

    return _fmt({
        "period": period,
        "total_leave_days": total_leave_days,
        "by_leave_type": leaves,
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CRM / PIPELINE TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_crm_pipeline() -> str:
    """
    CRM Pipeline — cơ hội bán hàng theo giai đoạn.

    Returns:
        Số lượng và giá trị cơ hội theo stage, win rate.
    """
    missing = await _check_modules("crm")
    if missing:
        return _module_missing_response("get_crm_pipeline", missing)

    by_stage = await odoo.read_group(
        "crm.lead",
        [("type", "=", "opportunity"), ("active", "=", True)],
        fields=["stage_id", "expected_revenue"],
        groupby=["stage_id"],
    )
    total_won = await odoo.search_count(
        "crm.lead", [("type", "=", "opportunity"), ("stage_id.is_won", "=", True)]
    )
    total_all = await odoo.search_count(
        "crm.lead", [("type", "=", "opportunity")]
    )
    win_rate = round(total_won / total_all * 100, 1) if total_all else 0

    return _fmt({
        "pipeline": by_stage,
        "total_opportunities": total_all,
        "won": total_won,
        "win_rate_pct": win_rate,
        "currency": "VND",
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  EXECUTIVE KPI DASHBOARD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_kpi_dashboard(period: str = "this_month") -> str:
    """
    Bảng KPI tổng hợp cho CEO — tất cả chỉ số quan trọng trong 1 lần gọi.

    Args:
        period: Khoảng thời gian

    Returns:
        Dashboard bao gồm: doanh thu, số đơn, giá trị đơn TB, tồn kho,
        công nợ phải thu, nhân sự, CRM pipeline.
    """
    date_domain_order = _period_domain("date_order", period)
    date_domain_inv = _period_domain("invoice_date", period)

    # Check which optional modules are available
    missing = await _check_modules("stock", "hr", "crm")
    has_stock = "stock" not in missing
    has_hr = "hr" not in missing
    has_crm = "crm" not in missing

    # Revenue (always available via sale.order from base)
    orders = await odoo.search_read(
        "sale.order",
        [("state", "in", ["sale", "done"])] + date_domain_order,
        fields=["amount_total"],
        limit=0,
    )
    total_revenue = sum(o["amount_total"] for o in orders)
    order_count = len(orders)
    aov = round(total_revenue / order_count, 0) if order_count else 0

    # Inventory value (requires stock)
    inventory_value = None
    if has_stock:
        inv_data = await odoo.read_group(
            "stock.quant",
            [("quantity", ">", 0)],
            fields=["value"],
            groupby=[],
        )
        inventory_value = inv_data[0].get("value", 0) if inv_data else 0

    # Receivables
    receivables = await odoo.search_read(
        "account.move",
        [
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "in", ["not_paid", "partial"]),
        ] + date_domain_inv,
        fields=["amount_residual"],
        limit=0,
    )
    total_ar = sum(r["amount_residual"] for r in receivables)

    # Employees (requires hr)
    employee_count = None
    if has_hr:
        employee_count = await odoo.search_count("hr.employee", [("active", "=", True)])

    # CRM (requires crm)
    crm_count = None
    if has_crm:
        crm_count = await odoo.search_count(
            "crm.lead", [("type", "=", "opportunity"), ("active", "=", True)]
        )

    # Low stock (requires stock)
    low_stock_count = None
    if has_stock:
        low_stock_count = await odoo.search_count(
            "stock.warehouse.orderpoint", [("qty_to_order", ">", 0)]
        )

    kpi: dict[str, Any] = {
        "revenue": total_revenue,
        "order_count": order_count,
        "avg_order_value": aov,
        "accounts_receivable": total_ar,
    }
    if inventory_value is not None:
        kpi["inventory_value"] = inventory_value
    if employee_count is not None:
        kpi["employee_count"] = employee_count
    if crm_count is not None:
        kpi["crm_opportunities"] = crm_count
    if low_stock_count is not None:
        kpi["low_stock_alerts"] = low_stock_count
    if missing:
        kpi["unavailable_modules"] = missing

    return _fmt({
        "period": period,
        "currency": "VND",
        "kpi": kpi,
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MANUFACTURING / PRODUCTION ANALYSIS TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def get_production_analysis(
    period: str = "this_month",
    group_by: str = "product",
) -> str:
    """
    Phân tích sản xuất — tổng hợp lệnh sản xuất (Manufacturing Orders).

    Args:
        period: Khoảng thời gian — today, this_week, this_month, last_month,
                this_quarter, this_year, hoặc "YYYY-MM-DD,YYYY-MM-DD"
        group_by: Nhóm theo — product (sản phẩm), state (trạng thái),
                  month (theo tháng), none

    Returns:
        Số lượng lệnh SX, sản lượng, phân bổ theo nhóm.
    """
    missing = await _check_modules("mrp")
    if missing:
        return _module_missing_response("get_production_analysis", missing)

    date_domain = _period_domain("date_finished", period)

    groupby_map = {
        "product": ["product_id"],
        "state": ["state"],
        "month": ["date_finished:month"],
        "none": [],
    }
    groupby_fields = groupby_map.get(group_by, ["product_id"])

    if not groupby_fields:
        orders = await odoo.search_read(
            "mrp.production",
            date_domain,
            fields=["product_qty", "qty_produced", "state"],
            limit=0,
        )
        total_planned = sum(o["product_qty"] for o in orders)
        total_produced = sum(o.get("qty_produced", 0) for o in orders)
        states = {}
        for o in orders:
            s = o.get("state", "unknown")
            states[s] = states.get(s, 0) + 1
        return _fmt({
            "period": period,
            "total_orders": len(orders),
            "total_planned_qty": total_planned,
            "total_produced_qty": total_produced,
            "completion_pct": round(total_produced / total_planned * 100, 1) if total_planned else 0,
            "by_state": states,
        })

    result = await odoo.read_group(
        "mrp.production",
        date_domain,
        fields=["product_qty", "qty_produced"],
        groupby=groupby_fields,
    )
    return _fmt({"period": period, "group_by": group_by, "data": result})


@mcp.tool()
async def get_material_consumption(
    period: str = "this_month",
    group_by: str = "product",
    limit: int = 50,
) -> str:
    """
    Báo cáo nguyên vật liệu tiêu thụ — NVL đã xuất kho cho sản xuất.

    Trích xuất từ stock.move có raw_material_production_id (liên kết lệnh SX),
    trạng thái done, trong kỳ chỉ định.

    Args:
        period: Khoảng thời gian — today, this_week, this_month, last_month,
                this_quarter, this_year, hoặc "YYYY-MM-DD,YYYY-MM-DD"
        group_by: Nhóm theo — product (theo NVL), production (theo lệnh SX), none
        limit: Số bản ghi tối đa (cho mode none)

    Returns:
        Lượng NVL tiêu thụ gộp theo nhóm, bao gồm số lượng và đơn vị tính.
    """
    missing = await _check_modules("mrp")
    if missing:
        return _module_missing_response("get_material_consumption", missing)

    date_domain = _period_domain("date", period)
    base_domain = date_domain + [
        ("state", "=", "done"),
        ("raw_material_production_id", "!=", False),
    ]

    if group_by == "product":
        result = await odoo.read_group(
            "stock.move",
            base_domain,
            fields=["product_id", "product_uom_qty"],
            groupby=["product_id"],
            orderby="product_uom_qty desc",
        )
        # Enrich with UoM info
        enriched = []
        for r in result:
            enriched.append({
                "product": r.get("product_id"),
                "total_qty": r.get("product_uom_qty", 0),
                "move_count": r.get("__count", r.get("product_id_count", 0)),
            })
        return _fmt({
            "period": period,
            "group_by": "product",
            "total_materials": len(enriched),
            "data": enriched,
        })

    if group_by == "production":
        result = await odoo.read_group(
            "stock.move",
            base_domain,
            fields=["raw_material_production_id", "product_uom_qty"],
            groupby=["raw_material_production_id"],
            orderby="product_uom_qty desc",
        )
        return _fmt({
            "period": period,
            "group_by": "production",
            "total_productions": len(result),
            "data": result,
        })

    # mode: none — chi tiết từng dòng
    moves = await odoo.search_read(
        "stock.move",
        base_domain,
        fields=[
            "product_id", "product_uom_qty", "product_uom",
            "raw_material_production_id", "date",
        ],
        limit=limit,
        order="date desc",
    )
    count = await odoo.search_count("stock.move", base_domain)
    return _fmt({
        "period": period,
        "group_by": "none",
        "total_matching": count,
        "returned": len(moves),
        "moves": moves,
    })


@mcp.tool()
async def get_bom_overview(
    product_name: str = "",
    limit: int = 10,
) -> str:
    """
    Xem định mức nguyên liệu (Bill of Materials) — bao gồm thành phần NVL.

    Args:
        product_name: Lọc theo tên sản phẩm (tìm kiếm gần đúng). Để trống = tất cả.
        limit: Số BOM trả về tối đa.

    Returns:
        Danh sách BOM với các thành phần NVL, số lượng, đơn vị tính.
    """
    missing = await _check_modules("mrp")
    if missing:
        return _module_missing_response("get_bom_overview", missing)

    domain: list = []
    if product_name:
        domain.append(("product_tmpl_id.name", "ilike", product_name))

    boms = await odoo.search_read(
        "mrp.bom",
        domain,
        fields=["product_tmpl_id", "product_qty", "product_uom_id",
                "type", "code"],
        limit=limit,
        order="id desc",
    )

    # Fetch BOM lines for each BOM
    bom_ids = [b["id"] for b in boms]
    if bom_ids:
        lines = await odoo.search_read(
            "mrp.bom.line",
            [("bom_id", "in", bom_ids)],
            fields=["bom_id", "product_id", "product_qty", "product_uom_id"],
            limit=0,
        )
        # Group lines by bom_id
        lines_by_bom: dict[int, list] = {}
        for line in lines:
            bid = line["bom_id"][0] if isinstance(line["bom_id"], list) else line["bom_id"]
            lines_by_bom.setdefault(bid, []).append({
                "product": line["product_id"],
                "qty": line["product_qty"],
                "uom": line["product_uom_id"],
            })
        for bom in boms:
            bom["components"] = lines_by_bom.get(bom["id"], [])

    return _fmt({"total_boms": len(boms), "boms": boms})


@mcp.tool()
async def get_production_efficiency(
    period: str = "this_month",
) -> str:
    """
    Hiệu suất sản xuất — so sánh kế hoạch vs thực tế, tỷ lệ hoàn thành.

    Args:
        period: Khoảng thời gian

    Returns:
        Tổng sản lượng kế hoạch, thực tế, tỷ lệ hoàn thành,
        phân bổ theo trạng thái lệnh SX.
    """
    missing = await _check_modules("mrp")
    if missing:
        return _module_missing_response("get_production_efficiency", missing)

    date_domain = _period_domain("date_finished", period)

    # All production orders in period
    orders = await odoo.search_read(
        "mrp.production",
        date_domain,
        fields=["name", "product_id", "product_qty", "qty_produced",
                "state", "date_start", "date_finished"],
        limit=0,
    )

    total_planned = 0.0
    total_produced = 0.0
    by_state: dict[str, dict] = {}
    completed_durations = []

    for o in orders:
        qty_plan = o.get("product_qty", 0)
        qty_done = o.get("qty_produced", 0)
        state = o.get("state", "unknown")
        total_planned += qty_plan
        total_produced += qty_done

        if state not in by_state:
            by_state[state] = {"count": 0, "planned_qty": 0, "produced_qty": 0}
        by_state[state]["count"] += 1
        by_state[state]["planned_qty"] += qty_plan
        by_state[state]["produced_qty"] += qty_done

    return _fmt({
        "period": period,
        "total_orders": len(orders),
        "total_planned_qty": total_planned,
        "total_produced_qty": total_produced,
        "completion_pct": round(total_produced / total_planned * 100, 1) if total_planned else 0,
        "by_state": by_state,
        "state_legend": {
            "draft": "Nháp",
            "confirmed": "Đã xác nhận",
            "progress": "Đang sản xuất",
            "to_close": "Chờ đóng",
            "done": "Hoàn thành",
            "cancel": "Đã huỷ",
        },
    })


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GENERIC EXPLORATION TOOLS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@mcp.tool()
async def search_records(
    model: str,
    domain: str = "[]",
    fields: str = "[]",
    limit: int = 10,
    order: str = "id desc",
) -> str:
    """
    Tìm kiếm linh hoạt trên các model Odoo được phép.

    Args:
        model: Tên model Odoo (vd: "sale.order", "product.template", "res.partner")
        domain: Odoo domain filter dạng JSON (vd: '[["state","=","sale"]]')
        fields: Danh sách fields dạng JSON (vd: '["name","amount_total"]') — [] = tất cả
        limit: Số bản ghi tối đa
        order: Sắp xếp (vd: "create_date desc")

    Returns:
        Danh sách bản ghi thoả mãn điều kiện.
    """
    if model not in _ALLOWED_MODELS:
        return _fmt({
            "error": f"Model '{model}' không nằm trong danh sách được phép truy cập.",
            "allowed_models": sorted(_ALLOWED_MODELS),
        })

    parsed_domain = json.loads(domain) if isinstance(domain, str) else domain
    parsed_fields = json.loads(fields) if isinstance(fields, str) else fields

    records = await odoo.search_read(
        model,
        parsed_domain,
        fields=parsed_fields or None,
        limit=limit,
        order=order,
    )
    count = await odoo.search_count(model, parsed_domain)
    return _fmt({"model": model, "total_matching": count, "returned": len(records), "records": records})


@mcp.tool()
async def get_model_fields(model: str) -> str:
    """
    Liệt kê các field có sẵn trên model Odoo — hữu ích để khám phá dữ liệu.

    Args:
        model: Tên model Odoo (vd: "sale.order")

    Returns:
        Danh sách fields với tên, loại, mô tả.
    """
    if model not in _ALLOWED_MODELS:
        return _fmt({
            "error": f"Model '{model}' không nằm trong danh sách được phép truy cập.",
            "allowed_models": sorted(_ALLOWED_MODELS),
        })

    fields_data = await odoo.fields_get(model, ["string", "type", "required", "help"])
    # Format concisely
    summary = {
        name: {
            "label": info.get("string", ""),
            "type": info.get("type", ""),
            "required": info.get("required", False),
        }
        for name, info in fields_data.items()
        if not name.startswith("__")
    }
    return _fmt({"model": model, "field_count": len(summary), "fields": summary})


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ENTRYPOINT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    mcp.run()
